"""
StepRoast AI — Real-time footwork judge backend.

Architecture:
  Mobile app → Stream SFU ← AI Agent (this server)
  The agent watches the dancer's video via Gemini Realtime,
  and sends live audio roasts + text commentary back.
  Text commentary is also relayed via /metrics HTTP polling
  as a fallback when WebRTC audio publisher is unstable.
"""

import os
import re
import asyncio
import logging
import threading
from dotenv import load_dotenv
from vision_agents.core import Agent, AgentLauncher, User, Runner
from vision_agents.plugins import getstream, gemini, deepgram, elevenlabs
from getstream import Stream
from fastapi import Request, HTTPException
from processors.footwork_processor import FootworkProcessor

load_dotenv()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ── Transcript capture ──────────────────────────────────────────────────
class TranscriptCapture:
    """Captures agent transcript fragments and accumulates them into
    complete sentences. Works with both loguru and standard logging."""

    def __init__(self):
        self._lock = threading.Lock()
        self.current_sentence = ""
        self.latest_complete = ""
        self.all_commentary: list[str] = []

    def handle_fragment(self, fragment: str):
        """Process a single transcript fragment."""
        with self._lock:
            self.current_sentence += fragment
            stripped = self.current_sentence.strip()
            # Sentence-ending punctuation → flush
            if stripped and stripped[-1] in ".!?":
                self.latest_complete = stripped
                self.all_commentary.append(stripped)
                if len(self.all_commentary) > 50:
                    self.all_commentary = self.all_commentary[-50:]
                self.current_sentence = ""

    def get_latest(self) -> str:
        with self._lock:
            return self.latest_complete or self.current_sentence.strip()

    def get_all(self) -> list[str]:
        with self._lock:
            return list(self.all_commentary)

    def reset(self):
        with self._lock:
            self.current_sentence = ""
            self.latest_complete = ""
            self.all_commentary.clear()


transcript = TranscriptCapture()


class TranscriptInterceptor:
    """Intercepts stderr to capture transcript lines from SDK logs."""
    
    def __init__(self, original_stderr):
        self.original = original_stderr
        self.buffer = ""
    
    def write(self, text):
        # Always write to original stderr
        self.original.write(text)
        
        # Buffer and process line by line
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if "[Agent transcript]:" in line:
                fragment = line.split("[Agent transcript]:")[-1]
                # Strip ANSI escape codes (e.g. \x1b[0m) before storing
                fragment = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', fragment)
                transcript.handle_fragment(fragment)
    
    def flush(self):
        self.original.flush()


# Install stderr interceptor at module load time
import sys
if not isinstance(sys.stderr, TranscriptInterceptor):
    sys.stderr = TranscriptInterceptor(sys.stderr)


# ── Shared processor instance ───────────────────────────────────────────
footwork = FootworkProcessor()


async def create_agent(**kwargs) -> Agent:
    """Factory called by Vision Agents Runner for each new session."""
    agent = Agent(
        edge=getstream.Edge(),
        agent_user=User(name="StepRoast Coach", id="steproast-agent"),
        instructions="Read @steproast_judge.md",
        llm=gemini.Realtime(fps=10),  # 10 fps for faster real-time analysis
        processors=[],
        stt=deepgram.STT(),
        tts=elevenlabs.TTS(),
    )
    return agent


async def join_call(agent: Agent, call_type: str, call_id: str, **kwargs) -> None:
    """Called when a mobile user spawns a session — agent joins the call."""
    transcript.reset()

    await agent.create_user()
    call = await agent.create_call(call_type, call_id)

    async with agent.join(call):
        # Kick-start Gemini with an opening prompt
        await agent.llm.simple_response(
            text=(
                "You are StepRoast Coach. Look at the feet right now. "
                "Give one honest coaching sentence about what you actually see — "
                "if they're not moving, say so."
            )
        )

        # Re-prompt Gemini every 5s with observational coaching questions
        async def keep_roasting():
            prompts = [
                "Are the feet moving right now? Give one honest coaching sentence.",
                "What is the actual speed and rhythm of the feet? One sentence.",
                "Are they on beat or off? Be direct, one sentence.",
                "How is the foot placement and balance right now? One sentence.",
                "Is the footwork improving or staying the same? One honest sentence.",
                "What specific thing should they fix right now? One sentence.",
            ]
            i = 0
            while True:
                await asyncio.sleep(5)  # 5 seconds between prompts
                try:
                    prompt = prompts[i % len(prompts)]
                    await agent.llm.simple_response(text=prompt)
                    i += 1
                except Exception as e:
                    logger.warning(f"Re-prompt failed: {e}")
                    break

        roast_task = asyncio.create_task(keep_roasting())
        try:
            await agent.finish()
        finally:
            roast_task.cancel()
            try:
                await roast_task
            except asyncio.CancelledError:
                pass


# ── Runner / FastAPI ────────────────────────────────────────────────────────
launcher = AgentLauncher(create_agent=create_agent, join_call=join_call)
runner = Runner(launcher)

# Stream client for /token endpoint
stream_client = Stream(
    api_key=os.getenv("STREAM_API_KEY"),
    api_secret=os.getenv("STREAM_API_SECRET"),
)


@runner.fast_api.get("/token")
async def get_token(user_id: str = "mobile-user"):
    """Generate a Stream user token for the mobile app."""
    try:
        api_key = os.getenv("STREAM_API_KEY")
        api_secret = os.getenv("STREAM_API_SECRET")
        
        if not api_key or not api_secret:
            logger.error(f"Missing Stream credentials: api_key={bool(api_key)}, api_secret={bool(api_secret)}")
            return {"error": "Missing Stream API credentials", "token": None, "user_id": user_id}
        
        logger.info(f"Creating Stream user: {user_id}")
        stream_client.create_user(name="Dancer", id=user_id)
        
        logger.info(f"Generating Stream token for: {user_id}")
        token = stream_client.create_token(user_id, expiration=3600)
        
        return {
            "token": token,
            "user_id": user_id,
            "api_key": api_key,
        }
    except Exception as e:
        logger.error(f"Token generation failed: {type(e).__name__}: {e}", exc_info=True)
        return {"error": str(e), "token": None, "user_id": user_id}


@runner.fast_api.post("/sessions")
async def create_session(request: Request):
    """Create a new AI agent session for a call."""
    try:
        body = await request.json()
        call_id = body.get("call_id")
        call_type = body.get("call_type", "default")
        
        if not call_id:
            logger.error("Missing call_id in session creation")
            raise HTTPException(status_code=400, detail="Missing call_id")
        
        logger.info(f"Creating session for call: {call_id}")
        session_id = f"session-{call_id}"
        
        return {
            "session_id": session_id,
            "call_id": call_id,
            "call_type": call_type,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session creation failed: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@runner.fast_api.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """End an AI agent session."""
    try:
        logger.info(f"Ending session: {session_id}")
        return {"session_id": session_id, "status": "ended"}
    except Exception as e:
        logger.error(f"Session deletion failed: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@runner.fast_api.get("/metrics")
async def get_metrics():
    """Return live footwork metrics + AI commentary (polled by mobile)."""
    return {
        "step_count": footwork.step_count,
        "avg_speed": float(
            __import__("numpy").mean(footwork.speed_history)
        ) if footwork.speed_history else 0,
        "current_speed": footwork.current_speed,
        "frame_count": footwork.frame_count,
        "persons_detected": footwork.persons_detected,
        "summary": footwork.get_metrics_text(),
        # Live AI commentary captured from agent transcripts
        "commentary": transcript.get_latest(),
        "all_commentary": transcript.get_all(),
    }


if __name__ == "__main__":
    runner.cli()

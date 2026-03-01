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
import time
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
        self._version = 0
        self._last_update = 0.0

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
                self._version += 1
                self._last_update = time.time()

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
            self._version = 0
            self._last_update = 0.0

    @property
    def version(self) -> int:
        with self._lock:
            return self._version


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
                # Collapse multiple spaces into single space
                fragment = re.sub(r'  +', ' ', fragment)
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
    footwork.reset()
    agent = Agent(
        edge=getstream.Edge(),
        agent_user=User(name="FootworkAI Coach", id="steproast-agent"),
        instructions="Read @steproast_judge.md",
        llm=gemini.Realtime(fps=10),
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
        # Opening prompt — observe first, then coach
        await agent.llm.simple_response(
            text=(
                "You are FootworkAI Coach watching a dancer through their front camera. "
                "You can see their full body. Describe what movement you see and "
                "give one encouraging coaching sentence."
            )
        )

        # Re-prompt loop — short punchy prompts, never dies
        async def keep_roasting():
            await asyncio.sleep(3)  # let opening prompt land first

            prompts = [
                "What's the energy RIGHT NOW? 1 sentence!",
                "Fast or slow? Quick comment!",
                "What's moving the most? React!",
                "On rhythm or off? 1 sentence!",
                "What stands out? Quick take!",
                "Full body vibing? 1 sentence!",
            ]

            i = 0
            while True:
                prompt = prompts[i % len(prompts)]
                i += 1

                # Retry up to 5 times — but loop NEVER dies, just skips failed prompt
                for attempt in range(5):
                    try:
                        await agent.llm.simple_response(text=prompt)
                        break  # success — move to next prompt
                    except Exception as e:
                        logger.warning(f"Re-prompt attempt {attempt + 1}/5 failed: {e}")
                        if attempt < 4:
                            await asyncio.sleep(2)
                        # else: give up this prompt, continue loop

                await asyncio.sleep(4)  # wait before next prompt

        roast_task = asyncio.create_task(keep_roasting())
        try:
            # 5-minute max session — prevents infinite hangs if mobile disconnects
            await asyncio.wait_for(agent.finish(), timeout=300)
        except asyncio.TimeoutError:
            logger.warning("Session timed out after 5 minutes")
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


@runner.fast_api.get("/verdict")
async def get_verdict():
    """Return a final score breakdown + improvement tips based on AI commentary."""
    commentary = transcript.get_all()
    commentary_text = " ".join(commentary).lower()
    
    # Analyze keywords in the AI's commentary to generate score
    positive_keywords = ["fast", "sharp", "electric", "synced", "rhythm", "high", "quick", 
                        "dynamic", "engaged", "perfect", "driving", "dominating", "intense"]
    neutral_keywords = ["standing", "still", "slow", "minimal", "needs"]
    
    positive_count = sum(1 for word in positive_keywords if word in commentary_text)
    neutral_count = sum(1 for word in neutral_keywords if word in commentary_text)
    total_comments = len(commentary)
    
    # Each category 0-25
    # Speed: based on "fast", "quick", "tempo" mentions
    speed_indicators = ["fast", "quick", "tempo", "rapid"]
    speed_score = min(25, sum(3 for word in speed_indicators if word in commentary_text))
    
    # Rhythm: based on "rhythm", "synced", "beat" mentions
    rhythm_indicators = ["rhythm", "synced", "beat", "timing"]
    rhythm_score = min(25, sum(4 for word in rhythm_indicators if word in commentary_text))
    
    # Complexity: based on "dynamic", "sharp", "pattern", "movement" variety
    complexity_indicators = ["dynamic", "sharp", "pattern", "isolation", "switching"]
    complexity_score = min(25, sum(3 for word in complexity_indicators if word in commentary_text))
    
    # Commitment: based on total positive commentary + "energy", "engaged", "high"
    commitment_indicators = ["energy", "engaged", "intensity", "momentum", "full body"]
    commitment_score = min(25, sum(3 for word in commitment_indicators if word in commentary_text))
    
    # Boost all scores if lots of positive commentary
    if total_comments > 8:
        boost = min(5, total_comments - 8)
        speed_score = min(25, speed_score + boost)
        rhythm_score = min(25, rhythm_score + boost)
        complexity_score = min(25, complexity_score + boost)
        commitment_score = min(25, commitment_score + boost)
    
    total = speed_score + rhythm_score + complexity_score + commitment_score

    tips = []
    if speed_score < 10:
        tips.append("Work on faster, snappier movements")
    if rhythm_score < 10:
        tips.append("Focus on staying on rhythm — find the beat")
    if complexity_score < 10:
        tips.append("Try more varied patterns and dynamic movement")
    if commitment_score < 10:
        tips.append("Bring more energy — commit fully to each move")
    if not tips:
        tips = ["Push for even more intensity", "Try faster tempo music next time"]

    highlights = transcript.get_all()
    # Pick last 3 non-empty highlights
    highlights = [h for h in highlights if h.strip()][-3:]

    return {
        "total_score": total,
        "breakdown": {
            "speed": speed_score,
            "rhythm": rhythm_score,
            "complexity": complexity_score,
            "commitment": commitment_score,
        },
        "tips": tips[:3],
        "stats": {
            "total_feedback": total_comments,
            "positive_mentions": positive_count,
            "session_quality": "High" if total_comments > 10 else "Medium" if total_comments > 5 else "Short",
        },
        "highlights": highlights,
    }


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
        "commentary_version": transcript.version,
        "all_commentary": transcript.get_all(),
    }


if __name__ == "__main__":
    runner.cli()

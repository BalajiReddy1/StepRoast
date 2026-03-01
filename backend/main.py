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
import asyncio
import logging
import threading
from dotenv import load_dotenv
from vision_agents.core import Agent, AgentLauncher, User, Runner
from vision_agents.plugins import getstream, gemini, deepgram, elevenlabs
from processors.footwork_processor import FootworkProcessor
from getstream import Stream

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
_loguru_sink_id = None  # Track sink ID to avoid duplicates


def install_loguru_sink():
    """Install loguru sink AFTER SDK initializes (call from join_call)."""
    global _loguru_sink_id
    try:
        from loguru import logger as loguru_logger
        
        # Remove previous sink if exists
        if _loguru_sink_id is not None:
            try:
                loguru_logger.remove(_loguru_sink_id)
            except ValueError:
                pass
        
        def _transcript_sink(message):
            # Use str(message) to get full formatted log line
            msg = str(message)
            if "[Agent transcript]:" in msg:
                # Extract fragment after the marker (keep leading space for word separation!)
                fragment = msg.split("[Agent transcript]:")[-1].rstrip('\n')
                transcript.handle_fragment(fragment)
        
        _loguru_sink_id = loguru_logger.add(
            _transcript_sink,
            level="INFO",
            filter=lambda record: "Agent transcript" in record["message"],
        )
        loguru_logger.info("✅ Loguru transcript sink installed")
    except Exception as e:
        logger.warning(f"⚠️ Could not install loguru sink: {e}")


# ── Shared processor instance ───────────────────────────────────────────
footwork = FootworkProcessor()


async def create_agent(**kwargs) -> Agent:
    """Factory called by Vision Agents Runner for each new session."""
    agent = Agent(
        edge=getstream.Edge(),
        agent_user=User(name="StepRoast AI", id="steproast-agent"),
        instructions="Read @steproast_judge.md",
        llm=gemini.Realtime(fps=5),
        processors=[],
        stt=deepgram.STT(),
        tts=elevenlabs.TTS(),
    )
    return agent


async def join_call(agent: Agent, call_type: str, call_id: str, **kwargs) -> None:
    """Called when a mobile user spawns a session — agent joins the call."""
    transcript.reset()
    
    # Install loguru sink NOW (after SDK has set up its logging)
    install_loguru_sink()

    await agent.create_user()
    call = await agent.create_call(call_type, call_id)

    async with agent.join(call):
        # Kick-start Gemini with an opening prompt
        await agent.llm.simple_response(
            text=(
                "You are StepRoast, a savage but funny AI dance judge. "
                "You're watching a live video of someone's feet dancing. "
                "Give a 1-sentence hype intro, then DESCRIBE what you literally see!"
            )
        )

        # Keep Gemini roasting by re-prompting every 6 seconds
        # Prompts force Gemini to describe SPECIFIC things it sees
        async def keep_roasting():
            prompts = [
                "DESCRIBE exactly what the feet are doing RIGHT NOW - are they moving left, right, jumping, shuffling? Give a funny 1-sentence reaction to the SPECIFIC movement you see!",
                "What COLOR are the shoes or socks you see? Are the feet fast or slow right now? One punchy roast about what you're LITERALLY watching!",
                "Count how many steps you just saw in the last few seconds! Are they on beat or off? React with one savage sentence!",
                "Is the dancer's weight on their left foot or right foot RIGHT NOW? Roast their balance in one sentence!",
                "What's the FLOOR look like? Are the feet close together or spread apart? Give a quick funny observation!",
                "Are those feet ACTUALLY dancing or just standing there? Describe the movement speed and roast it!",
            ]
            i = 0
            while True:
                await asyncio.sleep(6)  # Slightly faster prompting
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
    stream_client.create_user(name="Dancer", id=user_id)
    token = stream_client.create_token(user_id, expiration=3600)
    return {
        "token": token,
        "user_id": user_id,
        "api_key": os.getenv("STREAM_API_KEY"),
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
        "all_commentary": transcript.get_all(),
    }


if __name__ == "__main__":
    runner.cli()

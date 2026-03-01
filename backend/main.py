"""
StepRoast AI — Real-time footwork judge backend.

Architecture:
  Mobile app → Stream SFU ← AI Agent (this server)
  The agent watches the dancer's video, runs YOLO pose detection,
  and sends live audio roasts + text commentary back.
"""

import os
import logging
from dotenv import load_dotenv
from vision_agents.core import Agent, AgentLauncher, User, Runner
from vision_agents.plugins import getstream, gemini, deepgram, elevenlabs
from processors.footwork_processor import FootworkProcessor
from getstream import Stream

load_dotenv()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ── Shared processor instance so we can read metrics from the /token route ──
footwork = FootworkProcessor()


async def create_agent(**kwargs) -> Agent:
    """Factory called by Vision Agents Runner for each new session."""
    agent = Agent(
        edge=getstream.Edge(),
        agent_user=User(name="StepRoast AI", id="steproast-agent"),
        instructions="Read @steproast_judge.md",
        llm=gemini.Realtime(fps=5),
        # YOLO disabled — CPU-only Codespace can't handle 30 FPS inference
        # Gemini Realtime sees the raw video directly and judges visually
        processors=[],
        stt=deepgram.STT(),
        tts=elevenlabs.TTS(),
    )
    return agent


async def join_call(agent: Agent, call_type: str, call_id: str, **kwargs) -> None:
    """Called when a mobile user spawns a session — agent joins the call."""
    await agent.create_user()
    call = await agent.create_call(call_type, call_id)

    async with agent.join(call):
        # Kick-start Gemini with an opening prompt (like the golf coach example)
        await agent.llm.simple_response(
            text=(
                "You are StepRoast, a savage but funny AI dance judge. "
                "The camera is on the floor pointing up at the dancer's feet. "
                "Start by greeting the dancer with a short hype intro (1 sentence). "
                "Then watch their footwork and give SHORT, punchy, live commentary "
                "while they dance — max 1-2 sentences per response. Be funny, not mean. "
                "When the call is about to end, give a final score out of 100."
            )
        )
        await agent.finish()


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
    """Return live footwork metrics (polled by mobile for vibe meter)."""
    return {
        "step_count": footwork.step_count,
        "avg_speed": float(
            __import__("numpy").mean(footwork.speed_history)
        ) if footwork.speed_history else 0,
        "current_speed": footwork.current_speed,
        "frame_count": footwork.frame_count,
        "persons_detected": footwork.persons_detected,
        "summary": footwork.get_metrics_text(),
    }


if __name__ == "__main__":
    runner.cli()

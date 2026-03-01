# FootworkAI 🎤

**Real-time AI dance coach powered by Vision Agents SDK + Gemini Realtime Vision**

Built for the **Vision Possible Hackathon** — Stream × Google.

---

## What is FootworkAI?

FootworkAI is a mobile app that watches you dance through your phone's camera and gives you **live, continuous AI coaching** on your moves. Point your front camera at yourself, hit START, and an AI coach powered by Google Gemini will watch your full body in real time — commenting on your energy, rhythm, footwork, and style every few seconds.

When you stop, you get a **full breakdown scorecard** — Speed, Rhythm, Complexity, Commitment — with tips and highlights from the session.

---

## Demo

> The AI coach watches you dance live and says things like:
> - *"Full body energy is electric — keep that intensity and push for more dynamic!"*
> - *"Feet are perfectly synced to the rhythm — drive that fast pace!"*
> - *"Sharp arm movements are standing out — try adding more dynamic hip isolation to match!"*

After stopping, you get a 4-category score breakdown with improvement tips.

---

## How Vision Agents Powers This

FootworkAI is built on top of the **[Vision Agents SDK](https://github.com/GetStream/vision-agents)** by Stream.

### The Pipeline

```
📱 Phone Camera (front-facing, full body)
        ↓  WebRTC video stream
🔗 Stream SFU (Real-time Media Server)
        ↓  Video frames
🤖 Vision Agents SDK
        ↓  10fps frames
🧠 Gemini Realtime (Live API)
        ↓  Text coaching response captured from transcript
📊 FastAPI /metrics endpoint (polled every 1s)
        ↓
📱 Mobile Screen → Live commentary displayed
```

### Key Vision Agents Components Used

| Component | Usage |
|---|---|
| `AgentLauncher` | Factory pattern — creates a fresh AI agent per session |
| `Runner` | Wraps `AgentLauncher` into a FastAPI server with WebRTC support |
| `Agent` | The AI coach instance — joined into each Stream call |
| `gemini.Realtime(fps=10)` | Streams 10 frames per second of live video to Gemini Live API |
| `getstream.Edge` | Stream's WebRTC edge — bridges phone camera to AI |
| `agent.llm.simple_response(text=...)` | Re-prompts Gemini every 4 seconds to generate new coaching |
| `agent.finish()` | Blocks until session ends (with 5-min timeout) |

### The Agent Instruction Pattern

The agent reads its personality and coaching rules from `steproast_judge.md` via `instructions="Read @steproast_judge.md"`. This keeps the system prompt clean and editable without touching code.

Re-prompts are injected every 4 seconds via `agent.llm.simple_response()` to force fresh observations:

```python
prompts = [
    "What's the energy RIGHT NOW? 1 sentence!",
    "Fast or slow? Quick comment!",
    "What's moving the most? React!",
    "On rhythm or off? 1 sentence!",
    "What stands out? Quick take!",
    "Full body vibing? 1 sentence!",
]
```

Short, directive prompts → faster Gemini response → lower latency coaching.

### Transcript Capture

The Vision Agents SDK logs agent speech to `stderr` as `[Agent transcript]: <fragment>`. We intercept stderr at module load time to capture every text fragment in real time:

```python
class TranscriptInterceptor:
    def write(self, text):
        self.original.write(text)
        if "[Agent transcript]:" in line:
            fragment = line.split("[Agent transcript]:")[-1]
            fragment = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', fragment)  # strip ANSI
            transcript.handle_fragment(fragment)
```

These fragments are accumulated into complete sentences and served via `/metrics` — polled by the mobile app every second.

---

## Technical Architecture

### Backend (Python + FastAPI)

| File | Purpose |
|---|---|
| `main.py` | Vision Agents setup, FastAPI endpoints, transcript capture |
| `steproast_judge.md` | AI coach personality, examples, rules |
| `pyproject.toml` | Dependencies managed with `uv` |

**Endpoints:**

| Endpoint | Method | Description |
|---|---|---|
| `/token` | GET | Generate Stream auth token for mobile |
| `/sessions` | POST | Spawn AI agent into a WebRTC call |
| `/sessions/{id}` | DELETE | End a session |
| `/metrics` | GET | Live AI commentary (polled every 1s) |
| `/verdict` | GET | Final score breakdown after session |

### Mobile (React Native + Expo)

| File | Purpose |
|---|---|
| `src/hooks/useStepRoastAgent.ts` | All session logic — connect, start, stop, poll |
| `src/screens/HomeScreen.tsx` | Landing screen with logo and START button |
| `src/screens/JudgeScreen.tsx` | Live coaching view + results screen |
| `src/components/ScoreCard.tsx` | Score card component |

**Mobile Flow:**
1. User opens app → enters backend URL → hits START
2. App fetches `/token`, creates a Stream WebRTC call
3. App POSTs to `/sessions` → backend spawns AI agent into same call
4. Gemini watches the dancer's camera via WebRTC
5. App polls `/metrics` every 1s → displays live commentary
6. Also listens to Stream Chat channel for real-time text fragments
7. User hits STOP → app fetches `/verdict` → results screen shown



## Project Stack

| Layer | Technology |
|---|---|
| AI Vision | Google Gemini Live API (via Vision Agents SDK) |
| Video Pipeline | Stream SFU + WebRTC |
| Backend Framework | FastAPI (via Vision Agents Runner) |
| Backend Runtime | Python 3.11+, `uv` package manager |
| Backend Hosting | GitHub Codespaces |
| Mobile Framework | React Native + Expo Dev Client |
| Mobile SDKs | `@stream-io/video-react-native-sdk`, `stream-chat` |

---


### Backend (GitHub Codespaces — recommended)

```bash
# 1. Open repo in GitHub Codespaces
# 2. In terminal:
cd backend
cp .env.example .env
# Fill in your API keys in .env
uv sync
python main.py serve --host 0.0.0.0 --port 8000

# 3. In Codespaces: Ports tab → port 8000 → right-click → Make Public
# 4. Copy the URL (e.g. https://xxx-8000.app.github.dev)
```

### Required API Keys (in `backend/.env`)

```env
STREAM_API_KEY=...        # getstream.io
STREAM_API_SECRET=...     # getstream.io
GOOGLE_API_KEY=...        # aistudio.google.com
```

### Mobile (Expo Dev Client)

```bash
cd mobile
npm install
npx expo start --dev-client
# Scan QR with Expo Go or your dev client app
# Enter your Codespace backend URL in the app settings
```

---

## What's Next

- **Beat detection** — sync coaching to actual music BPM
- **Session history** — track improvement over multiple sessions
- **YOLO pose integration** — pixel-level movement analysis running alongside Gemini
- **Multi-dancer** — compare scores between two dancers on the same call

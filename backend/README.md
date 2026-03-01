# StepRoast Backend

Real-time AI footwork judge powered by Vision Agents SDK, YOLO pose detection, and Gemini.

## Quick Start (GitHub Codespaces — recommended)

1. Push this repo to GitHub
2. Go to your repo → **Code** → **Codespaces** → **Create codespace on main**
3. In the Codespace terminal:
   ```bash
   cd backend
   cp .env.example .env
   # Fill in your API keys in .env
   uv sync
   uv run python main.py serve --host 0.0.0.0 --port 8000
   ```
4. The port 8000 will auto-forward. Click **Make Public** in the Ports tab.
5. Copy the Codespace URL (e.g. `https://xxx-8000.app.github.dev`) — paste it in the mobile app's settings.

## Local Development (Linux only — Windows/WSL has WebRTC issues)

```bash
cd backend
pip install uv
uv sync
cp .env.example .env
# Fill in your API keys
uv run python main.py serve --host 0.0.0.0 --port 8000
```

## Environment Variables

See `.env.example` for required keys:
- `STREAM_API_KEY` / `STREAM_API_SECRET` — [getstream.io](https://getstream.io/try-for-free/)
- `GOOGLE_API_KEY` — [AI Studio](https://aistudio.google.com/apikey)
- `DEEPGRAM_API_KEY` — [console.deepgram.com](https://console.deepgram.com)
- `ELEVENLABS_API_KEY` — [elevenlabs.io](https://elevenlabs.io)

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/token` | GET | Generate Stream auth token for mobile app |
| `/sessions` | POST | Spawn AI agent into a call |
| `/sessions/{id}` | DELETE | End an agent session |
| `/metrics` | GET | Live footwork metrics (polled by mobile) |

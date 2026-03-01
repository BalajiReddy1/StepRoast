# FootworkAI — Hackathon Session Summary

## What We Built

**FootworkAI** (formerly StepRoast) — a real-time AI dance footwork coach for the Vision Possible hackathon.

### Full Stack
- **Mobile**: React Native + Expo dev client (local Windows → physical phone)
- **Backend**: Python FastAPI on GitHub Codespaces (port 8000, must be Public)
- **AI Vision**: Vision Agents SDK with Gemini Realtime at 10fps, watching the dancer live
- **Voice Pipeline**: Deepgram STT → Gemini → ElevenLabs TTS → audio back to user
- **Text Commentary**: Captured from SDK stderr (`[Agent transcript]:`), polled via `/metrics` endpoint every 1s on mobile

### Architecture
```
Phone Camera
    ↓
Stream SFU (WebRTC)
    ↓
Vision Agents SDK ← Gemini Realtime (watches video, generates coaching)
    ↓
FastAPI /metrics (text commentary, polled every 1s)
    ↓
Mobile Screen (liveCommentary state)
```

---

## What Works ✅

| Feature | Status |
|---|---|
| End-to-end pipeline: camera → AI → text commentary | ✅ Working |
| Real-time Gemini vision (10fps) watching dancer | ✅ Working |
| Stream SFU WebRTC call setup | ✅ Working |
| Stream Chat integration for live text fragments | ✅ Working |
| ANSI escape code stripping in transcript (`\x1b[0m`) | ✅ Fixed |
| Double-space collapsing in transcript | ✅ Fixed |
| Session management `/sessions` POST + DELETE | ✅ Working |
| `/token` endpoint for Stream auth | ✅ Working |
| `/verdict` endpoint — post-session score breakdown | ✅ Built |
| Results screen: score circle, category bars, tips, highlights | ✅ Built |
| App rebrand: StepRoast → FootworkAI | ✅ Done |
| VibeMeter removed (was crashing/broken) | ✅ Done |
| Skull emoji removed from farewell | ✅ Done |
| Camera correctly set to `facing="front"` (full body) | ✅ Fixed |
| Prompts updated to match front-facing full-body camera | ✅ Fixed |
| Re-prompt retry logic (5 attempts, 2s backoff) | ✅ Added |
| 5-minute session timeout (prevents infinite hang) | ✅ Added |

---

## The ONE Remaining Issue ❌

### AI commentary stops updating after the first line

**Symptom** (seen in logs):
```
[METRICS] {"commentary":"The stage is set, Standing still—jump in with a simple bounce to find the rhythm!","all":1}
[METRICS] {"commentary":"The stage is set, Standing still—jump in with a simple bounce to find the rhythm!","all":1}
[METRICS] {"commentary":"The stage is set, Standing still—jump in with a simple bounce to find the rhythm!","all":1}
... (repeats forever, same line, never updates)
```

**Root Cause Chain:**
1. `agent.finish()` on the backend **never returns** if the mobile client disconnects uncleanly
2. The session hangs indefinitely → backend process runs forever, consuming all resources
3. The re-prompt `keep_roasting()` loop calls `agent.llm.simple_response()` → this starts **failing silently** when session state is corrupt
4. The original loop had `break` on first failure → loop dies → no more re-prompts → transcript never updates → mobile polls the same stale commentary forever

**Why it looked like "commentary stopped":**
- The OPENING PROMPT always fires successfully → produces one line
- Re-prompts then fail → loop breaks → nothing new ever gets generated
- `/metrics` keeps returning the same `latest_complete` indefinitely

---

## What We Changed That May Have Broken It

The original working commit was **`f484067`** — short, punchy prompts:
```
"How's the footwork RIGHT NOW? 1 quick sentence!"
"Fast or slow feet? Quick comment!"
"Balanced or wobbly? 1 sentence!"
"Which foot is leading? React!"
```

We gradually made prompts longer and more descriptive (30+ words each), trying to fix "no movement" false negatives. Longer prompts = Gemini takes longer = more likely to timeout → failures compound.

The camera description was also wrong until `27356d8` — said "floor camera, feet only" when it's actually front-facing showing full body. This caused Gemini to say "no movement" because it couldn't see feet.

---

## Latest Fixes (committed, NOT YET TESTED on Codespace)

Commit `e3df0e2`:
- **Re-prompt retry**: loop retries up to 5 times with 2s backoff before giving up (no longer breaks on first error)
- **5-min session timeout**: `asyncio.wait_for(agent.finish(), timeout=300)` — prevents infinite hangs
- **Stale metrics suppressed**: mobile only updates `liveCommentary` when text actually changes

**To test**: In Codespace → `git pull && python main.py`

---

## If Current Fix Doesn't Work — Fallback Plan

Revert prompts to the short punchy style from `f484067`:
```python
prompts = [
    "How's the dancing RIGHT NOW? 1 quick sentence!",
    "What's the energy like? Quick comment!",
    "What body part stands out? React!",
    "Full body or just vibing? 1 sentence!",
    "Are they on rhythm? Quick take!",
    "What's moving the most? 1 sentence!",
]
```
And keep the judge prompt but trim it down — Gemini Realtime responds faster to short directive prompts.

---

## Commit History (What Changed When)

| Commit | What |
|---|---|
| `e3df0e2` | Re-prompt retry + 5-min timeout + stale metrics fix |
| `c5f2ba8` | Rebalanced coaching prompt — lead with positives |
| `27356d8` | Fixed camera description (front-facing, full body) |
| `c85ccae` | Reverted YOLO processor (was crashing SFU) |
| `1699e1d` | Attached YOLO processor (broke SFU — reverted) |
| `9faa183` | Rebranded StepRoast → FootworkAI |
| `1f7edf0` | Results/score screen + `/verdict` endpoint |
| `c55f831` | Fixed JSX syntax error |
| `47a84cd` | Removed skull/VibeMeter, rewrote judge prompt |
| `f484067` | **Last known working baseline** — original short prompts |

---

## Key Technical Constraints

- `processors=[]` **must stay empty** — adding `FootworkProcessor` to the Vision Agents processor list causes SFU WebSocket to drop within ~2 seconds (`participant not found` error). YOLO and Gemini Realtime cannot share the same WebRTC video track.
- Camera is `facing="front"` — shows full body, NOT floor/feet-only
- Gemini Realtime fps: 10
- Re-prompt interval: 4 seconds
- Backend URL: `https://orange-yodel-gjp6g6q9grr29v4w-8000.app.github.dev` (must be set to Public in Codespaces port visibility)

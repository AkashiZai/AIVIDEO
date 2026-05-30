# CaptionForge AI — Auto-Caption Video Editor

Upload video → AI transcribes speech → pick caption style → preview → export with captions burned in.

## Architecture

- **Backend**: Python + FastAPI + OpenAI Whisper + Typhoon Thai LLM + FFmpeg
- **Frontend**: React + Vite + TypeScript + Zustand
- **Communication**: REST API + WebSocket (real-time progress)

---

## 🚀 Quick Start (Local)

### Prerequisites
- **Python 3.10+**
- **Node.js 18+**
- **FFmpeg** — must be installed and in PATH (for local dev only)

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```
API: `http://localhost:8000`

### Frontend
```bash
cd frontend
npm install
npm run dev
```
Frontend: `http://localhost:5173`

---

## ☁️ Deploy Backend to Cloud (Free)

Deploy to the cloud so you **never need to install FFmpeg** — it's included in the Docker image.

### Option 1: Railway (Recommended)

Railway offers a free tier with $5/month credits — plenty for light use.

**Steps:**
1. Push your code to GitHub
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
3. Railway auto-detects the `railway.json` and `Dockerfile`
4. Set the **Root Directory** to `/backend` if prompted
5. Wait for the build (~3-5 min first time due to Whisper model download)
6. Railway gives you a URL like `https://captionforge-api-xxxx.up.railway.app`

**Environment variables** (optional, set in Railway dashboard):
| Variable | Default | Description |
|----------|---------|-------------|
| `WHISPER_MODEL` | `base` | Whisper model size |
| `MAX_UPLOAD_MB` | `500` | Max upload file size |
| `TYPHOON_API_KEY` | — | Typhoon Thai LLM API key (from [opentyphoon.ai](https://opentyphoon.ai)) |

### Option 2: Render

Render has a free tier with auto-sleep after 15 min inactivity.

**Steps:**
1. Push code to GitHub
2. Go to [render.com](https://render.com) → **New** → **Web Service**
3. Connect your GitHub repo
4. Render auto-detects `render.yaml`
5. Or manually configure:
   - **Environment**: Docker
   - **Dockerfile Path**: `./backend/Dockerfile`
   - **Docker Context**: `./backend`
6. Deploy — get URL like `https://captionforge-api.onrender.com`

> ⚠️ Render free tier sleeps after 15 min — first request may take 30-60s to cold start.

### Option 3: Fly.io

Fly.io offers free allowances (3 shared VMs, 3GB storage).

**Steps:**
```bash
# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Login
fly auth login

# Deploy from project root
fly launch --dockerfile backend/Dockerfile
fly deploy
```

Your app will be at `https://captionforge-api.fly.dev`

---

## 🔗 Connect Frontend to Deployed Backend

After deploying, update the frontend to point to your cloud backend:

### For local development
Create `frontend/.env`:
```env
VITE_API_URL=https://your-backend-url.up.railway.app
```

### For deploying frontend to Vercel/Netlify
Set the environment variable in the dashboard:
```
VITE_API_URL=https://your-backend-url.up.railway.app
```

Then build & deploy:
```bash
cd frontend
npm run build
# Upload the dist/ folder to Vercel/Netlify/Cloudflare Pages
```

---

## 📡 API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/upload` | Upload video file → returns `job_id` |
| `POST` | `/transcribe/{job_id}` | Run Whisper → returns segments |
| `POST` | `/export/{job_id}` | Burn captions → renders video |
| `GET` | `/status/{job_id}` | Job progress (0–100%) |
| `GET` | `/download/{job_id}` | Stream the final video |
| `GET` | `/video/{job_id}` | Stream the original video |
| `WS` | `/ws/{job_id}` | Real-time progress updates |
| `GET` | `/health` | Health check |

---

## 🎨 Caption Styles

| Style | Description |
|-------|-------------|
| 🔥 **TikTok** | Bold word-by-word, center screen with pop effect |
| 📺 **Subtitle** | Classic bottom subtitles with transparent bar |
| ✍️ **Word-by-Word** | Words build up sentence, then clear |
| 🎤 **Karaoke** | Full line visible, active word in yellow |

Each style supports: **Font Size** (S/M/L) · **Text Color** (6 presets + custom) · **Position** (Top/Center/Bottom)

---

## 🏗️ Project Structure

```
├── backend/
│   ├── Dockerfile          # Docker image with FFmpeg
│   ├── main.py             # FastAPI routes + WebSocket
│   ├── whisper_service.py  # Whisper transcription
│   ├── typhoon_correction.py # Typhoon Thai LLM correction
│   ├── ffmpeg_service.py   # FFmpeg caption burning
│   ├── caption_styles.py   # 4 drawtext filter builders
│   ├── job_manager.py      # Job state + WS broadcast
│   ├── models.py           # Pydantic models
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/     # 11 React components
│   │   ├── api.ts          # REST + WebSocket client
│   │   ├── store.ts        # Zustand state
│   │   ├── types.ts        # TypeScript types
│   │   └── index.css       # Dark theme design system
│   └── .env.example        # API URL template
├── railway.json            # Railway deploy config
├── render.yaml             # Render deploy config
├── fly.toml                # Fly.io deploy config
└── README.md
```

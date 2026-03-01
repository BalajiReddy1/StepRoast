# ── StepRoast Backend ──
# Build:  docker build -t steproast-backend ./backend
# Run:    docker run --env-file backend/.env -p 8000:8000 steproast-backend

FROM python:3.12-slim

WORKDIR /app

# System deps for opencv (used by ultralytics) and aiortc
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    gcc g++ libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Copy project files
COPY backend/pyproject.toml backend/uv.lock* ./
RUN uv sync --no-dev 2>/dev/null || uv sync

COPY backend/ ./

# YOLO model will download on first inference (~6MB)
# Pre-download if you want faster cold starts:
# RUN python -c "from ultralytics import YOLO; YOLO('yolo11n-pose.pt')"

EXPOSE 8000

CMD ["uv", "run", "python", "main.py", "serve", "--host", "0.0.0.0", "--port", "8000"]

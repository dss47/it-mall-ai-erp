FROM python:3.12-slim

WORKDIR /app

# Install system dependencies & audio tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    tar \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download local Piper neural TTS & model
RUN mkdir -p /app/piper && cd /app/piper && \
    wget -q https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_amd64.tar.gz && \
    tar -xzf piper_amd64.tar.gz && \
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx && \
    wget -q https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json

# Copy application source
COPY . .

# Start both AudioSocket server (8300) and PDF microservice (8301)
CMD python3 -m agent.server & uvicorn agent.pdf_service:app --host 0.0.0.0 --port 8301

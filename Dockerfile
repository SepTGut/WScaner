FROM node:20-bookworm-slim

# Install Python 3, pip, and Tesseract OCR with Indonesian & English models
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python-is-python3 \
    tesseract-ocr \
    tesseract-ocr-ind \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Node.js dependencies
COPY package*.json ./
RUN npm install --omit=dev

# Install Python dependencies
COPY requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copy application folders
COPY src/ ./src/
COPY data/ ./data/
COPY scripts/ ./scripts/

# Create persistent directories
RUN mkdir -p /app/runtime/temp /app/runtime/auth /app/runtime/logs /app/data/downloads

CMD ["node", "src/bot/bot.js"]

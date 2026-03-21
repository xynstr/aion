FROM python:3.12-slim

WORKDIR /app

# System-Abhängigkeiten (für Playwright, Audio-Pipeline, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Python-Abhängigkeiten
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright Chromium installieren
RUN pip install --no-cache-dir playwright && playwright install chromium --with-deps

# AION-Code kopieren
COPY . .

# Port freigeben
EXPOSE 7000

# Gesundheitscheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7000/api/status')"

CMD ["python", "aion_web.py"]

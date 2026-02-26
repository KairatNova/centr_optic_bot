FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY reqirements.txt ./reqirements.txt
RUN python - <<'PY'
from pathlib import Path
raw = Path('reqirements.txt').read_bytes()
if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
    text = raw.decode('utf-16')
    Path('requirements.txt').write_text(text, encoding='utf-8')
else:
    Path('requirements.txt').write_bytes(raw)
PY
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/logs

CMD ["python", "bot.py"]

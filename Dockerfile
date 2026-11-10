FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 bot
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -U -r requirements.txt

COPY app ./app
RUN mkdir -p /app/data /app/cookies && chown -R bot:bot /app
USER bot

CMD ["python", "-m", "app.main"]

# Build vom Repo-Root:  docker build -f bot/Dockerfile -t reko-bot .
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    BOT_DATA_DIR=/data/raw \
    BOT_DB_PATH=/data/state.db

COPY bot/requirements.txt /app/bot/requirements.txt
RUN pip install --no-cache-dir -r /app/bot/requirements.txt

COPY bot/ /app/bot/

# Standard: einmaliger Value-Lauf. Fuer andere Tasks Command ueberschreiben,
# z.B.:  docker run --rm --env-file bot/.env reko-bot python -m bot.track grade
CMD ["python", "-m", "bot.run"]

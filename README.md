# Optic Bot

## Docker deployment

### 1. Build image

```bash
docker build -t optic-bot:latest .
```

### 2. Prepare env file

Create `.env` file:

```env
BOT_TOKEN=your_telegram_bot_token
OWNER_IDS=123456789
# Optional
DATABASE_URL=sqlite+aiosqlite:///data/database.db
AUTO_BACKUP_INTERVAL_HOURS=24
AUTO_BACKUP_TARGET_IDS=123456789
```

### 3. Run container

```bash
docker run -d \
  --name optic-bot \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  optic-bot:latest
```

The bot runs in polling mode (`python bot.py`).
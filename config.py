import os

# ─── Required ─────────────────────────────────────────────────────────────────
# Set this via environment variable or replace the default below
BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# ─── Timezone ────────────────────────────────────────────────────────────────
# Change to your timezone, e.g. "Europe/Moscow", "Asia/Yekaterinburg", etc.
TIMEZONE: str = os.environ.get("TIMEZONE", "Europe/Moscow")

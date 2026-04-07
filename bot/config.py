import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
REQUIRED_CHANNEL_ID = os.getenv("REQUIRED_CHANNEL_ID", "@JYRYGROUP")
SCRAPE_INTERVAL_MINUTES = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "1"))
DATABASE_PATH = os.getenv("DATABASE_PATH", "db/goethe_bot.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

BOT_NAME = "JYRY AI"

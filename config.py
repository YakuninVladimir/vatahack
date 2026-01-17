import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
DB_DSN = os.getenv("DB_DSN")
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
DB_DSN = os.getenv("DB_DSN")
REDIS_URL = os.getenv("REDIS_URL")

AGENT_URL = os.getenv("AGENT_URL", "http://stub-service:8001")


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


SUMMARY_MAX_MESSAGES = _int_env("SUMMARY_MAX_MESSAGES", 1000)
SUMMARY_MIN_TOPIC_SIZE = _int_env("SUMMARY_MIN_TOPIC_SIZE", 10)
SUMMARY_INCLUDE_NOISE = _bool_env("SUMMARY_INCLUDE_NOISE", True)
SUMMARY_OLLAMA_MODEL = os.getenv("SUMMARY_OLLAMA_MODEL", "qwen2.5:1.5b-instruct")
SUMMARY_CONTEXT_WINDOW_TOKENS = _int_env("SUMMARY_CONTEXT_WINDOW_TOKENS", 4096)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

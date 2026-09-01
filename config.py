"""
config.py

Central configuration for BizLeadBot.

All configuration is loaded from environment variables (or a local .env file
when running locally). Nothing sensitive should ever be hard-coded here.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()  # Loads variables from a local .env file if present (no-op on Render)


def _get_int(name: str, default: int) -> int:
    """Safely parse an integer environment variable, falling back to a default."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"[config] WARNING: {name}='{raw}' is not a valid integer, using default {default}")
        return default


# --- Telegram ---------------------------------------------------------------
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID: int = _get_int("ADMIN_ID", 0)

# --- Database -----------------------------------------------------------------
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/bizleadbot.db").strip()

# --- Scraping limits ----------------------------------------------------------
MAX_PAGES: int = _get_int("MAX_PAGES", 10)
MAX_LEADS: int = _get_int("MAX_LEADS", 5000)
REQUEST_TIMEOUT: int = _get_int("REQUEST_TIMEOUT", 20)

# --- Output ---------------------------------------------------------------------
OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "output").strip()


def validate_config() -> None:
    """
    Validate required configuration at startup.
    Fails fast with a clear message instead of crashing later with a
    confusing traceback.
    """
    errors = []

    if not BOT_TOKEN:
        errors.append("BOT_TOKEN is not set. Get a token from @BotFather and set it in your .env")

    if ADMIN_ID == 0:
        errors.append("ADMIN_ID is not set. Set it to your numeric Telegram user ID.")

    if MAX_PAGES <= 0:
        errors.append("MAX_PAGES must be a positive integer.")

    if MAX_LEADS <= 0:
        errors.append("MAX_LEADS must be a positive integer.")

    if REQUEST_TIMEOUT <= 0:
        errors.append("REQUEST_TIMEOUT must be a positive integer.")

    if errors:
        print("BizLeadBot configuration error(s):")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)


SEARCH_QUERY = "Digital Marketing"
OUTPUT_DIR = "output"
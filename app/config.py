import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    BASE_DIR = BASE_DIR
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    MAX_INPUT_LENGTH = 8192
    MAX_FIELD_OUTPUT_LENGTH = 48
    MAX_DESCRIPTION_OUTPUT_LENGTH = 96
    PUBLIC_DIR = BASE_DIR / "public"
    MAX_URL_CONTENT_SIZE = 2 * 1024 * 1024
    URL_FETCH_TIMEOUT = 15.0
    MAX_URL_REDIRECTS = 5
    REQUIREMENT_FORMATS = ["short", "ultra_short", "tag"]
    WHY_JOIN_FORMATS = ["short", "ultra_short"]

settings = Settings()

from pathlib import Path

import torch


class Settings:
    BASE_DIR = Path(__file__).resolve().parent.parent
    MODEL_NAME = "google/gemma-3-1b-it"
    MAX_INPUT_LENGTH = 512
    MAX_FIELD_OUTPUT_LENGTH = 48
    # Decoder-only models use considerably more memory per prompt than T5.
    INFERENCE_BATCH_SIZE = 1
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    UPLOAD_DIR = BASE_DIR / "uploads"
    STATIC_DIR = BASE_DIR / "static"
    MAX_UPLOAD_SIZE = 10 * 1024 * 1024
    UPLOAD_CHUNK_SIZE = 1024 * 1024
    REQUIREMENT_FORMATS = ["short", "ultra_short", "tag"]
    WHY_JOIN_FORMATS = ["short", "ultra_short"]

settings = Settings()
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

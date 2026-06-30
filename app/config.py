from pathlib import Path

import torch


class Settings:
    BASE_DIR = Path(__file__).resolve().parent.parent
    MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"
    MAX_INPUT_LENGTH = 512
    MAX_FIELD_OUTPUT_LENGTH = 48
    # Decoder-only models use considerably more memory per prompt than T5.
    INFERENCE_BATCH_SIZE = 1
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    STATIC_DIR = BASE_DIR / "static"
    MAX_URL_CONTENT_SIZE = 2 * 1024 * 1024
    URL_FETCH_TIMEOUT = 15.0
    MAX_URL_REDIRECTS = 5
    REQUIREMENT_FORMATS = ["short", "ultra_short", "tag"]
    WHY_JOIN_FORMATS = ["short", "ultra_short"]

settings = Settings()

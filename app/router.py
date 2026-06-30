import logging
import threading
import uuid
from pathlib import Path
from typing import BinaryIO, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.extractor import ALLOWED_EXTENSIONS, extract_text
from app.formatter import format_output
from app.models import OutputData, SummarizeResponse
from app.summarize import Summarizer


logger = logging.getLogger(__name__)
router = APIRouter()
summarizer: Summarizer | None = None
inference_lock = threading.Lock()


class UploadTooLargeError(ValueError):
    pass


def get_summarizer() -> Summarizer:
    global summarizer
    if summarizer is None:
        summarizer = Summarizer()
    return summarizer


def summarize_text(text: str, req_format: str, why_join_format: str) -> dict:
    # Model initialization, lock waiting, and GPU work all stay off the event loop.
    with inference_lock:
        return get_summarizer().summarize(text, req_format, why_join_format)


def save_upload(source: BinaryIO, destination: Path) -> None:
    source.seek(0)
    total = 0
    with destination.open("wb") as output:
        while chunk := source.read(settings.UPLOAD_CHUNK_SIZE):
            total += len(chunk)
            if total > settings.MAX_UPLOAD_SIZE:
                raise UploadTooLargeError(
                    f"File is too large. Maximum size is {settings.MAX_UPLOAD_SIZE // (1024 * 1024)} MB."
                )
            output.write(chunk)


@router.post("/api/upload", response_model=OutputData)
async def upload_file(
    file: UploadFile = File(...),
    req_format: Literal["short", "ultra_short", "tag"] = Form("short"),
    why_join_format: Literal["short", "ultra_short"] = Form("short"),
) -> OutputData:
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {ext or 'missing extension'}. Allowed: {allowed}",
        )

    temp_path = settings.UPLOAD_DIR / f"{uuid.uuid4()}{ext}"

    try:
        await run_in_threadpool(save_upload, file.file, temp_path)
        text = await run_in_threadpool(extract_text, str(temp_path))

        result = await run_in_threadpool(
            summarize_text,
            text,
            req_format,
            why_join_format,
        )

        normalized = SummarizeResponse.model_validate(result)
        return OutputData(
            data=normalized,
            formatted_text=format_output(normalized, req_format),
        )
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except ValidationError as exc:
        logger.error("Model output validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The model returned an invalid result.",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to process uploaded file")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The document could not be processed.",
        ) from exc
    finally:
        temp_path.unlink(missing_ok=True)
        await file.close()

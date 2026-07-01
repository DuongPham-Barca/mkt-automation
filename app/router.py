import logging
from typing import Literal

from fastapi import APIRouter, Form, HTTPException, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.formatter import format_output
from app.models import OutputData, SummarizeResponse
from app.summarize import Summarizer
from app.url_extractor import fetch_url_text


logger = logging.getLogger(__name__)
router = APIRouter()
summarizer: Summarizer | None = None


def get_summarizer() -> Summarizer:
    global summarizer
    if summarizer is None:
        summarizer = Summarizer()
    return summarizer


@router.post("/api/summarize-url", response_model=OutputData)
async def summarize_url(
    url: str = Form(...),
    req_format: Literal["short", "ultra_short", "tag"] = Form("short"),
    why_join_format: Literal["short", "ultra_short"] = Form("short"),
) -> OutputData:
    try:
        text = await run_in_threadpool(fetch_url_text, url)

        result = await run_in_threadpool(
            get_summarizer().summarize,
            text,
            req_format,
            why_join_format,
        )

        normalized = SummarizeResponse.model_validate(result)
        return OutputData(
            data=normalized,
            formatted_text=format_output(normalized, req_format),
        )
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
        logger.exception("Failed to process URL")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The URL could not be processed.",
        ) from exc

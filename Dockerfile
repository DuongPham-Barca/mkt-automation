FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --uid 1000 user
WORKDIR /home/user/app

COPY requirements-space.txt .
RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements-space.txt

COPY --chown=user:user app ./app
COPY --chown=user:user static ./static
COPY --chown=user:user main.py ./main.py

USER user
EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/healthz', timeout=3)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]

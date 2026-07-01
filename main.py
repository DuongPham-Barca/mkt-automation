import os

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.router import router
from app.config import settings

app = FastAPI(title="MKT Automation - Job Summarizer")

app.include_router(router)


@app.get("/healthz", include_in_schema=False)
async def healthcheck():
    return {"status": "ok"}


# Vercel serves public/ through its CDN. Local and Docker runs need FastAPI
# to serve the same directory, mounted after all API routes.
if not os.getenv("VERCEL"):
    app.mount(
        "/",
        StaticFiles(directory=settings.PUBLIC_DIR, html=True),
        name="public",
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

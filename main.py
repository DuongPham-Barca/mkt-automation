import os

import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.router import router
from app.config import settings

app = FastAPI(title="MKT Automation - Job Summarizer")

app.include_router(router)


@app.get("/healthz", include_in_schema=False)
async def healthcheck():
    return {"status": "ok"}


# Vercel serves public/ through its CDN but does not map / to index.html for
# FastAPI projects, so redirect the root explicitly. Local and Docker runs
# mount the directory after all API routes.
if os.getenv("VERCEL"):
    @app.get("/", include_in_schema=False)
    async def vercel_root():
        return RedirectResponse(url="/index.html")
else:
    app.mount(
        "/",
        StaticFiles(directory=settings.PUBLIC_DIR, html=True),
        name="public",
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

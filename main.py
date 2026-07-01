import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.router import router
from app.config import settings

app = FastAPI(title="MKT Automation - Job Summarizer")

app.include_router(router)


@app.get("/healthz", include_in_schema=False)
async def healthcheck():
    return {"status": "ok"}


@app.get("/")
async def root():
    return FileResponse(settings.PUBLIC_DIR / "index.html")


@app.get("/app.js", include_in_schema=False)
async def frontend_script():
    return FileResponse(settings.PUBLIC_DIR / "app.js", media_type="text/javascript")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.router import router
from app.config import settings

app = FastAPI(title="MKT Automation - Job Summarizer")

app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")
app.include_router(router)

@app.get("/")
async def root():
    return FileResponse(settings.STATIC_DIR / "index.html")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

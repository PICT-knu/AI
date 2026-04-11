from fastapi import FastAPI
from routers import resume, matching

app = FastAPI(
    title="PICT AI Server",
    description="맞춤형 취업 AI Agent — 이력서 수정 및 공고 매칭 AI 서버",
    version="0.1.0",
)

app.include_router(resume.router, prefix="/resume", tags=["resume"])
app.include_router(matching.router, prefix="/match", tags=["matching"])


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}

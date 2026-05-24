import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from routers import resume_router, matching_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    missing = [k for k in ("GROQ_API_KEY", "OPENROUTER_API_KEY") if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"필수 환경변수 없음: {', '.join(missing)}")
    yield


app = FastAPI(
    title="PICT AI Server",
    description="맞춤형 취업 AI Agent — 이력서 수정 및 공고 매칭 AI 서버",
    version="0.1.0",
    openapi_version="3.0.3",
    lifespan=lifespan,
)

app.include_router(resume_router, prefix="/resume", tags=["resume"])
app.include_router(matching_router, prefix="/match", tags=["matching"])


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}

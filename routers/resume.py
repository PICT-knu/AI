import asyncio

from fastapi import APIRouter, File, HTTPException, UploadFile

from models import (
    ResumeFixRequest, ResumeFixResponse,
    ResumeChatRequest, ResumeChatResponse,
    ResumeGenerateRequest, ResumeGenerateResponse,
    PdfExtractResponse,
    TextExtractRequest,
)
from services import fix_resume, chat_resume, generate_resume
from services.pdf_service import extract_materials_from_pdf, extract_materials_from_text

router = APIRouter()


@router.post("/fix", response_model=ResumeFixResponse)
async def resume_fix(req: ResumeFixRequest) -> ResumeFixResponse:
    """이력서 자동 생성 (Default Mode, Stateless)."""
    try:
        return await fix_resume(req.resume_materials, req.job_post)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="AI 처리 시간 초과")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat", response_model=ResumeChatResponse)
async def resume_chat(req: ResumeChatRequest) -> ResumeChatResponse:
    """챗봇 교정 모드 (Session-based). reason + suggested_body(ResumeBody) 반환."""
    try:
        return await chat_resume(
            session_id=req.session_id,
            message=req.message,
            current_body=req.current_body,
            materials=req.resume_materials,
            job_post=req.job_post,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="AI 처리 시간 초과")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate", response_model=ResumeGenerateResponse)
async def resume_generate(req: ResumeGenerateRequest) -> ResumeGenerateResponse:
    """1클릭 이력서 초안 생성. 유저 프로필 + 소재 + 공고 JD 기반 맞춤형 이력서 전문 생성."""
    try:
        return await generate_resume(req.user_profile, req.resume_materials, req.job_post)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="AI 처리 시간 초과")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/pdf/extract", response_model=PdfExtractResponse)
async def resume_pdf_extract(
    file: UploadFile = File(..., description="이력서 PDF 파일"),
) -> PdfExtractResponse:
    """PDF 이력서에서 소재 카드를 자동 추출합니다. AI 처리 실패 시 502 반환."""
    pdf_bytes = await file.read()
    filename = file.filename or "resume.pdf"
    try:
        return await extract_materials_from_pdf(pdf_bytes, filename)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/text/extract", response_model=PdfExtractResponse)
async def resume_text_extract(req: TextExtractRequest) -> PdfExtractResponse:
    """자유 형식 텍스트(Notion 페이지 본문 등)에서 소재 카드를 자동 추출합니다.
    AI 처리 실패 시 502 반환. 빈/공백 텍스트는 200 + 빈 materials 로 응답.
    """
    try:
        return await extract_materials_from_text(req.text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

from fastapi import APIRouter, HTTPException, Response

from models import (
    ResumeFixRequest, ResumeFixResponse,
    ResumeChatRequest, ResumeChatResponse,
    ResumeGenerateRequest, ResumeGenerateResponse,
)
from services import fix_resume, chat_resume, generate_resume
from services.resume_graph_service import fix_resume_graph

router = APIRouter()


@router.post("/fix", response_model=ResumeFixResponse)
async def resume_fix(req: ResumeFixRequest) -> ResumeFixResponse:
    """이력서 자동 생성 (Default Mode, Stateless)."""
    try:
        return await fix_resume(req.resume_materials, req.job_post)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat", response_model=ResumeChatResponse)
async def resume_chat(req: ResumeChatRequest, response: Response) -> ResumeChatResponse:
    """
    챗봇 교정 모드 (Session-based). session_id 없으면 새 세션 자동 생성.
    
    세션 ID를 헤더(X-Session-Id)에 중복 포함한 이유:
        1. 빠른 인식: 데이터가 길어질 경우, 본문을 다 읽기 전에 헤더만 보고 세션 식별 가능
        2. 연동 편의성: 프론트엔드 통신 라이브러리(Axios 등)에서 세션 ID를 가로채 관리하기 최적화된 구조
    """
    try:
        result = await chat_resume(
            session_id=req.session_id,
            user_message=req.user_message,
            materials=req.resume_materials,
            job_post=req.job_post,
        )
        # 클라이언트가 session_id를 헤더로도 받을 수 있도록
        response.headers["X-Session-Id"] = result.session_id
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate", response_model=ResumeGenerateResponse)
async def resume_generate(req: ResumeGenerateRequest) -> ResumeGenerateResponse:
    """1클릭 이력서 초안 생성. 유저 프로필 + 소재 + 공고 JD 기반 맞춤형 이력서 전문 생성."""
    try:
        return await generate_resume(req.user_profile, req.resume_materials, req.job_post)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fix-graph", response_model=ResumeFixResponse)
async def resume_fix_graph(req: ResumeFixRequest) -> ResumeFixResponse:
    """
    LangGraph 9단계 파이프라인 기반 이력서 생성 (성능 비교용).
    /fix와 동일한 요청/응답 스키마.
    단계: 소재 정규화 → 공고 요구사항 추출 → 소재-공고 매핑 → 구조 설계
          → 섹션별 작성 → 근거 검증 → 포맷 검증 → 실패 섹션 재작성 → 최종 반환
    """
    try:
        return await fix_resume_graph(req.resume_materials, req.job_post)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

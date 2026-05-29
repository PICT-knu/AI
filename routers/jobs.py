from fastapi import APIRouter, HTTPException

from models import JobDetailAnalysisRequest, JobDetailAnalysisResponse
from services.job_service import analyze_job_detail

router = APIRouter()


@router.post("/detail-analysis", response_model=JobDetailAnalysisResponse)
async def job_detail_analysis(req: JobDetailAnalysisRequest) -> JobDetailAnalysisResponse:
    """공고 상세 조회 페이지용 분석. description을 주요 업무/자격 요건/복지 배열로 정리해 반환.
    AI 처리 실패 시 502 반환."""
    try:
        return await analyze_job_detail(req.description)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

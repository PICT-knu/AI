from fastapi import APIRouter, HTTPException

from models import MatchRequest, MatchResponse
from services.matching_service import top10_matching

router = APIRouter()


@router.post("/top10", response_model=MatchResponse)
async def match_top10(req: MatchRequest) -> MatchResponse: #입력 규격 및 반환규격 정의
    """공고 TOP 10 추천. resume_materials와 job_posts 기반으로 적합도 점수 계산 후 상위 10개 반환."""
    try:
        return await top10_matching(req.resume_materials, req.job_posts)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

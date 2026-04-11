from pydantic import BaseModel, Field
from models.resume import ResumeMaterial, JobPost

# 매칭 input
class MatchRequest(BaseModel):
    resume_materials: list[ResumeMaterial] = Field(description="이력서 소재가 담긴 리스트")
    job_posts: list[JobPost] = Field(description="공고가 담긴 리스트")

# AI가 반환하는 매칭 결과 양식
class Recommendation(BaseModel):
    job_id: str = Field(description="채용공고 고유 ID")
    match_score: float = Field(description="매칭 점수 (0~100)")
    reason_text: str = Field(description="AI의 근거 설명 (예: \"경력:90, 기술스택:80, 복지:75\")")
    #매칭 근거가 필요할까? 어차피 카드 형식으로 출력될텐데

# AI서버가 최종 반환하는 응답 양식
class MatchResponse(BaseModel):
    recommendations: list[Recommendation] = Field(description="여러 공고에 대한 추천 결과를 리스트로 묶어 반환")

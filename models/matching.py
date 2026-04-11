from pydantic import BaseModel, Field
from models.resume import ResumeMaterial

#매칭용 채용공고 데이터
class JobPostForMatch(BaseModel):
    job_id: str = Field(description="채용공고 고유 ID")
    description: str = Field(description="채용공고 상세 설명") 
    experience_text: str = Field(description="요구 경력") 
    education_text: str = Field(description="요구 학력")
    employment_type: str = Field(description="고용 형태 (예: 정규직, 계약직)")

#서버로 전달되는 매칭 데이터 양식
class MatchRequest(BaseModel):
    resume_materials: list[ResumeMaterial] = Field(description="이력서 소재가 담긴 리스트")
    job_posts: list[JobPostForMatch] = Field(description="공고가 담긴 리스트")

# AI가 반환하는 매칭 결과 양식
class Recommendation(BaseModel):
    job_id: str = Field(description="채용공고 고유 ID")
    match_score: float = Field(description="매칭 점수 (0~100)")
    reason_text: str = Field(description="AI의 근거 설명 (예: \"경력:90, 기술스택:80, 복지:75\")")
    # 근거 설명이 필요한가? 어차피 카드 형태로 보여줄 건데, 점수만 있으면 되지 않을까?

# AI서버가 최종 반환하는 응답 양식
class MatchResponse(BaseModel):
    recommendations: list[Recommendation] = Field(description="여러 공고에 대한 추천 결과를 리스트로 묶어 반환")
    #공고별로 매칭 점수와 설명을 주는 것보단 이쪽에서 top-10을 가져다 주는편이 편할지도
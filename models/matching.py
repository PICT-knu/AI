from typing import Optional
from pydantic import BaseModel, Field
from models.resume import ResumeMaterial, JobPost


class UserPreferences(BaseModel):
    # 피하고 싶어요
    avoidance_options: list[str] = Field(default_factory=list, description="고정 선택지 목록 (예: '계약직 제외')")
    avoidance_cert_text: str = Field(default="", description="제외할 자격증 (자유 텍스트, 예: '정보처리기사')")
    avoidance_skill_text: str = Field(default="", description="제외할 기술스택 (자유 텍스트, 예: 'React')")

    # 선호 조건 (스코어링 반영)
    preferred_locations: list[str] = Field(default_factory=list, description="희망 근무지역 목록 (예: ['서울 강남구'])")
    experience_level: str = Field(default="", description="경력 단계 (예: '신입', '1-3년')")
    preferred_job_rank: str = Field(default="", description="희망 직급 (예: '신입', '주니어')")
    preferred_company_sizes: list[str] = Field(default_factory=list, description="선호 기업 규모 목록")
    preferred_benefits: list[str] = Field(default_factory=list, description="선호 복리후생 목록")


class MatchRequest(BaseModel):
    resume_materials: list[ResumeMaterial] = Field(description="이력서 소재가 담긴 리스트")
    job_posts: list[JobPost] = Field(description="공고가 담긴 리스트")
    user_preferences: UserPreferences = Field(default_factory=UserPreferences, description="사용자 선호/기피 조건")


class Recommendation(BaseModel):
    job_posting_id: Optional[int] = Field(default=None, description="채용공고 PK (BE1 DB)")
    job_id: Optional[str] = Field(default=None, description="채용공고 고유 ID (하위 호환)")
    match_score: float = Field(description="매칭 점수 (0~100)")
    reason_text: str = Field(description="AI의 근거 설명 (예: '경력:90, 기술스택:80, 복지:75')")


class MatchResponse(BaseModel):
    recommendations: list[Recommendation] = Field(description="여러 공고에 대한 추천 결과를 리스트로 묶어 반환")

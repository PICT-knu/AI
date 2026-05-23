from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class ResumeMaterial(BaseModel):
    material_type: str = Field(description="소재 유형 (예: EXPERIENCE, PROJECT, SKILL)")
    title: Optional[str] = Field(default=None, description="소재 제목")
    content: str = Field(description="소재 내용")
    summary: Optional[str] = Field(default=None, description="소재 요약")
    material_id: Optional[str] = Field(description="소재 고유 ID", default=None)


class JobPost(BaseModel):
    job_id: Optional[str] = Field(default=None, description="채용공고 고유 ID (하위 호환)")
    job_posting_id: Optional[int] = Field(default=None, description="채용공고 PK (BE1 DB)")
    company_name: Optional[str] = Field(default=None, description="회사명")
    title: Optional[str] = Field(default=None, description="공고 제목")
    description: str = Field(description="채용공고 상세 설명")
    experience_text: str = Field(description="요구 경력")
    education_text: str = Field(description="요구 학력")
    employment_type: str = Field(description="고용 형태 (예: 정규직, 계약직)")
    location: Optional[str] = Field(default=None, description="근무지 (예: 서울 강남구)")


class ResumeExperience(BaseModel):
    company: Optional[str] = None
    period: Optional[str] = None
    role: Optional[str] = None
    description: Optional[str] = None


class ResumeBody(BaseModel):
    about: Optional[str] = None
    experience: list[ResumeExperience] = []
    skills: list[str] = []


class ResumeVersion(BaseModel):
    type: str = Field(description='"JOB_FIT" | "ACHIEVEMENT"')
    body: ResumeBody
    matching_score: int = Field(description="0~100")
    summary: str


class ResumeFixRequest(BaseModel):
    member_id: Optional[int] = Field(default=None, description="회원 PK (BE1)")
    job_posting_id: Optional[int] = Field(default=None, description="공고 PK (BE1)")
    resume_materials: list[ResumeMaterial]
    job_post: JobPost


class ResumeFixResponse(BaseModel):
    generated_at: str = Field(description="생성 시각 (ISO 8601)")
    recommended_type: str = Field(description='"JOB_FIT" | "ACHIEVEMENT"')
    versions: list[ResumeVersion] = Field(description="항상 2개 (JOB_FIT, ACHIEVEMENT)")


class ResumeChatRequest(BaseModel):
    session_id: Optional[str] = Field(default=None, description="세션 ID (BE1 제공 숫자 문자열 또는 없음)")
    tailored_resume_id: Optional[int] = Field(default=None, description="tailored_resume PK (BE1)")
    message: str = Field(description="사용자 메시지")
    current_body: Optional[dict] = Field(default=None, description="현재 이력서 body (ResumeBody 구조, BE1 확인 후 Optional[ResumeBody]로 교체 예정)")
    resume_materials: list[ResumeMaterial]
    job_post: Optional[JobPost] = Field(default=None)


class ResumeChatResponse(BaseModel):
    reason: str = Field(description="수정 이유 (255자 이하, BE1 DB 컬럼 길이 제한)")
    suggested_body: ResumeBody


class UserProfile(BaseModel):
    career_level: str = Field(default="", description="경력 단계 (예: '신입', '1-3년')")
    degree_type: str = Field(default="", description="대학 유형 (예: '4년제', '2/3년제')")
    graduation_status: str = Field(default="", description="졸업 여부 (예: '졸업', '재학중', '졸업예정')")
    school_name: str = Field(default="", description="학교명 (예: '국립공주대학교')")
    major: str = Field(default="", description="전공 (예: '컴퓨터공학')")
    enrollment_year: str = Field(default="", description="입학년도 (예: '2022')")
    graduation_year: str = Field(default="", description="졸업년도 (예: '2026')")


class ResumeGenerateRequest(BaseModel):
    user_profile: UserProfile = Field(default_factory=UserProfile)
    resume_materials: list[ResumeMaterial]
    job_post: JobPost


class ResumeGenerateResponse(BaseModel):
    generated_resume: str = Field(description="AI가 생성한 이력서 초안 전문")

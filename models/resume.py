from typing import Optional
from pydantic import BaseModel, Field

# 이력서 소재 데이터 양식
class ResumeMaterial(BaseModel):
    material_type: str = Field(description="소재 유형 (예: 경력, 프로젝트, 기술)")
    content: str = Field(description="소재 내용")
    material_id: Optional[str] = Field(description="소재 고유 ID", default=None)
    # 임시 데이터 사용을 대비해 material_id를 Optional로 설정

# 채용공고 데이터 양식
class JobPost(BaseModel):
    job_id: Optional[str] = Field(description="채용공고 고유 ID (매칭 시 사용, 이력서 수정 시 생략 가능)", default=None)
    description: str = Field(description="채용공고 상세 설명")
    experience_text: str = Field(description="요구 경력")
    education_text: str = Field(description="요구 학력")
    employment_type: str = Field(description="고용 형태 (예: 정규직, 계약직)")
    location: Optional[str] = Field(description="근무지 (예: 서울 강남구)", default=None)

# 이력서 수정 요청 양식
class ResumeFixRequest(BaseModel):
    resume_materials: list[ResumeMaterial] = Field(description="이력서 소재가 담긴 리스트") #소재뿐인 이유는 사용자가 넣은 이력서 원본도 소재 목록에 넣기 때문
    job_post: JobPost = Field(description="지원할 채용공고 정보")
    # 이력서 원본을 소재로 할지, 아니면 별도로 할지 논의 필요
    # 이력서 원본 및 소재들을 원자화 할지 아니면 그냥 텍스트로 넘길지 논의 필요

# 이력서 수정 응답 양식
class ResumeFixResponse(BaseModel):
    revised_resume: str = Field(description="AI가 수정한 이력서 텍스트 전문")

# 이력서 수정 제안 양식
class ResumeChatRequest(BaseModel):
    session_id: Optional[str] = Field(description="세션 ID", default=None)
    user_message: str = Field(description="사용자 메시지")
    resume_materials: list[ResumeMaterial] = Field(description="이력서 소재가 담긴 리스트")
    job_post: Optional[JobPost] = Field(description="지원할 채용공고 정보", default=None)

# 이력서 수정 제안 응답 양식
class ChangeItem(BaseModel):
    original: str = Field(description="수정 전 내용")
    suggested: str = Field(description="수정 후 내용")
    reason: str = Field(description="수정 이유")
    material_id: Optional[str] = Field(description="소재 고유 ID", default=None)

# 이력서 수정 제안 서버 응답 양식
class ResumeChatResponse(BaseModel):
    session_id: str = Field(description="세션 ID")
    changes: list[ChangeItem] = Field(description="수정 제안 목록")

class UserProfile(BaseModel):
    career_level: str = Field(default="", description="경력 단계 (예: '신입', '1-3년')")
    degree_type: str = Field(default="", description="대학 유형 (예: '4년제', '2/3년제')")
    graduation_status: str = Field(default="", description="졸업 여부 (예: '졸업', '재학중', '졸업예정')")
    school_name: str = Field(default="", description="학교명 (예: '국립공주대학교')")
    major: str = Field(default="", description="전공 (예: '컴퓨터공학')")
    enrollment_year: str = Field(default="", description="입학년도 (예: '2022')")
    graduation_year: str = Field(default="", description="졸업년도 (예: '2026')")


# 1클릭 이력서 초안 생성 요청 양식
class ResumeGenerateRequest(BaseModel):
    user_profile: UserProfile = Field(default_factory=UserProfile, description="유저 기본 프로필 (학력, 경력 단계 등)")
    resume_materials: list[ResumeMaterial] = Field(description="이력서 소재가 담긴 리스트")
    job_post: JobPost = Field(description="지원할 채용공고 정보")

# 1클릭 이력서 초안 생성 응답 양식
class ResumeGenerateResponse(BaseModel):
    generated_resume: str = Field(description="AI가 생성한 이력서 초안 전문")

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

from typing import Optional
from pydantic import BaseModel, Field


class JobDetailAnalysisRequest(BaseModel):
    job_posting_id: Optional[int] = Field(default=None, description="채용공고 PK (BE1 DB)")
    company_name: Optional[str] = Field(default=None, description="회사명")
    title: Optional[str] = Field(default=None, description="공고 제목")
    description: str = Field(min_length=1, description="채용공고 원문 (메인 분석 대상)")


class JobDetailAnalysisResponse(BaseModel):
    main_tasks: list[str] = Field(default_factory=list, description="담당할 주요 업무를 한 문장 단위로 정리")
    qualifications: list[str] = Field(default_factory=list, description="지원자에게 요구되는 자격 요건을 한 문장 단위로 정리")
    benefits: list[str] = Field(default_factory=list, description="복지 및 혜택을 한 문장 단위로 정리")

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class MaterialType(str, Enum):
    EXPERIENCE = "경력"
    PROJECT = "프로젝트"
    SKILL = "기술스택"
    EDUCATION = "교육"
    OTHER = "기타"


class ExtractedMaterial(BaseModel):
    title: str = Field(description="소재 제목 (30자 이내 권장)")
    summary: Optional[str] = Field(default=None, description="소재 요약 (100자 이내 권장)")
    material_type: MaterialType


class PdfExtractResponse(BaseModel):
    materials: list[ExtractedMaterial]


class ManualExtractedMaterial(BaseModel):
    title: str = Field(description="소재 제목 (30자 이내 권장)")
    content: str = Field(description="해당 소재에 해당하는 원문 발췌")
    summary: Optional[str] = Field(default=None, description="소재 요약 (100자 이내 권장)")
    material_type: MaterialType


class ManualExtractResponse(BaseModel):
    materials: list[ManualExtractedMaterial]


class TextExtractRequest(BaseModel):
    text: str = Field(description="이력서 소재 추출 대상 텍스트 (Notion 페이지 본문 등 자유 형식)")

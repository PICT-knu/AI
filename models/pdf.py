from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class MaterialType(str, Enum):
    EXPERIENCE = "EXPERIENCE"
    PROJECT = "PROJECT"
    SKILL = "SKILL"
    EDUCATION = "EDUCATION"
    OTHER = "OTHER"


class ExtractedMaterial(BaseModel):
    title: str = Field(description="소재 제목 (30자 이내 권장)")
    summary: Optional[str] = Field(default=None, description="소재 요약 (100자 이내 권장)")
    material_type: MaterialType


class PdfExtractResponse(BaseModel):
    materials: list[ExtractedMaterial]

from typing import Optional
from pydantic import BaseModel


class ResumeMaterial(BaseModel):
    material_type: str  # "experience" | "project" | "skill" 등
    content: str
    material_id: Optional[str] = None


class JobPost(BaseModel):
    description: str
    experience_text: str
    education_text: str
    employment_type: str


class ResumeFixRequest(BaseModel):
    resume_materials: list[ResumeMaterial]
    job_post: JobPost


class ResumeFixResponse(BaseModel):
    revised_resume: str


class ResumeChatRequest(BaseModel):
    session_id: Optional[str] = None
    user_message: str
    resume_materials: list[ResumeMaterial]
    job_post: Optional[JobPost] = None


class ChangeItem(BaseModel):
    original: str
    suggested: str
    reason: str
    material_id: Optional[str] = None


class ResumeChatResponse(BaseModel):
    session_id: str
    changes: list[ChangeItem]

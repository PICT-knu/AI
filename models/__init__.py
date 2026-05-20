from .resume import (
    ResumeMaterial,
    JobPost,
    UserProfile,
    ResumeFixRequest,
    ResumeFixResponse,
    ResumeChatRequest,
    ResumeChatResponse,
    ChangeItem,
    ResumeGenerateRequest,
    ResumeGenerateResponse,
)

from .matching import (
    MatchRequest,
    MatchResponse,
    Recommendation,
    UserPreferences,
)

from .pdf import (
    MaterialType,
    ExtractedMaterial,
    PdfExtractResponse,
    ManualExtractedMaterial,
    ManualExtractResponse,
    TextExtractRequest,
)
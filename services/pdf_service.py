import base64
import json
import os

import httpx

from models.pdf import PdfExtractResponse

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM_PROMPT = """당신은 이력서 소재 추출 전문 AI입니다.
첨부된 PDF 이력서를 분석하여 아래 규칙에 따라 소재를 추출하십시오.

[소재 유형]
- EXPERIENCE: 직장 경력, 인턴십 등 실제 근무 이력
- PROJECT: 팀/개인 프로젝트, 오픈소스 기여 등 작업 결과물
- SKILL: 프로그래밍 언어, 프레임워크, 자격증, 어학 능력 등 보유 역량
- EDUCATION: 학력 (학교, 전공, 수료 과정)
- OTHER: 수상 이력, 봉사활동 등 기타

[규칙]
1. PDF에 명시된 내용만 추출하고 내용을 지어내지 마십시오.
2. 각 소재는 독립 항목(경력 1건, 프로젝트 1건 등) 단위로 분리하십시오.
3. title은 30자 이내 간결한 제목으로 작성하십시오.
4. summary는 핵심 내용 2~4문장 요약 또는 null로 작성하십시오.
5. 소재가 전혀 없으면 materials를 빈 배열로 반환하십시오."""


# Notion 본문 등 자유 형식 텍스트용. PDF 프롬프트와 동일하나 두 가지 차이:
#   (1) "첨부된 PDF" → "아래 텍스트"
#   (2) 본인 작업/역량으로 단정할 수 있을 때만 추출하라는 규칙 추가 — 회의록/피드백/코드 덤프/
#       자격 증명 정보 같은 페이지에서 무리하게 소재를 만들어내지 않도록 가드.
_SYSTEM_PROMPT_TEXT = """당신은 이력서 소재 추출 전문 AI입니다.
아래 텍스트(Notion 페이지 본문 등 자유 형식)를 분석하여 아래 규칙에 따라 소재를 추출하십시오.

[소재 유형]
- EXPERIENCE: 직장 경력, 인턴십 등 실제 근무 이력
- PROJECT: 팀/개인 프로젝트, 오픈소스 기여 등 작업 결과물
- SKILL: 프로그래밍 언어, 프레임워크, 자격증, 어학 능력 등 보유 역량
- EDUCATION: 학력 (학교, 전공, 수료 과정)
- OTHER: 수상 이력, 봉사활동 등 기타

[규칙]
1. 텍스트에 명시된 내용만 추출하고 내용을 지어내지 마십시오.
2. 본인이 직접 한 일 또는 보유 역량으로 단정할 수 있을 때만 추출하십시오.
   회의록, 받은 피드백, 타인 발언, 코드/설정 덤프, 계정/키 같은 자격 증명, 단순 일정·일지 등은
   소재로 보지 말고 materials 를 빈 배열로 반환하십시오.
3. 각 소재는 독립 항목(경력 1건, 프로젝트 1건 등) 단위로 분리하십시오.
4. title은 30자 이내 간결한 제목으로 작성하십시오.
5. summary는 핵심 내용 2~4문장 요약 또는 null로 작성하십시오.
6. 소재가 전혀 없으면 materials를 빈 배열로 반환하십시오."""

_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "pdf_extract_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "materials": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "summary": {"type": ["string", "null"]},
                            "material_type": {
                                "type": "string",
                                "enum": ["EXPERIENCE", "PROJECT", "SKILL", "EDUCATION", "OTHER"],
                            },
                        },
                        "required": ["title", "summary", "material_type"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["materials"],
            "additionalProperties": False,
        },
    },
}


async def extract_materials_from_pdf(pdf_bytes: bytes, filename: str) -> PdfExtractResponse:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY가 설정되지 않았습니다.")

    model = (
        os.getenv("PDF_EXTRACT_MODEL")
        or os.getenv("OPENROUTER_MODEL", "anthropic/claude-opus-4")
    )
    safe_name = filename if filename.lower().endswith(".pdf") else filename + ".pdf"
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {
                            "filename": safe_name,
                            "file_data": f"data:application/pdf;base64,{b64}",
                        },
                    },
                    {"type": "text", "text": "위 PDF 이력서에서 소재를 추출해 주십시오."},
                ],
            },
        ],
        "plugins": [{"id": "file-parser", "pdf": {"engine": "native"}}],
        "response_format": _JSON_SCHEMA,
        "temperature": 0.1,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            _OPENROUTER_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()

    raw = resp.json()["choices"][0]["message"]["content"]
    parsed = raw if isinstance(raw, dict) else json.loads(raw)
    return PdfExtractResponse.model_validate(parsed)


async def extract_materials_from_text(text: str) -> PdfExtractResponse:
    """자유 형식 텍스트(Notion 페이지 본문 등)에서 소재를 추출.

    PDF 흐름과 동일하게 OpenRouter 호출 + JSON Schema 강제. 차이점은 file/file-parser 플러그인을
    쓰지 않고 단순 text content 로 보낸다는 점과 빈/공백 입력은 LLM 호출 없이 빈 결과를 돌려준다는
    점. 응답 모델은 PDF 흐름과 동일한 PdfExtractResponse 를 재사용한다.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY가 설정되지 않았습니다.")

    if not text or not text.strip():
        return PdfExtractResponse(materials=[])

    # Notion 본문 등 외부 원본을 그대로 받기 때문에 lone surrogate / 잘린 UTF-8 시퀀스가 섞일 수 있다.
    # httpx 가 OpenRouter 로 json.dumps 시 surrogates not allowed 로 터지므로 한 번 정리해서 안전화.
    text = text.encode("utf-8", errors="ignore").decode("utf-8")

    model = (
        os.getenv("TEXT_EXTRACT_MODEL")
        or os.getenv("PDF_EXTRACT_MODEL")
        or os.getenv("OPENROUTER_MODEL", "anthropic/claude-opus-4")
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT_TEXT},
            {"role": "user", "content": text},
        ],
        "response_format": _JSON_SCHEMA,
        "temperature": 0.1,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            _OPENROUTER_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()

    raw = resp.json()["choices"][0]["message"]["content"]
    parsed = raw if isinstance(raw, dict) else json.loads(raw)
    return PdfExtractResponse.model_validate(parsed)

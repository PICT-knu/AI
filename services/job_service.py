import json
import os

import httpx

from models.job import JobDetailAnalysisResponse

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM_PROMPT = """당신은 채용 공고 분석 전문 AI입니다.
아래 채용 공고 원문을 분석하여 세 가지 항목으로 정리하십시오.

[추출 항목]
- main_tasks: 입사 후 담당하게 될 주요 업무
- qualifications: 지원자에게 요구되는 자격 요건
- benefits: 복지 및 혜택

[규칙]
1. 공고에 명시된 내용만 추출하고 내용을 지어내지 마십시오.
2. 각 항목은 한 문장 단위로 간결하게 정리하십시오.
3. 각 항목 배열은 핵심 위주로 최대 6개까지만 작성하십시오.
4. 해당 정보가 공고에 없으면 빈 배열로 반환하십시오.
5. 한국어로 작성하십시오."""

_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "job_detail_analysis",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "main_tasks": {"type": "array", "items": {"type": "string"}},
                "qualifications": {"type": "array", "items": {"type": "string"}},
                "benefits": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["main_tasks", "qualifications", "benefits"],
            "additionalProperties": False,
        },
    },
}


async def analyze_job_detail(description: str) -> JobDetailAnalysisResponse:
    """채용 공고 원문(description)을 분석해 주요 업무/자격 요건/복지를 섹션별 배열로 추출.

    OpenRouter JSON Schema strict 모드로 구조화 출력을 강제한다(pdf_service 흐름과 동일).
    공백뿐인 입력은 LLM 호출 없이 빈 결과를 돌려준다.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY가 설정되지 않았습니다.")

    if not description or not description.strip():
        return JobDetailAnalysisResponse()

    # BE1이 전달한 외부 원본 텍스트에 lone surrogate / 잘린 UTF-8 시퀀스가 섞이면
    # httpx 의 json.dumps 단계에서 터지므로 한 번 정리한다.
    description = description.encode("utf-8", errors="ignore").decode("utf-8")

    model = (
        os.getenv("JOB_ANALYSIS_MODEL")
        or os.getenv("OPENROUTER_MODEL", "anthropic/claude-opus-4")
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": description},
        ],
        "response_format": _JSON_SCHEMA,
        "temperature": 0.2,
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
    if not raw:
        raise ValueError(f"OpenRouter returned empty content (model={model})")
    parsed = raw if isinstance(raw, dict) else json.loads(raw)
    return JobDetailAnalysisResponse.model_validate(parsed)

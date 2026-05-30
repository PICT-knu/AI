import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from models.job import JobDetailAnalysisResponse
from services.llm_client import get_llm_client

logger = logging.getLogger(__name__)

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
5. 한국어로 작성하십시오.

[출력 형식 — 반드시 준수]
JSON 객체만 출력하라. 다른 텍스트 없음:
{"main_tasks": ["..."], "qualifications": ["..."], "benefits": ["..."]}"""


async def analyze_job_detail(description: str) -> JobDetailAnalysisResponse:
    """채용 공고 원문(description)을 분석해 주요 업무/자격 요건/복지를 섹션별 배열로 추출. Groq 사용."""
    if not description or not description.strip():
        return JobDetailAnalysisResponse()

    description = description.encode("utf-8", errors="ignore").decode("utf-8")

    llm = get_llm_client(temperature=0.2).bind(
        response_format={"type": "json_object"}
    )

    try:
        resp = await llm.ainvoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=description),
        ])
    except Exception as e:
        logger.error("공고 분석 Groq 오류: %s", e)
        raise

    try:
        parsed = json.loads(resp.content)
        return JobDetailAnalysisResponse.model_validate(parsed)
    except Exception as e:
        logger.error("공고 분석 JSON 파싱 오류: %s | 응답: %s", e, resp.content[:200])
        return JobDetailAnalysisResponse()

import json
import re
from langchain_core.messages import HumanMessage, SystemMessage

from models.resume import ResumeMaterial, JobPost
from models.matching import MatchResponse, Recommendation
from services.llm_client import get_llm_client
from utils.fact_check import build_context_block


def _build_matching_system_prompt(materials: list[ResumeMaterial]) -> str:
    context = build_context_block(materials)
    return f"""당신은 채용 공고 매칭 전문 AI입니다.
지원자의 이력 소재를 분석하여 제공된 공고들과의 적합도를 평가하십시오.

{context}

평가 기준:
- 경력: 공고의 경력 조건과 지원자 경험 일치도
- 기술스택: 공고 요구 기술과 지원자 보유 기술 일치도
- 학력/기타: 공고 학력 조건, 고용 형태 적합도

응답은 반드시 다음 JSON 형식으로만 반환하십시오:
{{
  "recommendations": [
    {{
      "job_id": "공고 ID",
      "match_score": 87.50,
      "reason_text": "경력:90, 기술스택:80, 복지:75"
    }}
  ]
}}

match_score는 0~100 사이의 소수점 2자리 숫자입니다.
상위 10개 공고만 반환하고, match_score 내림차순으로 정렬하십시오."""


def _format_job_posts(job_posts: list[JobPost]) -> str:
    lines = ["[평가 대상 채용 공고 목록]"]
    for jp in job_posts:
        lines.append(f"\n## job_id: {jp.job_id}")
        lines.append(f"- 공고 설명: {jp.description}")
        lines.append(f"- 경력 조건: {jp.experience_text}")
        lines.append(f"- 학력 조건: {jp.education_text}")
        lines.append(f"- 고용 형태: {jp.employment_type}")
    return "\n".join(lines)


def _parse_recommendations(text: str) -> list[Recommendation]:
    clean = re.sub(r"```(?:json)?", "", text).strip().rstrip("```").strip()

    try:
        data = json.loads(clean)
        raw_recs = data.get("recommendations", [])
    except (json.JSONDecodeError, AttributeError):
        return []

    result = []
    for item in raw_recs:
        try:
            result.append(
                Recommendation(
                    job_id=str(item["job_id"]),
                    match_score=float(item["match_score"]),
                    reason_text=str(item["reason_text"]),
                )
            )
        except (KeyError, ValueError):
            continue
    return result


async def top10_matching(
    materials: list[ResumeMaterial],
    job_posts: list[JobPost],
) -> MatchResponse:
    """공고 TOP 10 추천 (Stateless). temperature: 0.2."""
    llm = get_llm_client(temperature=0.2)
    system_prompt = _build_matching_system_prompt(materials)
    job_posts_text = _format_job_posts(job_posts)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=f"{job_posts_text}\n\n위 공고들을 지원자 소재와 비교하여 적합도를 평가하고 상위 10개를 JSON으로 반환하십시오."
        ),
    ]

    response = await llm.ainvoke(messages)
    recommendations = _parse_recommendations(response.content)
    return MatchResponse(recommendations=recommendations)

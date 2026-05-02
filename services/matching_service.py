import json
import re
import logging
from langchain_core.messages import HumanMessage, SystemMessage

from models import ResumeMaterial, JobPost, MatchResponse, Recommendation
from services.llm_client import get_llm_client
from utils.fact_check import build_context_block

logger = logging.getLogger(__name__)

BATCH_SIZE = 10  # 배치당 공고 수


def _chunk(lst: list, size: int):
    """리스트를 size개씩 나누는 제너레이터."""
    for i in range(0, len(lst), size):
        yield lst[i : i + size]

# AI에게 점수 계산을 요청하는 프롬프트 생성
def _build_score_prompt(materials: list[ResumeMaterial]) -> str:
    context = build_context_block(materials)
    return f"""당신은 채용 공고 적합도 평가 AI입니다.
지원자의 이력 소재를 기반으로 각 채용 공고에 대한 적합도 점수를 계산하십시오.

{context}

평가 기준:
- 경력: 공고의 경력 조건과 지원자 경험 일치도
- 기술스택: 공고 요구 기술과 지원자 보유 기술 일치도
- 학력/기타: 공고 학력 조건, 고용 형태 적합도

[출력 규칙 — 반드시 준수]
- JSON 배열 하나만 출력한다. 다른 텍스트나 마크다운을 포함하지 않는다.
- 첫 글자는 반드시 [ 이고 마지막 글자는 반드시 ] 이다.
- 전달된 모든 공고에 대해 빠짐없이 점수를 계산한다. Top N 선택은 하지 않는다.
- 스키마: [{{"job_id": "공고 ID", "match_score": 87.50, "reason_text": "경력:90, 기술스택:80, 복지:75"}}]
- match_score는 0~100 사이 소수점 2자리 숫자이다."""

# AI가 읽기 좋은 형태로 배치 포맷팅
def _format_batch(batch: list[JobPost]) -> str:
    lines = ["[평가 대상 채용 공고]"]
    for jp in batch:
        lines.append(f"\n## job_id: {jp.job_id}")
        lines.append(f"- 공고 설명: {jp.description}")
        lines.append(f"- 경력 조건: {jp.experience_text}")
        lines.append(f"- 학력 조건: {jp.education_text}")
        lines.append(f"- 고용 형태: {jp.employment_type}")
    return "\n".join(lines)


def _parse_scores(text: str) -> list[Recommendation]:
    """AI 응답에서 JSON 배열을 추출해 Recommendation 리스트로 변환."""
    # 코드 블록 안의 배열[] 우선 추출
    code_block = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if code_block:
        candidate = code_block.group(1)
    else:
        # 첫 [ ~ 마지막 ] 슬라이싱
        start = text.find("[")
        end = text.rfind("]")
        candidate = text[start : end + 1] if start != -1 and end > start else text

    try:
        raw = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return []

    result = []
    for item in raw:
        try:
            result.append(
                Recommendation(
                    job_id=str(item["job_id"]),
                    match_score=float(item["match_score"]),
                    reason_text=str(item.get("reason_text", "")),
                )
            )
        except (KeyError, ValueError):
            continue
    return result

# 공고 배치를 AI에게 전달하여 점수를 산출하고, 실패 시 빈 리스트를 반환
async def _score_batch(
    batch: list[JobPost],
    materials: list[ResumeMaterial],
    llm,
) -> list[Recommendation]:
    """
    배치 하나를 AI에 전달해 점수를 받아온다.
    실패 시 빈 리스트를 반환하여 전체 프로세스가 중단되지 않도록 한다.
    """
    try:
        batch_text = _format_batch(batch)
        messages = [
            SystemMessage(content=_build_score_prompt(materials)),
            HumanMessage(
                content=f"{batch_text}\n\n위 공고들의 적합도 점수를 JSON 배열로 반환하십시오."
            ),
        ]
        response = await llm.ainvoke(messages)
        return _parse_scores(response.content)
    except Exception as e:
        logger.warning("배치 처리 실패 (건너뜀): %s", e)
        return []


async def top10_matching(
    materials: list[ResumeMaterial],
    job_posts: list[JobPost],
) -> MatchResponse:
    """
    전체 공고를 BATCH_SIZE개씩 나누어 AI에게 점수를 받고,
    Python에서 정렬 후 상위 10개를 반환한다.
    temperature: 0.1 (점수 계산 — 낮은 창의성 필요)
    """
    llm = get_llm_client(temperature=0.1)
    all_scores: list[Recommendation] = []

    for batch in _chunk(job_posts, BATCH_SIZE):
        scores = await _score_batch(batch, materials, llm)
        all_scores.extend(scores)

    top10 = sorted(all_scores, key=lambda r: r.match_score, reverse=True)[:10]
    return MatchResponse(recommendations=top10)

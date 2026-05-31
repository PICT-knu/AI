import asyncio
import json
import logging
import os
import re

import numpy as np
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import OpenAIEmbeddings

from models import ResumeMaterial, JobPost, MatchResponse, Recommendation
from models.matching import UserPreferences
from services.llm_client import get_llm_client
from utils.fact_check import build_context_block

logger = logging.getLogger(__name__)

BATCH_SIZE = 10
_LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT_SECONDS", "90"))

# 피하고 싶어요 고정 선택지 → 검사 키워드 매핑
AVOIDANCE_KEYWORD_MAP: dict[str, list[str]] = {
    "계약직 제외":         ["계약직"],
    "경력직만 채용 제외":  ["경력직만", "경력자만"],
    "주말 근무 제외":      ["주말근무", "주말 근무"],
    "교대/야간 근무 제외": ["교대근무", "야간근무", "교대", "야간"],
    "잦은 출장 제외":      ["출장"],
    "포트폴리오 필수 제외": ["포트폴리오"],
    "사전 과제 있음 제외": ["사전과제", "사전 과제"],
    "고객 응대 중심 제외": ["고객응대", "고객 응대"],
}


def _chunk(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i: i + size]


def _pre_filter(
    job_posts: list[JobPost],
    pref: UserPreferences,
    apply_location: bool = True,
) -> list[JobPost]:
    """
    1. 고정 선택지 → AVOIDANCE_KEYWORD_MAP 키워드로 공고 본문 검사
    2. 자유 텍스트(cert/skill) → description 직접 검색
    3. apply_location=True이면 preferred_locations로 location 필터
    검사 대상: description + title + employment_type 합친 텍스트
    """
    # 피하고 싶어요 고정 선택지에서 검사 키워드 수집
    avoidance_keywords: list[str] = []
    for option in pref.avoidance_options:
        avoidance_keywords.extend(AVOIDANCE_KEYWORD_MAP.get(option, []))

    result = []
    for jp in job_posts:
        search_text = f"{jp.description} {jp.employment_type}".lower()

        # 고정 선택지 키워드 필터
        if any(kw in search_text for kw in avoidance_keywords):
            continue

        # 자유 텍스트 필터 (자격증)
        if pref.avoidance_cert_text and pref.avoidance_cert_text.lower() in search_text:
            continue

        # 자유 텍스트 필터 (기술스택)
        if pref.avoidance_skill_text and pref.avoidance_skill_text.lower() in search_text:
            continue

        # 지역 필터
        if apply_location and pref.preferred_locations:
            loc = (jp.location or "").strip()
            if not any(preferred in loc for preferred in pref.preferred_locations):
                continue

        result.append(jp)

    return result


async def _embedding_filter(
    materials: list[ResumeMaterial],
    job_posts: list[JobPost],
    top_n: int = 25,
) -> list[JobPost]:
    """OpenRouter 임베딩 API로 resume_materials와 코사인 유사도 top-N 공고 추출."""
    if not job_posts:
        return []

    embedder = OpenAIEmbeddings(
        model="openai/text-embedding-3-small",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
    )

    user_text = " ".join(m.content for m in materials)
    job_texts = [
        f"{jp.description} {jp.experience_text} {jp.employment_type}"
        for jp in job_posts
    ]

    all_embs = await embedder.aembed_documents([user_text] + job_texts)
    user_emb = np.array(all_embs[0])
    job_embs = np.array(all_embs[1:])

    norms = np.linalg.norm(job_embs, axis=1) * np.linalg.norm(user_emb)
    # 분모가 0인 경우 0으로 처리
    sims = np.where(norms > 0, np.dot(job_embs, user_emb) / norms, 0.0)

    top_idx = np.argsort(sims)[::-1][:top_n]
    return [job_posts[int(i)] for i in top_idx]


def _build_score_prompt(
    materials: list[ResumeMaterial],
    pref: UserPreferences | None = None,
) -> str:
    context = build_context_block(materials)
    pref_section = ""
    if pref:
        parts = []
        if pref.experience_level:
            parts.append(f"- 경력 단계: {pref.experience_level}")
        if pref.preferred_job_rank:
            parts.append(f"- 희망 직급: {pref.preferred_job_rank}")
        if pref.preferred_company_sizes:
            parts.append(f"- 선호 기업 규모: {', '.join(pref.preferred_company_sizes)}")
        if pref.preferred_benefits:
            parts.append(f"- 선호 복리후생: {', '.join(pref.preferred_benefits)}")
        if parts:
            pref_section = (
                "\n[사용자 선호 조건 — 스코어링 시 반영]\n"
                + "\n".join(parts)
                + "\n선호 조건에 가까울수록 높은 점수를 부여하라.\n"
            )

    return f"""당신은 채용 공고 적합도 평가 AI입니다.
지원자의 이력 소재를 기반으로 각 채용 공고에 대한 적합도 점수를 계산하십시오.

{context}
{pref_section}
평가 기준:
- 경력: 공고의 경력 조건과 지원자 경험 일치도
- 기술스택: 공고 요구 기술과 지원자 보유 기술 일치도
- 학력/기타: 공고 학력 조건, 고용 형태 적합도

[출력 규칙 — 반드시 준수]
- JSON 배열 하나만 출력한다. 다른 텍스트나 마크다운을 포함하지 않는다.
- 첫 글자는 반드시 [ 이고 마지막 글자는 반드시 ] 이다.
- 전달된 모든 공고에 대해 빠짐없이 점수를 계산한다. Top N 선택은 하지 않는다.
- 스키마: [{{"job_posting_id": <공고 ID>, "match_score": 87.50, "reason_text": "경력:90, 기술스택:80, 복지:75"}}]
- match_score는 0~100 사이 소수점 2자리 숫자이다."""


def _format_batch(batch: list[JobPost]) -> str:
    lines = ["[평가 대상 채용 공고]"]
    for jp in batch:
        jid = jp.job_posting_id if jp.job_posting_id is not None else jp.job_id
        lines.append(f"\n## job_posting_id: {jid}")
        lines.append(f"- 공고 설명: {jp.description}")
        lines.append(f"- 경력 조건: {jp.experience_text}")
        lines.append(f"- 학력 조건: {jp.education_text}")
        lines.append(f"- 고용 형태: {jp.employment_type}")
    return "\n".join(lines)


def _parse_scores(text: str) -> list[Recommendation]:
    code_block = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if code_block:
        candidate = code_block.group(1)
    else:
        start = text.find("[")
        end = text.rfind("]")
        candidate = text[start: end + 1] if start != -1 and end > start else text

    try:
        raw = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return []

    result = []
    for item in raw:
        try:
            raw_id = item["job_posting_id"]
            try:
                rec = Recommendation(
                    job_posting_id=int(raw_id),
                    match_score=float(item["match_score"]),
                    reason_text=str(item.get("reason_text", "")),
                )
            except (ValueError, TypeError):
                rec = Recommendation(
                    job_id=str(raw_id),
                    match_score=float(item["match_score"]),
                    reason_text=str(item.get("reason_text", "")),
                )
            result.append(rec)
        except (KeyError, ValueError):
            continue
    return result


async def _score_batch(
    batch: list[JobPost],
    materials: list[ResumeMaterial],
    llm,
    pref: UserPreferences | None = None,
) -> list[Recommendation]:
    try:
        batch_text = _format_batch(batch)
        messages = [
            SystemMessage(content=_build_score_prompt(materials, pref)),
            HumanMessage(
                content=f"{batch_text}\n\n위 공고들의 적합도 점수를 JSON 배열로 반환하십시오."
            ),
        ]
        response = await asyncio.wait_for(llm.ainvoke(messages), timeout=_LLM_TIMEOUT)
        return _parse_scores(response.content)
    except Exception as e:
        logger.warning("배치 처리 실패 (건너뜀): %s", e)
        return []


async def top10_matching(
    materials: list[ResumeMaterial],
    job_posts: list[JobPost],
    user_preferences: UserPreferences | None = None,
) -> MatchResponse:
    """
    3단계 파이프라인:
    [1] _pre_filter  — 피하고 싶어요 + 지역 필터 (Python, 0ms)
    [2] _embedding_filter — OpenRouter 임베딩 유사도 top-25
    [3] LLM 병렬 스코어링 — asyncio.gather, 선호도 프롬프트 반영
    지역 필터 결과 < 10이면 지역 필터 해제 후 재시도.
    """
    pref = user_preferences or UserPreferences()
    llm = get_llm_client(temperature=0.1)

    # [1] 피하고 싶어요 + 지역 필터
    eligible = _pre_filter(job_posts, pref, apply_location=True)

    # [2] 임베딩 top-25
    embedding_filtered = await _embedding_filter(materials, eligible, top_n=25)

    # 지역 필터 fallback: 결과 < 10이면 지역 필터 해제 후 재시도
    if len(embedding_filtered) < 10 and pref.preferred_locations:
        logger.info("지역 필터 결과 %d개 미만 — 지역 필터 해제 후 재시도", len(embedding_filtered))
        eligible_all = _pre_filter(job_posts, pref, apply_location=False)
        embedding_filtered = await _embedding_filter(materials, eligible_all, top_n=25)

    # [3] LLM 병렬 스코어링
    tasks = [
        _score_batch(batch, materials, llm, pref)
        for batch in _chunk(embedding_filtered, BATCH_SIZE)
    ]
    results = await asyncio.gather(*tasks)
    all_scores = [r for batch in results for r in batch]

    top10 = sorted(all_scores, key=lambda r: r.match_score, reverse=True)[:10]
    return MatchResponse(recommendations=top10)

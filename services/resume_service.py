import json
import logging
import os
import re

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_groq import ChatGroq

from models import (
    ResumeMaterial,
    JobPost,
    ResumeFixResponse,
    ResumeChatResponse,
    ChangeItem,
)
from services.llm_client import get_llm_client
from services.session_store import session_store
from utils.fact_check import build_context_block, llm_verify_against_materials

logger = logging.getLogger(__name__)

_MAX_HISTORY_MESSAGES = 20
_SUMMARY_KEEP_MESSAGES = 6


def _get_verifier_llm():
    """검증 전용 LLM (Gemma). 생성 모델과 다른 아키텍처로 Self-Verification Bias 감소."""
    return ChatGroq(
        api_key=os.getenv("GROQ_API_KEY"),
        model=os.getenv("VERIFY_MODEL", "llama-3.1-8b-instant"),
        temperature=0.0,
    )


def _build_chat_system_prompt(materials: list[ResumeMaterial], job_post: JobPost | None) -> str:
    context = build_context_block(materials)
    job_info = ""
    if job_post:
        job_info = f"""
[채용 공고 정보]
- 공고 설명: {job_post.description}
- 경력 조건: {job_post.experience_text}
- 학력 조건: {job_post.education_text}
- 고용 형태: {job_post.employment_type}"""

    return f"""당신은 이력서 교정 전문 AI입니다.
사용자의 요청에 따라 이력서를 수정하되, 반드시 아래 소재에서 유래한 내용만 사용하십시오.
제공된 소재에 없는 내용을 추가하거나 지어내지 마십시오.

{context}{job_info}

[출력 규칙 — 반드시 준수]
- 응답은 JSON 객체 하나만 출력한다. 다른 텍스트, 설명, 마크다운 코드 블록을 절대 포함하지 않는다.
- 첫 글자는 반드시 {{ 이어야 하고, 마지막 글자는 반드시 }} 이어야 한다.
- 아래 스키마를 정확히 따른다:

{{"changes": [{{"original": "원본 텍스트", "suggested": "수정된 텍스트", "reason": "수정 이유", "material_id": "소재 id 또는 null"}}]}}"""


# AI 기억 압축: 이전 대화 요약과 최신 메시지만 유지
async def _summarize_history(history: list[dict], llm) -> list[dict]:
    """대화 이력이 임계값을 초과하면 앞부분을 요약하고 최신 메시지만 유지한다."""
    old = history[:-_SUMMARY_KEEP_MESSAGES]
    recent = history[-_SUMMARY_KEEP_MESSAGES:]

    summary_prompt = "다음 대화 이력을 한국어로 간결하게 요약하십시오:\n\n"
    for msg in old:
        summary_prompt += f"{msg['role'].upper()}: {msg['content']}\n"

    summary_msg = await llm.ainvoke([HumanMessage(content=summary_prompt)])
    summary_text = f"[이전 대화 요약]\n{summary_msg.content}"

    return [{"role": "system", "content": summary_text}] + recent


async def _extract_material_keywords(materials: list[ResumeMaterial], llm) -> list[str]:
    """소재에서 역량 키워드를 추출한다. (Phase 3-1)"""
    context = build_context_block(materials)
    prompt = f"""{context}

위 소재에서 이력서에 활용할 핵심 역량 키워드를 추출하라.
소재 유형(경험·기술·프로젝트)별로 대표 키워드를 각 줄에 하나씩 나열하라.
추가 설명 없이 키워드만 나열하라."""

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    lines = [line.strip() for line in response.content.splitlines() if line.strip()]
    clean = []
    for line in lines:
        line = re.sub(r"^[\-\*\d\.\s]+", "", line).strip()
        if line:
            clean.append(line)
    return clean


async def fix_resume(
    materials: list[ResumeMaterial], job_post: JobPost
) -> ResumeFixResponse:
    """이력서 자동 생성. 마스킹 + 플래너 파이프라인 사용."""
    from services.resume_service_v2 import fix_resume_v2
    return await fix_resume_v2(materials, job_post)


async def chat_resume(
    session_id: str | None,
    user_message: str,
    materials: list[ResumeMaterial],
    job_post: JobPost | None,
) -> ResumeChatResponse:
    """챗봇 교정 모드 (Session-based + 변경 항목별 LLM 검증). temperature: 0.6."""
    llm = get_llm_client(temperature=0.6)
    verifier_llm = _get_verifier_llm()
    system_prompt = _build_chat_system_prompt(materials, job_post)

    if not session_id or not session_store.exists(session_id):
        session_id = session_store.create_session()

    history = session_store.get_history(session_id)

    # 토큰 예산 초과 시 요약(과거 메시지 요약)
    if len(history) > _MAX_HISTORY_MESSAGES:
        history = await _summarize_history(history, llm)
        # 요약된 이력을 세션에 덮어쓰기
        session_store.delete(session_id)
        session_id = session_store.create_session()
        for msg in history:
            session_store.append(session_id, msg["role"], msg["content"])

    # 메시지 조립
    messages = [SystemMessage(content=system_prompt)]
    for msg in history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
        else:
            messages.append(SystemMessage(content=msg["content"]))
    messages.append(HumanMessage(content=user_message))

    response = await llm.ainvoke(messages)
    ai_text = response.content

    session_store.append(session_id, "user", user_message)
    session_store.append(session_id, "assistant", ai_text)

    # 각 변경 항목을 개별 검증 — 날조 감지된 항목만 제거
    changes = _parse_changes(ai_text)
    verified_changes = []
    for item in changes:
        is_pass, _ = await llm_verify_against_materials(item.suggested, materials, verifier_llm)
        if is_pass:
            verified_changes.append(item)

    return ResumeChatResponse(session_id=session_id, changes=verified_changes)


async def generate_resume(
    user_profile: str,
    materials: list[ResumeMaterial],
    job_post: JobPost,
) -> "ResumeGenerateResponse":
    """1클릭 이력서 초안 생성. 유저 프로필 + 소재 키워드 + 공고 JD 기반 전문 생성. temperature: 0.6."""
    from models import ResumeGenerateResponse

    llm = get_llm_client(temperature=0.6)
    verifier_llm = _get_verifier_llm()

    keywords = await _extract_material_keywords(materials, llm)
    context = build_context_block(materials)
    kw_list = "\n".join(f"- {kw}" for kw in keywords)

    system_prompt = f"""당신은 전문 이력서 작성 AI입니다.
아래 유저 프로필, 소재, 핵심 키워드를 바탕으로 채용 공고 맞춤형 이력서 초안 전문을 작성하십시오.
소재에 없는 내용을 지어내지 마십시오.

[유저 프로필]
{user_profile}

{context}

[핵심 역량 키워드]
{kw_list}

[채용 공고 정보]
- 공고 설명: {job_post.description}
- 경력 조건: {job_post.experience_text}
- 학력 조건: {job_post.education_text}
- 고용 형태: {job_post.employment_type}

지시사항:
1. 자기소개, 경력/프로젝트, 기술스택 섹션을 포함한 이력서 초안을 작성하십시오.
2. 소재에 없는 내용을 절대 추가하지 마십시오.
3. 핵심 키워드를 이력서에 자연스럽게 반영하십시오."""

    user_msg = "위 내용을 바탕으로 이력서 초안을 작성해 주십시오."
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_msg),
    ]

    response = await llm.ainvoke(messages)
    generated = response.content

    is_pass, issues = await llm_verify_against_materials(generated, materials, verifier_llm)
    if is_pass:
        return ResumeGenerateResponse(generated_resume=generated)

    issues_text = "\n".join(f"- {issue}" for issue in issues)
    messages[1] = HumanMessage(content=(
        f"{user_msg}\n\n"
        f"주의: 소재에 없는 내용이 감지되었습니다. 아래 항목을 반드시 제외하십시오:\n{issues_text}"
    ))
    response = await llm.ainvoke(messages)
    generated_retry = response.content

    is_pass2, _ = await llm_verify_against_materials(generated_retry, materials, verifier_llm)
    if is_pass2:
        return ResumeGenerateResponse(generated_resume=generated_retry)

    logger.warning("generate_resume: 2회 검증 모두 실패. 소재 원문을 반환합니다.")
    return ResumeGenerateResponse(generated_resume="\n\n".join(m.content for m in materials))


# JSON 추출
def _extract_json(text: str) -> str:
    """LLM 응답에서 JSON 객체 부분만 추출한다."""
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block:
        return code_block.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


# JSON을 파이썬이 이해할 수 있도록 ChangeItem 리스트로 변환
def _parse_changes(text: str) -> list[ChangeItem]:
    """추출된 JSON 문자열을 분석(Parsing)하여 ChangeItem 객체 리스트로 변환한다."""
    candidate = _extract_json(text)
    try:
        data = json.loads(candidate)
        raw_changes = data.get("changes", [])
    except (json.JSONDecodeError, AttributeError):
        return [
            ChangeItem(
                original="",
                suggested=text,
                reason="AI 응답 (JSON 파싱 실패)",
                material_id=None,
            )
        ]
    result = []
    for item in raw_changes:
        result.append(
            ChangeItem(
                original=item.get("original", ""),
                suggested=item.get("suggested", ""),
                reason=item.get("reason", ""),
                material_id=item.get("material_id"),
            )
        )
    return result

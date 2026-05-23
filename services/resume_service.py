import json
import logging
import os
import re

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_groq import ChatGroq

from models import (
    ResumeMaterial,
    JobPost,
    UserProfile,
    ResumeFixResponse,
    ResumeChatResponse,
    ResumeBody,
    ResumeExperience,
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
        job_info = (
            f"\n[채용 공고 정보]\n"
            f"- 공고 설명: {job_post.description}\n"
            f"- 경력 조건: {job_post.experience_text}\n"
            f"- 학력 조건: {job_post.education_text}\n"
            f"- 고용 형태: {job_post.employment_type}"
        )

    return (
        "당신은 이력서 교정 전문 AI입니다.\n"
        "사용자의 요청에 따라 이력서를 수정하되, 반드시 아래 소재에서 유래한 내용만 사용하십시오.\n"
        "제공된 소재에 없는 내용을 추가하거나 지어내지 마십시오.\n\n"
        f"{context}{job_info}\n\n"
        "[출력 규칙 — 반드시 준수]\n"
        "- 응답은 JSON 객체 하나만 출력한다. 다른 텍스트, 설명, 마크다운 코드 블록을 절대 포함하지 않는다.\n"
        "- 첫 글자는 반드시 { 이어야 하고, 마지막 글자는 반드시 } 이어야 한다.\n"
        "- reason은 255자 이하로 작성한다.\n"
        "- 아래 스키마를 정확히 따른다:\n\n"
        '{"reason": "수정 이유 (255자 이하)", '
        '"body": {"about": "자기소개 문단", '
        '"experience": [{"company": "회사명", "period": "기간", "role": "직무", "description": "상세 내용"}], '
        '"skills": ["기술1", "기술2"]}}'
    )


def _build_initial_context(
    current_body: dict | None,
    materials: list[ResumeMaterial],
) -> str:
    """세션 재생성 시 이전 이력서 상태를 복원할 컨텍스트를 구성한다."""
    parts: list[str] = []
    if current_body:
        parts.append(f"[현재 이력서 본문]\n{json.dumps(current_body, ensure_ascii=False, indent=2)}")
    context = build_context_block(materials)
    if context:
        parts.append(context)
    return "\n\n".join(parts)


def _parse_body_from_llm(text: str) -> tuple[str, ResumeBody]:
    """LLM 응답에서 {reason, body} JSON을 파싱한다. 실패 시 기본값 반환."""
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        try:
            data = json.loads(text[start:end + 1])
            reason = str(data.get("reason", ""))[:255]
            body_data = data.get("body", {})
            experiences = [
                ResumeExperience(**exp) if isinstance(exp, dict) else ResumeExperience()
                for exp in body_data.get("experience", [])
            ]
            body = ResumeBody(
                about=body_data.get("about"),
                experience=experiences,
                skills=body_data.get("skills", []),
            )
            return reason, body
        except (json.JSONDecodeError, TypeError):
            pass
    return "AI 응답 파싱 실패", ResumeBody(about=text)


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
    """소재에서 역량 키워드를 추출한다."""
    context = build_context_block(materials)
    prompt = (
        f"{context}\n\n"
        "위 소재에서 이력서에 활용할 핵심 역량 키워드를 추출하라.\n"
        "소재 유형(경험·기술·프로젝트)별로 대표 키워드를 각 줄에 하나씩 나열하라.\n"
        "추가 설명 없이 키워드만 나열하라."
    )
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
    message: str,
    current_body: dict | None,
    materials: list[ResumeMaterial],
    job_post: JobPost | None,
) -> ResumeChatResponse:
    """챗봇 교정 모드 (Session-based). suggested_body(ResumeBody) + reason 반환."""
    llm = get_llm_client(temperature=0.6)
    verifier_llm = _get_verifier_llm()
    system_prompt = _build_chat_system_prompt(materials, job_post)

    initial_context = _build_initial_context(current_body, materials)
    sid = session_store.get_or_create(session_id, initial_context)

    history = session_store.get_history(sid)

    if len(history) > _MAX_HISTORY_MESSAGES:
        history = await _summarize_history(history, llm)
        session_store.delete(sid)
        sid = session_store.get_or_create(session_id, initial_context)
        for msg in history:
            session_store.append(sid, msg["role"], msg["content"])

    messages = [SystemMessage(content=system_prompt)]
    for msg in history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
        else:
            messages.append(SystemMessage(content=msg["content"]))
    messages.append(HumanMessage(content=message))

    response = await llm.ainvoke(messages)
    ai_text = response.content

    session_store.append(sid, "user", message)
    session_store.append(sid, "assistant", ai_text)

    reason, body = _parse_body_from_llm(ai_text)

    is_pass, _ = await llm_verify_against_materials(
        body.model_dump_json(), materials, verifier_llm
    )
    if not is_pass:
        logger.warning("chat_resume: hallucination detected, returning parsed body as-is")

    return ResumeChatResponse(reason=reason, suggested_body=body)


def _format_user_profile(user_profile: UserProfile) -> str:
    """UserProfile 객체를 LLM 프롬프트용 텍스트로 변환."""
    lines = []
    if user_profile.career_level:
        lines.append(f"경력: {user_profile.career_level}")
    if user_profile.school_name:
        lines.append(
            f"학력: {user_profile.degree_type} {user_profile.school_name} {user_profile.major}, "
            f"{user_profile.enrollment_year}~{user_profile.graduation_year} {user_profile.graduation_status}"
        )
    return "\n".join(lines)


async def generate_resume(
    user_profile: UserProfile,
    materials: list[ResumeMaterial],
    job_post: JobPost,
) -> "ResumeGenerateResponse":
    """1클릭 이력서 초안 생성. v2 파이프라인으로 위임."""
    from services.resume_service_v2 import generate_resume_v2
    return await generate_resume_v2(user_profile, materials, job_post)

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from models import (
    ResumeMaterial,
    JobPost,
    UserProfile,
    ResumeExperience,
    ResumeBody,
    ResumeVersion,
    ResumeFixResponse,
    ResumeChatResponse,
    ResumeGenerateResponse,
)
from services.llm_client import get_llm_client, get_light_llm_client, get_verifier_llm_client
from services.session_store import session_store
from utils.fact_check import (
    build_context_block,
    extract_fact_tokens,
    mask_materials,
    unmask_text,
    verify_facts_present,
    llm_verify_against_materials,
)

logger = logging.getLogger(__name__)

_MAX_HISTORY_MESSAGES = 20
_SUMMARY_KEEP_MESSAGES = 6
_LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT_SECONDS", "90"))

_EXPLICIT_RULES = (
    "\n[작성 지시사항]\n"
    "1. 제공된 소재 이외의 내용을 절대 추가하지 마십시오.\n"
    "2. 공고의 요구 역량에 맞는 소재를 우선 배치하십시오.\n"
    "3. 완성된 이력서를 JSON 형식으로 반환하십시오."
)

_VERSION_STYLES = {
    "JOB_FIT": (
        "공고 요구사항을 직접 매핑하고 직무 키워드를 강조하십시오. "
        "채용 담당자가 JD 체크리스트를 보듯 읽을 수 있도록 작성하십시오."
    ),
    "ACHIEVEMENT": (
        "수치와 성과를 중심으로 임팩트 있는 표현으로 작성하십시오. "
        "구체적인 수치(%, 건수, 규모)를 최대한 활용하십시오."
    ),
}


def _get_verifier_llm():
    return get_verifier_llm_client()


async def _ainvoke(llm, messages: list):
    """LLM 호출 + 타임아웃. 초과 시 asyncio.TimeoutError 발생."""
    return await asyncio.wait_for(llm.ainvoke(messages), timeout=_LLM_TIMEOUT)


# ── 챗봇 모드 헬퍼 ────────────────────────────────────────────────────────────

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


def _build_initial_context(current_body: ResumeBody | None, materials: list[ResumeMaterial]) -> str:
    parts: list[str] = []
    if current_body:
        parts.append(f"[현재 이력서 본문]\n{json.dumps(current_body.model_dump(), ensure_ascii=False, indent=2)}")
    context = build_context_block(materials)
    if context:
        parts.append(context)
    return "\n\n".join(parts)


def _parse_body_from_llm(text: str) -> tuple[str, ResumeBody]:
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
    old = history[:-_SUMMARY_KEEP_MESSAGES]
    recent = history[-_SUMMARY_KEEP_MESSAGES:]
    summary_prompt = "다음 대화 이력을 한국어로 간결하게 요약하십시오:\n\n"
    for msg in old:
        summary_prompt += f"{msg['role'].upper()}: {msg['content']}\n"
    summary_msg = await _ainvoke(llm, [HumanMessage(content=summary_prompt)])
    summary_text = f"[이전 대화 요약]\n{summary_msg.content}"
    return [{"role": "system", "content": summary_text}] + recent


# ── v2 파이프라인 헬퍼 ────────────────────────────────────────────────────────

def _parse_plan(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return {}


def _parse_resume_body(text: str) -> ResumeBody:
    """LLM 응답 텍스트에서 ResumeBody JSON을 파싱한다. 실패 시 about에 전문을 담아 반환."""
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        try:
            data = json.loads(text[start:end + 1])
            experiences = [
                ResumeExperience(**exp) if isinstance(exp, dict) else ResumeExperience()
                for exp in data.get("experience", [])
            ]
            return ResumeBody(
                about=data.get("about"),
                experience=experiences,
                skills=data.get("skills", []),
            )
        except (json.JSONDecodeError, TypeError):
            pass
    return ResumeBody(about=text)


async def _plan_resume(masked_materials: list[ResumeMaterial], job_post: JobPost, llm) -> dict:
    context = build_context_block(masked_materials)
    prompt = (
        f"{context}\n\n"
        f"[채용 공고]\n"
        f"설명: {job_post.description}\n"
        f"경력: {job_post.experience_text}\n"
        f"학력: {job_post.education_text}\n"
        f"고용형태: {job_post.employment_type}\n\n"
        "위 공고와 소재를 분석하여 이력서 작성 계획을 아래 JSON 형식으로만 작성하라 (다른 텍스트 없음):\n"
        "{\n"
        '  "sections": ["자기소개", "경력사항", "프로젝트", "기술스택"],\n'
        '  "emphasis": {"섹션명": "강조할 내용"},\n'
        '  "style": {"tone": "전문적이고 겸손한", "ending": "~했습니다", "structure": "두괄식"},\n'
        '  "material_strategy": {"소재 요약": "활용할 섹션"}\n'
        "}"
    )
    resp = await _ainvoke(llm, [HumanMessage(content=prompt)])
    plan = _parse_plan(resp.content)
    if not plan:
        plan = {
            "sections": ["자기소개", "경력사항", "프로젝트", "기술스택"],
            "emphasis": {},
            "style": {"tone": "전문적", "ending": "~했습니다", "structure": "두괄식"},
            "material_strategy": {},
        }
    return plan


def _build_generator_prompt(
    masked_materials: list[ResumeMaterial],
    job_post: JobPost,
    plan: dict,
    version_style: str,
    extra_context: str = "",
    include_rules: bool = False,
) -> str:
    context = build_context_block(masked_materials)
    sections = plan.get("sections", [])
    emphasis = plan.get("emphasis", {})
    style = plan.get("style", {})

    section_guide = "\n".join(
        f"- {s}: {emphasis.get(s, '소재 기반으로 작성')}" for s in sections
    )
    style_guide = (
        f"말투: {style.get('tone', '전문적')}, "
        f"어미: {style.get('ending', '~했습니다')}, "
        f"구조: {style.get('structure', '두괄식')}"
    )

    prompt = (
        "당신은 전문 이력서 작성 AI입니다.\n"
        "아래 소재(마스킹된 팩트는 [F숫자] 형태)와 지침을 바탕으로 이력서를 JSON 형식으로 작성하십시오.\n"
        "소재에 없는 내용을 추가하거나 지어내지 마십시오.\n"
        "[F숫자] 기호는 절대 변경하지 말고 그대로 유지하십시오.\n\n"
        f"[버전 스타일 지시]\n{version_style}\n\n"
        f"{context}\n"
        f"{extra_context}"
        f"\n[채용 공고]\n"
        f"설명: {job_post.description}\n"
        f"경력: {job_post.experience_text}\n"
        f"학력: {job_post.education_text}\n"
        f"고용형태: {job_post.employment_type}\n\n"
        f"[작성 계획]\n"
        f"섹션 순서: {sections}\n"
        f"섹션별 강조점:\n{section_guide}\n"
        f"문체 지침: {style_guide}\n\n"
        "[출력 형식 — 반드시 준수]\n"
        "아래 JSON 스키마를 정확히 따르라. 다른 텍스트를 포함하지 마라:\n"
        '{"about": "자기소개 문단", '
        '"experience": [{"company": "회사명", "period": "기간", "role": "직무", "description": "상세 내용"}], '
        '"skills": ["기술1", "기술2"]}'
    )
    if include_rules:
        prompt += _EXPLICIT_RULES
    return prompt


async def _generate_version(
    masked_materials: list[ResumeMaterial],
    job_post: JobPost,
    plan: dict,
    version_type: str,
    llm,
    extra_context: str = "",
    issue_note: str = "",
    include_rules: bool = False,
) -> str:
    style = _VERSION_STYLES[version_type]
    system_prompt = _build_generator_prompt(
        masked_materials, job_post, plan, style, extra_context, include_rules
    )
    user_msg = "위 소재와 계획서를 바탕으로 이력서를 JSON 형식으로 작성해 주십시오."
    if issue_note:
        user_msg += f"\n\n주의: 이전 생성에서 아래 문제가 감지되었습니다. 반드시 수정하십시오:\n{issue_note}"

    resp = await _ainvoke(llm, [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_msg),
    ])
    return resp.content


async def _score_version(version_text: str, job_post: JobPost, llm) -> int:
    """공고 키워드 대비 소재 커버리지를 0~100 정수로 산출한다."""
    prompt = (
        f"[채용 공고]\n{job_post.description}\n경력: {job_post.experience_text}\n\n"
        f"[이력서]\n{version_text}\n\n"
        "위 이력서가 채용 공고의 요구사항을 얼마나 충족하는지 0~100 정수로만 답하라. 다른 텍스트 없음."
    )
    resp = await _ainvoke(llm, [HumanMessage(content=prompt)])
    match = re.search(r"\d+", resp.content.strip())
    if match:
        return min(100, max(0, int(match.group())))
    return 50


async def _run_version_pipeline(
    version_type: str,
    original_materials: list[ResumeMaterial],
    masked_materials: list[ResumeMaterial],
    job_post: JobPost,
    plan: dict,
    fact_map: dict[str, str],
    main_llm,
    verifier_llm,
    light_llm,
    extra_context: str = "",
) -> ResumeVersion:
    raw = await _generate_version(masked_materials, job_post, plan, version_type, main_llm, extra_context)
    unmasked = unmask_text(raw, fact_map)

    facts_ok, missing_facts = verify_facts_present(unmasked, fact_map)
    all_issues: list[str] = [f"누락된 팩트: {v}" for v in missing_facts] if not facts_ok else []

    llm_ok, llm_issues = await llm_verify_against_materials(unmasked, original_materials, verifier_llm)
    if not llm_ok:
        all_issues += llm_issues

    if all_issues:
        issues_text = "\n".join(f"- {i}" for i in all_issues)
        raw = await _generate_version(
            masked_materials, job_post, plan, version_type, main_llm, extra_context, issue_note=issues_text
        )
        unmasked = unmask_text(raw, fact_map)
        if not unmasked.strip():
            unmasked = raw

    body = _parse_resume_body(unmasked)
    score = await _score_version(unmasked, job_post, light_llm)

    return ResumeVersion(type=version_type, body=body, matching_score=score, summary=body.about or "")


# ── 공개 API ──────────────────────────────────────────────────────────────────

def _format_user_profile(user_profile: UserProfile) -> str:
    lines = []
    if user_profile.career_level:
        lines.append(f"경력: {user_profile.career_level}")
    if user_profile.school_name:
        lines.append(
            f"학력: {user_profile.degree_type} {user_profile.school_name} {user_profile.major}, "
            f"{user_profile.enrollment_year}~{user_profile.graduation_year} {user_profile.graduation_status}"
        )
    return "\n".join(lines)


async def fix_resume(
    materials: list[ResumeMaterial], job_post: JobPost
) -> ResumeFixResponse:
    """이력서 자동 생성. 팩트 마스킹 + Planner + Generator(JOB_FIT, ACHIEVEMENT) + Verifier."""
    main_llm = get_llm_client(temperature=0.6)
    light_llm = get_light_llm_client(temperature=0.1)
    verifier_llm = _get_verifier_llm()

    fact_map = await extract_fact_tokens(materials, light_llm)
    masked = mask_materials(materials, fact_map)
    plan = await _plan_resume(masked, job_post, light_llm)

    versions = await asyncio.gather(*[
        _run_version_pipeline(
            vtype, materials, masked, job_post, plan, fact_map, main_llm, verifier_llm, light_llm
        )
        for vtype in ("JOB_FIT", "ACHIEVEMENT")
    ])

    recommended = max(versions, key=lambda v: v.matching_score).type

    return ResumeFixResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        recommended_type=recommended,
        versions=list(versions),
    )


async def generate_resume(
    user_profile: UserProfile,
    materials: list[ResumeMaterial],
    job_post: JobPost,
) -> ResumeGenerateResponse:
    """1클릭 이력서 초안 생성. JOB_FIT 단일 버전으로 생성."""
    main_llm = get_llm_client(temperature=0.6)
    light_llm = get_light_llm_client(temperature=0.1)
    verifier_llm = _get_verifier_llm()

    fact_map = await extract_fact_tokens(materials, light_llm)
    masked = mask_materials(materials, fact_map)
    plan = await _plan_resume(masked, job_post, light_llm)
    extra = f"[유저 프로필]\n{_format_user_profile(user_profile)}\n"

    version = await _run_version_pipeline(
        "JOB_FIT", materials, masked, job_post, plan, fact_map,
        main_llm, verifier_llm, light_llm, extra_context=extra,
    )

    body_text = json.dumps(version.body.model_dump(), ensure_ascii=False, indent=2)
    return ResumeGenerateResponse(generated_resume=body_text)


async def chat_resume(
    session_id: str | None,
    message: str,
    current_body: ResumeBody | None,
    materials: list[ResumeMaterial],
    job_post: JobPost | None,
) -> ResumeChatResponse:
    """챗봇 교정 모드 (Session-based). reason + suggested_body(ResumeBody) 반환."""
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

    response = await _ainvoke(llm, messages)
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

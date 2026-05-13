import json
import logging
import os
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from models.resume import (
    ResumeMaterial,
    JobPost,
    ResumeFixResponse,
    ResumeGenerateResponse,
)
from services.llm_client import get_llm_client, get_light_llm_client
from utils.fact_check import (
    build_context_block,
    extract_fact_tokens,
    mask_materials,
    unmask_text,
    verify_facts_present,
    llm_verify_against_materials,
)

logger = logging.getLogger(__name__)


def _get_verifier_llm():
    """검증 전용 LLM (Gemma). Self-Verification Bias 감소 목적."""
    return ChatGroq(
        api_key=os.getenv("GROQ_API_KEY"),
        model=os.getenv("VERIFY_MODEL", "gemma2-9b-it"),
        temperature=0.0,
    )


def _parse_plan(text: str) -> dict:
    """LLM 응답에서 JSON 계획서를 추출한다."""
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return {}


async def _plan_resume(
    masked_materials: list[ResumeMaterial],
    job_post: JobPost,
    llm,
) -> dict:
    """
    Planner 단계. 마스킹된 소재와 공고를 분석하여 이력서 구성안(JSON)을 생성한다.
    섹션 순서, 소재 활용 전략, 문체 스타일 지침 포함.
    """
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
    resp = await llm.ainvoke([HumanMessage(content=prompt)])
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
    extra_context: str = "",
) -> str:
    """Generator 단계용 시스템 프롬프트를 구성한다."""
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

    return (
        "당신은 전문 이력서 작성 AI입니다.\n"
        "아래 소재(마스킹된 팩트는 [F숫자] 형태)와 계획서를 바탕으로 이력서 전문을 작성하십시오.\n"
        "소재에 없는 내용을 추가하거나 지어내지 마십시오.\n"
        "[F숫자] 기호는 절대 변경하지 말고 그대로 유지하십시오.\n\n"
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
        f"문체 지침: {style_guide}"
    )


async def _generate_from_plan(
    masked_materials: list[ResumeMaterial],
    job_post: JobPost,
    plan: dict,
    llm,
    extra_context: str = "",
    issue_note: str = "",
) -> str:
    """Generator 단계. 계획서와 마스킹 소재 기반으로 이력서 전문을 생성한다."""
    system_prompt = _build_generator_prompt(masked_materials, job_post, plan, extra_context)
    user_msg = "위 소재와 계획서를 바탕으로 이력서 전문을 작성해 주십시오."
    if issue_note:
        user_msg += f"\n\n주의: 이전 생성에서 아래 문제가 감지되었습니다. 반드시 수정하십시오:\n{issue_note}"

    resp = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_msg),
    ])
    return resp.content


async def _run_pipeline(
    original_materials: list[ResumeMaterial],
    masked_materials: list[ResumeMaterial],
    job_post: JobPost,
    plan: dict,
    fact_map: dict[str, str],
    main_llm,
    verifier_llm,
    extra_context: str = "",
    issue_note: str = "",
) -> tuple[str, bool, list[str]]:
    """
    Generator → 언마스킹 → 팩트 검사 → 날조 검사 순으로 실행.
    반환: (최종_텍스트, 검증_통과_여부, 이슈_목록)
    """
    raw = await _generate_from_plan(
        masked_materials, job_post, plan, main_llm, extra_context, issue_note
    )
    unmasked = unmask_text(raw, fact_map)

    # ⑤-a 팩트 검사 (Python, LLM 없음)
    facts_ok, missing_facts = verify_facts_present(unmasked, fact_map)
    all_issues: list[str] = []
    if not facts_ok:
        all_issues += [f"누락된 팩트: {v}" for v in missing_facts]

    # ⑤-b 날조 검사 (LLM)
    llm_ok, llm_issues = await llm_verify_against_materials(unmasked, original_materials, verifier_llm)
    if not llm_ok:
        all_issues += llm_issues

    return unmasked, len(all_issues) == 0, all_issues


async def fix_resume_v2(
    materials: list[ResumeMaterial],
    job_post: JobPost,
) -> ResumeFixResponse:
    """
    v2 파이프라인: 팩트 마스킹 + Planner + Generator + 2단계 Verifier.
    기존 /fix 엔드포인트와 동일 입출력 스키마 (성능 비교 목적).
    """
    main_llm = get_llm_client(temperature=0.6)
    light_llm = get_light_llm_client(temperature=0.1)
    verifier_llm = _get_verifier_llm()

    # ① 팩트 추출 + 마스킹
    fact_map = await extract_fact_tokens(materials, light_llm)
    masked = mask_materials(materials, fact_map)

    # ② Planner
    plan = await _plan_resume(masked, job_post, light_llm)

    # ③~⑤ 생성 + 검증
    result, is_pass, issues = await _run_pipeline(
        materials, masked, job_post, plan, fact_map, main_llm, verifier_llm
    )

    if is_pass:
        return ResumeFixResponse(revised_resume=result)

    # 실패 시 1회 재시도 (이슈 명시)
    issues_text = "\n".join(f"- {i}" for i in issues)
    result_retry, _, _ = await _run_pipeline(
        materials, masked, job_post, plan, fact_map, main_llm, verifier_llm,
        issue_note=issues_text,
    )

    if not result_retry.strip():
        logger.warning("fix_resume_v2: 재시도 결과 비어있음. 1차 결과 반환.")
        result_retry = result

    return ResumeFixResponse(revised_resume=result_retry)


async def generate_resume_v2(
    user_profile: str,
    materials: list[ResumeMaterial],
    job_post: JobPost,
) -> ResumeGenerateResponse:
    """
    v2 파이프라인 기반 1클릭 초안 생성.
    fix_resume_v2와 동일하나 Generator 프롬프트에 유저 프로필 추가.
    """
    main_llm = get_llm_client(temperature=0.6)
    light_llm = get_light_llm_client(temperature=0.1)
    verifier_llm = _get_verifier_llm()

    fact_map = await extract_fact_tokens(materials, light_llm)
    masked = mask_materials(materials, fact_map)
    plan = await _plan_resume(masked, job_post, light_llm)

    extra = f"[유저 프로필]\n{user_profile}\n"

    result, is_pass, issues = await _run_pipeline(
        materials, masked, job_post, plan, fact_map, main_llm, verifier_llm,
        extra_context=extra,
    )

    if is_pass:
        return ResumeGenerateResponse(generated_resume=result)

    issues_text = "\n".join(f"- {i}" for i in issues)
    result_retry, _, _ = await _run_pipeline(
        materials, masked, job_post, plan, fact_map, main_llm, verifier_llm,
        extra_context=extra,
        issue_note=issues_text,
    )

    if not result_retry.strip():
        logger.warning("generate_resume_v2: 재시도 결과 비어있음. 1차 결과 반환.")
        result_retry = result

    return ResumeGenerateResponse(generated_resume=result_retry)

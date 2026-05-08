import json
import logging
import os
import re
from typing import TypedDict

from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from models.resume import ResumeMaterial, JobPost, ResumeFixResponse
from services.llm_client import get_llm_client
from utils.fact_check import build_context_block, llm_verify_against_materials

logger = logging.getLogger(__name__)

_DEFAULT_SECTIONS = ["자기소개", "경력사항", "프로젝트", "기술스택", "교육"]


class ResumeGraphState(TypedDict):
    # 입력
    materials: list[ResumeMaterial]
    job_post: JobPost
    # 노드 산출물
    normalized_materials: list[dict]       # [{type, content, material_id, keywords}]
    job_requirements: dict                 # {required_skills, preferred_skills, experience_years, education, key_emphases}
    material_mapping: dict                 # {section_name: [material_id_or_index, ...]}
    resume_structure: list[str]            # 섹션 순서
    section_drafts: dict                   # {section_name: draft_text}
    verification_issues: dict              # {section_name: [issue, ...]}
    sections_passed: list[str]
    sections_failed: list[str]
    format_valid: bool
    format_errors: list[str]
    # 루프 제어
    retry_count: int
    max_retries: int
    # 출력
    final_resume: str


def _get_verifier_llm():
    return ChatGroq(
        api_key=os.getenv("GROQ_API_KEY"),
        model=os.getenv("VERIFY_MODEL", "gemma2-9b-it"),
        temperature=0.0,
    )


def _parse_json_obj(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return {}


def _parse_json_list(text: str) -> list:
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return []


# Node 1: 소재 정규화
async def normalize_materials(state: ResumeGraphState) -> dict:
    """소재별로 핵심 키워드를 추출하여 정규화된 구조를 만든다."""
    llm = get_llm_client(temperature=0.1)
    normalized = []

    for m in state["materials"]:
        prompt = (
            f"소재 유형: {m.material_type}\n소재 내용: {m.content}\n\n"
            "위 소재에서 이력서에 활용할 핵심 역량 키워드를 최대 5개 추출하라. "
            "각 줄에 하나씩, 설명 없이 키워드만 나열하라."
        )
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        lines = [re.sub(r"^[\-\*\d\.\s]+", "", l).strip() for l in resp.content.splitlines() if l.strip()]
        keywords = [l for l in lines if l][:5]
        normalized.append({
            "type": m.material_type,
            "content": m.content,
            "material_id": m.material_id,
            "keywords": keywords,
        })

    return {"normalized_materials": normalized}


# Node 2: 공고 요구사항 추출
async def extract_job_requirements(state: ResumeGraphState) -> dict:
    """채용 공고에서 구조화된 요구사항을 추출한다."""
    llm = get_llm_client(temperature=0.0)
    job = state["job_post"]

    prompt = (
        f"공고 설명: {job.description}\n"
        f"경력 조건: {job.experience_text}\n"
        f"학력 조건: {job.education_text}\n"
        f"고용 형태: {job.employment_type}\n\n"
        "위 채용 공고를 분석하여 아래 JSON 형식으로만 답하라 (다른 텍스트 없음):\n"
        '{"required_skills": [], "preferred_skills": [], '
        '"experience_years": "", "education": "", "key_emphases": []}'
    )

    resp = await llm.ainvoke([HumanMessage(content=prompt)])
    requirements = _parse_json_obj(resp.content)
    return {"job_requirements": requirements}


# Node 3: 소재-공고 매핑
async def map_materials_to_sections(state: ResumeGraphState) -> dict:
    """정규화된 소재를 이력서 섹션별로 배치한다."""
    llm = get_llm_client(temperature=0.1)
    normalized = state["normalized_materials"]
    requirements = state["job_requirements"]

    materials_text = "\n".join(
        f"[소재{i + 1}] 유형={m['type']}, 키워드={m['keywords']}"
        for i, m in enumerate(normalized)
    )
    req_skills = requirements.get("required_skills", [])

    prompt = (
        f"[공고 필수 기술] {req_skills}\n\n"
        f"[소재 목록]\n{materials_text}\n\n"
        f"위 소재들을 이력서 섹션별로 배치하라. "
        f"섹션명은 {_DEFAULT_SECTIONS} 중에서 선택하라. "
        "소재 번호(소재1, 소재2 형태)를 값으로 사용하라.\n"
        "JSON으로만 답하라 (다른 텍스트 없음):\n"
        '{"섹션명": ["소재1", "소재2"], ...}'
    )

    resp = await llm.ainvoke([HumanMessage(content=prompt)])
    mapping = _parse_json_obj(resp.content)

    # 파싱 실패 시 모든 소재를 기본 섹션에 배치
    if not mapping:
        mapping = {"자기소개": [f"소재{i + 1}" for i in range(len(normalized))]}

    return {"material_mapping": mapping}


# Node 4: 이력서 구조 설계
async def design_resume_structure(state: ResumeGraphState) -> dict:
    """공고 강조점을 반영하여 섹션 순서를 설계한다."""
    llm = get_llm_client(temperature=0.2)
    mapping = state["material_mapping"]
    emphases = state["job_requirements"].get("key_emphases", [])
    mapped_sections = list(mapping.keys())

    if not mapped_sections:
        return {"resume_structure": _DEFAULT_SECTIONS[:]}

    prompt = (
        f"사용 가능한 섹션: {mapped_sections}\n"
        f"공고 강조 역량: {emphases}\n\n"
        "규칙: '자기소개'는 항상 첫 번째. 공고 강조 역량 관련 섹션을 앞에 배치.\n"
        "JSON 배열로만 답하라 (다른 텍스트 없음):\n"
        '["섹션명1", "섹션명2"]'
    )

    resp = await llm.ainvoke([HumanMessage(content=prompt)])
    structure = _parse_json_list(resp.content)

    # LLM 응답에 없는 매핑 섹션 뒤에 추가, 매핑에 없는 섹션 제거
    structure = [s for s in structure if s in mapping]
    for s in mapped_sections:
        if s not in structure:
            structure.append(s)

    return {"resume_structure": structure if structure else mapped_sections}


# Node 5: 섹션별 작성 (재시도 시 실패 섹션만 재작성)
async def write_sections(state: ResumeGraphState) -> dict:
    """각 섹션을 개별 작성한다. retry_count > 0이면 sections_failed만 재작성."""
    llm = get_llm_client(temperature=0.6)

    retry_count = state.get("retry_count", 0)
    sections_to_write = state.get("sections_failed", []) if retry_count > 0 else state["resume_structure"]
    verification_issues = state.get("verification_issues", {})
    drafts = dict(state.get("section_drafts", {}))

    context = build_context_block(state["materials"])
    req_skills = ", ".join(state["job_requirements"].get("required_skills", [])[:5])

    for section in sections_to_write:
        issue_note = ""
        if retry_count > 0 and section in verification_issues:
            issues_text = "\n".join(f"  - {i}" for i in verification_issues[section])
            issue_note = (
                f"\n\n주의: 이전 작성에서 소재에 없는 내용이 감지되었습니다. "
                f"아래 항목을 반드시 제외하십시오:\n{issues_text}"
            )

        prompt = (
            f"[제공된 소재 — 이 내용만 사용할 것]\n{context}\n\n"
            f"[공고 필수 기술/역량]\n{req_skills if req_skills else '없음'}\n\n"
            f"위 소재만 참조하여 이력서의 '{section}' 섹션을 작성하라.\n"
            "- 소재에 없는 내용을 절대 추가하지 마라.\n"
            "- 섹션 제목은 포함하지 말고 본문 내용만 작성하라.\n"
            f"- 한국어로 작성하라.{issue_note}"
        )

        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        drafts[section] = resp.content.strip()

    return {"section_drafts": drafts}


# Node 6: 섹션별 근거 검증
async def verify_sections(state: ResumeGraphState) -> dict:
    """각 섹션 draft를 소재 기반으로 검증한다. 기존 llm_verify_against_materials 재사용."""
    verifier_llm = _get_verifier_llm()
    passed, failed, issues = [], [], {}

    for section, draft in state["section_drafts"].items():
        is_pass, section_issues = await llm_verify_against_materials(
            draft, state["materials"], verifier_llm
        )
        if is_pass:
            passed.append(section)
        else:
            failed.append(section)
            issues[section] = section_issues

    return {
        "verification_issues": issues,
        "sections_passed": passed,
        "sections_failed": failed,
    }


# Node 7: 포맷 검증 (LLM 없음, 순수 Python)
def validate_format(state: ResumeGraphState) -> dict:
    """섹션 draft의 형식을 검증한다. 50자 미만이면 부실 섹션으로 판단."""
    errors = []
    format_failed = []

    for section in state["resume_structure"]:
        draft = state["section_drafts"].get(section, "").strip()
        if len(draft) < 50:
            errors.append(f"{section}: 내용 부족 ({len(draft)}자)")
            format_failed.append(section)

    # 포맷 실패 섹션도 재작성 대상에 추가
    all_failed = list(set(state.get("sections_failed", []) + format_failed))

    return {
        "format_valid": len(errors) == 0,
        "format_errors": errors,
        "sections_failed": all_failed,
    }


# Node 8: 실패 섹션 재작성 진입 (retry_count 증가 후 write_sections로 루프백)
async def rewrite_failed_sections(state: ResumeGraphState) -> dict:
    """retry_count를 증가시킨다. 실제 재작성은 write_sections에서 수행."""
    new_count = state.get("retry_count", 0) + 1
    logger.info(
        "rewrite_failed_sections: retry %d/%d, 대상=%s",
        new_count, state.get("max_retries", 2), state.get("sections_failed", []),
    )
    return {"retry_count": new_count}


# Node 9: 최종 합성 (LLM 없음)
def finalize_resume(state: ResumeGraphState) -> dict:
    """섹션 순서대로 draft를 합쳐 이력서 전문을 생성한다."""
    parts = []
    for section in state["resume_structure"]:
        draft = state["section_drafts"].get(section, "").strip()
        if draft:
            parts.append(f"## {section}\n{draft}")
    return {"final_resume": "\n\n".join(parts)}


# 조건부 엣지
def _route_after_verify(state: ResumeGraphState) -> str:
    if not state.get("sections_failed") or state.get("retry_count", 0) >= state.get("max_retries", 2):
        return "format_check"
    return "rewrite"


def _route_after_format(state: ResumeGraphState) -> str:
    if not state.get("format_valid", True) and state.get("retry_count", 0) < state.get("max_retries", 2):
        return "rewrite"
    return "finalize"


def _build_resume_graph() -> CompiledStateGraph:
    graph = StateGraph(ResumeGraphState)

    graph.add_node("normalize_materials",       normalize_materials)
    graph.add_node("extract_job_requirements",  extract_job_requirements)
    graph.add_node("map_materials_to_sections", map_materials_to_sections)
    graph.add_node("design_resume_structure",   design_resume_structure)
    graph.add_node("write_sections",            write_sections)
    graph.add_node("verify_sections",           verify_sections)
    graph.add_node("validate_format",           validate_format)
    graph.add_node("rewrite_failed_sections",   rewrite_failed_sections)
    graph.add_node("finalize_resume",           finalize_resume)

    graph.add_edge(START,                        "normalize_materials")
    graph.add_edge("normalize_materials",        "extract_job_requirements")
    graph.add_edge("extract_job_requirements",   "map_materials_to_sections")
    graph.add_edge("map_materials_to_sections",  "design_resume_structure")
    graph.add_edge("design_resume_structure",    "write_sections")
    graph.add_edge("write_sections",             "verify_sections")

    graph.add_conditional_edges(
        "verify_sections",
        _route_after_verify,
        {"format_check": "validate_format", "rewrite": "rewrite_failed_sections"},
    )
    graph.add_edge("rewrite_failed_sections", "write_sections")

    graph.add_conditional_edges(
        "validate_format",
        _route_after_format,
        {"finalize": "finalize_resume", "rewrite": "rewrite_failed_sections"},
    )
    graph.add_edge("finalize_resume", END)

    return graph.compile()


_resume_graph: CompiledStateGraph = _build_resume_graph()


async def fix_resume_graph(
    materials: list[ResumeMaterial],
    job_post: JobPost,
) -> ResumeFixResponse:
    """LangGraph 9단계 파이프라인. 기존 fix_resume()과 동일 입출력 스키마."""
    initial_state: ResumeGraphState = {
        "materials":            materials,
        "job_post":             job_post,
        "normalized_materials": [],
        "job_requirements":     {},
        "material_mapping":     {},
        "resume_structure":     [],
        "section_drafts":       {},
        "verification_issues":  {},
        "sections_passed":      [],
        "sections_failed":      [],
        "format_valid":         False,
        "format_errors":        [],
        "retry_count":          0,
        "max_retries":          2,
        "final_resume":         "",
    }

    try:
        final_state = await _resume_graph.ainvoke(initial_state)
        result = final_state.get("final_resume", "")
        if not result:
            logger.warning("fix_resume_graph: final_resume 비어있음. 소재 원문 반환.")
            result = "\n\n".join(m.content for m in materials)
        return ResumeFixResponse(revised_resume=result)
    except Exception as e:
        logger.error("fix_resume_graph 실패: %s", e)
        raise

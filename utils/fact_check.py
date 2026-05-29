import json
import re

from langchain_core.messages import HumanMessage
from models.resume import ResumeMaterial


def build_context_block(materials: list[ResumeMaterial]) -> str:
    """
    resume_materials 리스트를 시스템 프롬프트에 삽입할 컨텍스트 블록으로 변환한다.
    material_type별로 그룹화하여 구조화된 텍스트로 반환.
    """
    grouped: dict[str, list[str]] = {}
    for m in materials:
        grouped.setdefault(m.material_type, []).append(m.content)

    lines = ["[제공된 소재 — 이 내용만 참조하여 작성할 것]"]
    for mtype, contents in grouped.items():
        lines.append(f"\n## {mtype}")
        for i, c in enumerate(contents, 1):
            lines.append(f"{i}. {c}")
    return "\n".join(lines)


async def llm_verify_against_materials(
    suggested_text: str,
    materials: list[ResumeMaterial],
    verifier_llm,
) -> tuple[bool, list[str]]:
    """
    검증 LLM(Gemma)을 사용해 suggested_text에 소재에 없는 날조가 있는지 확인한다.
    반환: (is_pass, issues)
      - PASS: (True, [])
      - 날조 감지: (False, ["감지된 항목1", ...])
    """
    if not materials:
        return True, []

    context = build_context_block(materials)
    prompt = f"""[소재 원문]
{context}

[검토 대상 텍스트]
{suggested_text}

[판정 기준]
날조로 판정하는 경우 (둘 중 하나에 해당할 때만):
  1. 소재에 있는 수치·날짜·고유명사가 다른 값으로 바뀐 경우 (예: 35% → 40%)
  2. 소재 어디에도 없는 완전히 새로운 경력·기술·자격증·수치가 추가된 경우

날조가 아닌 경우 (판정하지 말 것):
  - 소재 내용을 다른 문장 구조나 표현으로 자연스럽게 다듬은 것
  - 이력서 문체에 맞게 소재를 요약하거나 강조한 것

날조가 없으면 정확히 "PASS"라고만 답하라.
날조가 있으면 해당 항목명과 원문-변형 값을 간결하게 나열하라."""

    response = await verifier_llm.ainvoke([HumanMessage(content=prompt)])
    answer = response.content.strip()

    # "PASS", "날조가 없습니다", "날조 없음" 등 다양한 통과 표현 처리
    answer_lower = answer.lower()
    if (
        answer_lower == "pass"
        or "날조가 없" in answer
        or "날조 없음" in answer and "날조로 판정" not in answer
    ):
        return True, []

    issues = [line.lstrip("- •✓").strip() for line in answer.splitlines() if line.strip() and line.strip() != "✓"]
    return False, issues if issues else [answer]


async def extract_fact_tokens(
    materials: list[ResumeMaterial], llm
) -> dict[str, str]:
    """
    소재에서 절대 변경하면 안 되는 팩트를 추출하여 {F1: "값", F2: "값"} 형태로 반환.
    대상: 날짜, 숫자+단위, 회사명·학교명·기술명·자격증명·프로젝트명.
    """
    all_content = "\n".join(
        f"[{m.material_type}] {m.content}" for m in materials
    )
    prompt = (
        f"{all_content}\n\n"
        "위 소재에서 절대 바뀌면 안 되는 팩트 데이터를 추출하라.\n"
        "대상: 날짜(예: 2023.03, 2022년 6월), 수치+단위(예: 30%, 5억원, 3개월),\n"
        "      고유명사(회사명, 학교명, 기술명, 자격증명, 프로젝트명).\n"
        "중복 없이 JSON 배열로만 답하라 (다른 텍스트 없음):\n"
        '["팩트1", "팩트2", ...]'
    )
    resp = await llm.ainvoke([HumanMessage(content=prompt)])
    text = resp.content.strip()

    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1:
        try:
            facts: list[str] = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            facts = []
    else:
        facts = []

    return {f"F{i + 1}": v for i, v in enumerate(facts) if v.strip()}


def mask_materials(
    materials: list[ResumeMaterial], fact_map: dict[str, str]
) -> list[ResumeMaterial]:
    """
    소재 content 내 팩트 값을 [F1], [F2]... 기호로 치환한 새 소재 리스트 반환.
    긴 값부터 먼저 치환하여 부분 치환(예: "삼성"이 "삼성전자" 앞에 치환되는 문제) 방지.
    """
    sorted_items = sorted(fact_map.items(), key=lambda kv: len(kv[1]), reverse=True)
    masked = []
    for m in materials:
        content = m.content
        for key, val in sorted_items:
            content = content.replace(val, f"[{key}]")
        masked.append(
            ResumeMaterial(
                material_type=m.material_type,
                content=content,
                material_id=m.material_id,
            )
        )
    return masked


def unmask_text(text: str, fact_map: dict[str, str]) -> str:
    """생성된 텍스트의 [F1]... 기호를 원본 팩트 값으로 복원."""
    for key, val in fact_map.items():
        text = text.replace(f"[{key}]", val)
    # 혹시 중괄호 없이 F1 형태로 쓰인 경우도 처리
    for key, val in fact_map.items():
        text = re.sub(rf"\b{re.escape(key)}\b", val, text)
    return text


def verify_facts_present(
    text: str, masked_text: str, fact_map: dict[str, str]
) -> tuple[bool, list[str]]:
    """
    LLM이 실제로 사용한 팩트([Fx] 토큰이 masked_text에 등장한 것)만 최종 텍스트에서 검사.
    미사용 소재의 팩트는 검사하지 않아 false positive 누락 판정을 방지.
    반환: (모두_존재, 누락된_값_목록)
    """
    used_keys = {key for key in fact_map if f"[{key}]" in masked_text}
    missing = [fact_map[key] for key in used_keys if fact_map[key] not in text]
    return len(missing) == 0, missing

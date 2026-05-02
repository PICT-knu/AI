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

지침: 위 소재 원문에 근거가 있는 내용은 ✓, 소재에 없는 내용(경력·기술·수치 등 날조)은 항목명과 함께 나열하라. 날조가 없으면 정확히 "PASS"라고만 답하라."""

    response = await verifier_llm.ainvoke([HumanMessage(content=prompt)])
    answer = response.content.strip()

    if answer.upper() == "PASS":
        return True, []

    issues = [line.lstrip("- •✓").strip() for line in answer.splitlines() if line.strip() and line.strip() != "✓"]
    return False, issues if issues else [answer]

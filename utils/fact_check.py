import re
from models.resume import ResumeMaterial
# 단순한 RAG 로직

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


def _tokenize(text: str) -> set[str]:
    """간단한 토큰화: 한글 단어, 영문 단어, 숫자 추출."""
    return set(re.findall(r"[가-힣A-Za-z0-9]+", text))


def verify_against_materials(suggested_text: str, materials: list[ResumeMaterial]) -> bool:
    """
    suggested_text의 핵심 명사/수치가 materials 원문 중 하나에서 유래했는지 확인한다.
    - 전체 materials를 합친 토큰 집합과 교집합이 임계값 이상이면 통과.
    - 빈 materials는 검증 불가이므로 True를 반환한다 (상위에서 처리).
    """
    if not materials:
        return True

    all_material_tokens: set[str] = set()
    for m in materials:
        all_material_tokens |= _tokenize(m.content)

    suggested_tokens = _tokenize(suggested_text)
    if not suggested_tokens:
        return True

    overlap = suggested_tokens & all_material_tokens
    ratio = len(overlap) / len(suggested_tokens)

    # 30% 이상의 토큰이 materials에서 유래했으면 통과
    return ratio >= 0.3

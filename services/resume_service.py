import json
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from models import (
    ResumeMaterial,
    JobPost,
    ResumeFixResponse,
    ResumeChatResponse,
    ChangeItem,
)
from services.llm_client import get_llm_client
from services.session_store import session_store
from utils.fact_check import build_context_block

# 챗봇 세션의 토큰 예산 임계값 (메시지 수 기준 단순화)
_MAX_HISTORY_MESSAGES = 20
_SUMMARY_KEEP_MESSAGES = 6  # 요약 후 최신 N개 메시지만 유지


# 디폴트모드 이력서 작성 시스템 프롬프트 생성
def _build_fix_system_prompt(materials: list[ResumeMaterial], job_post: JobPost) -> str:
    context = build_context_block(materials)
    return f"""당신은 전문 이력서 작성 AI입니다.
아래에 제공된 소재(resume_materials)만을 사용하여 채용 공고에 최적화된 이력서 전문을 작성하십시오.
제공된 소재에 없는 내용을 추가하거나 지어내지 마십시오.

{context}

[채용 공고 정보]
- 공고 설명: {job_post.description}
- 경력 조건: {job_post.experience_text}
- 학력 조건: {job_post.education_text}
- 고용 형태: {job_post.employment_type}

지시사항:
1. 제공된 소재 이외의 내용을 절대 추가하지 마십시오.
2. 공고의 요구 역량에 맞는 소재를 강조하십시오.
3. 완성된 이력서 전문을 반환하십시오."""


# 챗봇모드 이력서 작성 시스템 프롬프트 생성
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


# AI 기억 압축 : 이전 대화 요약과 최신 메시지만 유지
async def _summarize_history(history: list[dict], llm) -> list[dict]:
    """
    대화 이력이 임계값을 초과하면 앞부분을 요약하고 최신 메시지만 유지한다.
    """
    old = history[:-_SUMMARY_KEEP_MESSAGES]
    recent = history[-_SUMMARY_KEEP_MESSAGES:]

    summary_prompt = "다음 대화 이력을 한국어로 간결하게 요약하십시오:\n\n"
    for msg in old:
        summary_prompt += f"{msg['role'].upper()}: {msg['content']}\n"

    summary_msg = await llm.ainvoke([HumanMessage(content=summary_prompt)])
    summary_text = f"[이전 대화 요약]\n{summary_msg.content}"

    return [{"role": "system", "content": summary_text}] + recent


# 디폴트모드 실행 함수
async def fix_resume(
    materials: list[ResumeMaterial], job_post: JobPost
) -> ResumeFixResponse:
    """이력서 자동 생성 (Default Mode, Stateless). temperature: 0.6."""
    llm = get_llm_client(temperature=0.6)
    system_prompt = _build_fix_system_prompt(materials, job_post)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content="위 소재와 채용 공고를 바탕으로 이력서 전문을 작성해 주십시오."),
    ]

    response = await llm.ainvoke(messages)
    return ResumeFixResponse(revised_resume=response.content)


# 챗봇모드 실행 함수
async def chat_resume(
    session_id: str | None,
    user_message: str,
    materials: list[ResumeMaterial],
    job_post: JobPost | None,
) -> ResumeChatResponse:
    """챗봇 교정 모드 (Session-based). temperature: 0.6."""
    llm = get_llm_client(temperature=0.6)
    system_prompt = _build_chat_system_prompt(materials, job_post)

    # 세션 처리
    if not session_id or not session_store.exists(session_id):
        session_id = session_store.create_session()

    history = session_store.get_history(session_id)

    # 토큰 예산 초과 시 요약(과거 메시지 요약)
    if len(history) > _MAX_HISTORY_MESSAGES:
        history = _summarize_history(history, llm)
        # 요약된 이력을 세션에 덮어쓰기
        session_store.delete(session_id)
        session_id = session_store.create_session()
        for msg in history:
            session_store.append(session_id, msg["role"], msg["content"])

    # 메시지 조립
    messages = [SystemMessage(content=system_prompt)]
    for msg in history: #과거 메시지(최근 6개 대화)
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
        else:
            messages.append(SystemMessage(content=msg["content"]))
    messages.append(HumanMessage(content=user_message)) #현재 메시지

    response = await llm.ainvoke(messages)
    ai_text = response.content

    # 대화 이력 저장
    session_store.append(session_id, "user", user_message)
    session_store.append(session_id, "assistant", ai_text)

    # JSON 파싱
    changes = _parse_changes(ai_text)
    return ResumeChatResponse(session_id=session_id, changes=changes)


# JSON 추출 
def _extract_json(text: str) -> str:
    """
    LLM 응답에서 JSON 객체 부분만 추출한다.
    1) 코드 블록(```json ... ```) 안의 내용 우선 추출
    2) 없으면 첫 번째 { 부터 마지막 } 까지 슬라이싱
    """
    import re

    # 코드 블록 안의 JSON 추출
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_block:
        return code_block.group(1)

    # 앞뒤 텍스트를 무시하고 첫 { ~ 마지막 } 추출
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    return text

# JSON을 파이썬이 이해할 수 있도록 ChangeItem 리스트로 변환
def _parse_changes(text: str) -> list[ChangeItem]:
    """추출된 JSON 문자열을 분석(Parsing)하여 ChangeItem 객체 리스트로 변환한다"""
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

import os
from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

load_dotenv('config.env')   # 공개 설정 (git 추적)
load_dotenv(override=True)  # API 키 (.env, gitignore) — 같은 변수명이면 .env 우선


def get_llm_client(temperature: float = 0.6) -> BaseChatModel: #temperature 변경 시 정확도와 창의성의 비율을 조절 가능
    """
    LLM_PROVIDER 환경변수에 따라 Groq 또는 OpenRouter 클라이언트를 반환한다.
    - groq: llama-3.3-70b-versatile
    - openrouter (기본): OPENROUTER_MODEL (기본 google/gemini-2.5-flash)
    """
    provider = os.getenv("LLM_PROVIDER", "openrouter").lower()

    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY가 .env에 설정되지 않았습니다.")
        return ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            model=model,
            temperature=temperature,
            timeout=120,
        )

    api_key = os.getenv("GROQ_API_KEY")
    groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    if not api_key:
        raise ValueError("GROQ_API_KEY가 .env에 설정되지 않았습니다.")
    return ChatGroq(
        api_key=api_key,
        model=groq_model,
        temperature=temperature,
        request_timeout=120,
    )


def get_light_llm_client(temperature: float = 0.1) -> BaseChatModel:
    """
    Planner 등 창의성이 덜 필요한 경량 단계 전용 클라이언트.
    - openrouter: OPENROUTER_LIGHT_MODEL (기본 google/gemini-2.5-flash-lite)
    - groq:       GROQ_LIGHT_MODEL       (없으면 GROQ_MODEL 사용)
    """
    provider = os.getenv("LLM_PROVIDER", "openrouter").lower()

    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = os.getenv("OPENROUTER_LIGHT_MODEL", "google/gemini-2.5-flash-lite")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY가 .env에 설정되지 않았습니다.")
        return ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            model=model,
            temperature=temperature,
            timeout=120,
        )

    api_key = os.getenv("GROQ_API_KEY")
    groq_model = os.getenv("GROQ_LIGHT_MODEL") or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    if not api_key:
        raise ValueError("GROQ_API_KEY가 .env에 설정되지 않았습니다.")
    return ChatGroq(
        api_key=api_key,
        model=groq_model,
        temperature=temperature,
        request_timeout=120,
    )


def get_matching_llm_client(temperature: float = 0.1) -> BaseChatModel:
    """
    공고 매칭(적합도 점수 산출) 전용 클라이언트.
    생성/챗봇 모델(Gemini)과 의도적으로 다른 모델을 사용한다.
    - openrouter: OPENROUTER_MATCHING_MODEL (기본 deepseek/deepseek-chat)
    - groq:       GROQ_MODEL               (보조 경로)
    """
    provider = os.getenv("LLM_PROVIDER", "openrouter").lower()

    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = os.getenv("OPENROUTER_MATCHING_MODEL", "deepseek/deepseek-chat")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY가 .env에 설정되지 않았습니다.")
        return ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            model=model,
            temperature=temperature,
            timeout=120,
        )

    api_key = os.getenv("GROQ_API_KEY")
    groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    if not api_key:
        raise ValueError("GROQ_API_KEY가 .env에 설정되지 않았습니다.")
    return ChatGroq(
        api_key=api_key,
        model=groq_model,
        temperature=temperature,
        request_timeout=120,
    )


def get_verifier_llm_client() -> BaseChatModel:
    """
    할루시네이션 검증 전용 클라이언트 (temperature=0.0 고정).
    생성 모델과 다른 소형 모델을 사용해 Self-Verification Bias 감소.
    - openrouter: VERIFY_MODEL (기본: google/gemini-2.5-flash-lite)
    - groq:       VERIFY_MODEL (기본: llama-3.1-8b-instant)
    """
    provider = os.getenv("LLM_PROVIDER", "openrouter").lower()

    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = os.getenv("VERIFY_MODEL", "google/gemini-2.5-flash-lite")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY가 .env에 설정되지 않았습니다.")
        return ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            model=model,
            temperature=0.0,
            timeout=120,
        )

    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("VERIFY_MODEL", "llama-3.1-8b-instant")
    if not api_key:
        raise ValueError("GROQ_API_KEY가 .env에 설정되지 않았습니다.")
    return ChatGroq(
        api_key=api_key,
        model=model,
        temperature=0.0,
        request_timeout=120,
    )

import os
from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

load_dotenv('config.env')   # 공개 설정 (git 추적)
load_dotenv(override=True)  # API 키 (.env, gitignore) — 같은 변수명이면 .env 우선

FREE_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemini-2.5-flash:free",
    "qwen/qwen-2.5-72b-instruct:free",
]


def _openrouter_fallbacks(temperature: float) -> list[BaseChatModel]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return []
    return [
        ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            model=m,
            temperature=temperature,
            timeout=120,
        )
        for m in FREE_MODELS
    ]


def get_llm_client(temperature: float = 0.6) -> BaseChatModel: #temperature 변경 시 정확도와 창의성의 비율을 조절 가능
    """
    LLM_PROVIDER 환경변수에 따라 Groq 또는 OpenRouter 클라이언트를 반환한다.
    - groq (기본): llama-3.3-70b-versatile
    - openrouter: OPENROUTER_MODEL 환경변수에 지정된 모델
    """
    provider = os.getenv("LLM_PROVIDER", "groq").lower() #LLM_PROVIDER 환경변수가 없으면 기본값으로 "groq" 사용

    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = os.getenv("OPENROUTER_MODEL", FREE_MODELS[0])
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY가 .env에 설정되지 않았습니다.")
        primary = ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            model=model,
            temperature=temperature,
            timeout=120,
        )
        fallbacks = _openrouter_fallbacks(temperature)
        return primary.with_fallbacks(fallbacks) if fallbacks else primary

    # 기본값: groq
    api_key = os.getenv("GROQ_API_KEY")
    groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    if not api_key:
        raise ValueError("GROQ_API_KEY가 .env에 설정되지 않았습니다.")
    primary = ChatGroq(
        api_key=api_key,
        model=groq_model,
        temperature=temperature,
        request_timeout=120,
    )
    fallbacks = _openrouter_fallbacks(temperature)
    return primary.with_fallbacks(fallbacks) if fallbacks else primary


def get_light_llm_client(temperature: float = 0.1) -> BaseChatModel:
    """
    Planner 등 창의성이 덜 필요한 단계 전용 경량 클라이언트.
    - openrouter: OPENROUTER_LIGHT_MODEL (없으면 OPENROUTER_MODEL 사용)
    - groq:       GROQ_LIGHT_MODEL       (없으면 GROQ_MODEL 사용)
    .env에서 저렴한 모델로 교체 가능. 미설정 시 기본 모델과 동일하게 동작.
    """
    provider = os.getenv("LLM_PROVIDER", "groq").lower()

    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = os.getenv("OPENROUTER_LIGHT_MODEL") or os.getenv("OPENROUTER_MODEL", FREE_MODELS[0])
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY가 .env에 설정되지 않았습니다.")
        primary = ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            model=model,
            temperature=temperature,
            timeout=120,
        )
        fallbacks = _openrouter_fallbacks(temperature)
        return primary.with_fallbacks(fallbacks) if fallbacks else primary

    api_key = os.getenv("GROQ_API_KEY")
    groq_model = os.getenv("GROQ_LIGHT_MODEL") or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    if not api_key:
        raise ValueError("GROQ_API_KEY가 .env에 설정되지 않았습니다.")
    primary = ChatGroq(
        api_key=api_key,
        model=groq_model,
        temperature=temperature,
        request_timeout=120,
    )
    fallbacks = _openrouter_fallbacks(temperature)
    return primary.with_fallbacks(fallbacks) if fallbacks else primary


def get_verifier_llm_client() -> BaseChatModel:
    """
    할루시네이션 검증 전용 클라이언트 (temperature=0.0 고정).
    생성 모델과 다른 소형 모델을 사용해 Self-Verification Bias 감소.
    - openrouter: VERIFY_MODEL (기본: meta-llama/llama-3.1-8b-instruct)
    - groq:       VERIFY_MODEL (기본: llama-3.1-8b-instant)
    """
    provider = os.getenv("LLM_PROVIDER", "groq").lower()

    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = os.getenv("VERIFY_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY가 .env에 설정되지 않았습니다.")
        primary = ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            model=model,
            temperature=0.0,
            timeout=120,
        )
        fallbacks = _openrouter_fallbacks(0.0)
        return primary.with_fallbacks(fallbacks) if fallbacks else primary

    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("VERIFY_MODEL", "llama-3.1-8b-instant")
    if not api_key:
        raise ValueError("GROQ_API_KEY가 .env에 설정되지 않았습니다.")
    primary = ChatGroq(
        api_key=api_key,
        model=model,
        temperature=0.0,
        request_timeout=120,
    )
    fallbacks = _openrouter_fallbacks(0.0)
    return primary.with_fallbacks(fallbacks) if fallbacks else primary

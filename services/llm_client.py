import os
from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

load_dotenv()


def get_llm_client(temperature: float = 0.6) -> BaseChatModel:
    """
    LLM_PROVIDER 환경변수에 따라 Groq 또는 OpenRouter 클라이언트를 반환한다.
    - groq (기본): llama-3.3-70b-versatile
    - openrouter: OPENROUTER_MODEL 환경변수에 지정된 모델
    """
    provider = os.getenv("LLM_PROVIDER", "groq").lower()

    if provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-opus-4")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY가 .env에 설정되지 않았습니다.")
        return ChatOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            model=model,
            temperature=temperature,
        )

    # 기본값: groq
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY가 .env에 설정되지 않았습니다.")
    return ChatGroq(
        api_key=api_key,
        model="llama-3.3-70b-versatile",
        temperature=temperature,
    )

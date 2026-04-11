import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any


class SessionStore(ABC):
    """세션 스토어 추상 인터페이스. RedisSessionStore로 교체 가능."""

    @abstractmethod
    def create_session(self) -> str:
        ...

    @abstractmethod
    def get_history(self, session_id: str) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def append(self, session_id: str, role: str, content: str) -> None:
        ...

    @abstractmethod
    def delete(self, session_id: str) -> None:
        ...

    @abstractmethod
    def exists(self, session_id: str) -> bool:
        ...


class InMemorySessionStore(SessionStore):
    """
    인메모리 세션 스토어 (개발/테스트용).
    TTL 만료 시 세션 자동 삭제.
    """

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._store: dict[str, list[dict[str, Any]]] = {}
        self._expires_at: dict[str, datetime] = {}
        self._ttl = timedelta(seconds=ttl_seconds)

    def _is_expired(self, session_id: str) -> bool:
        exp = self._expires_at.get(session_id)
        return exp is None or datetime.utcnow() > exp

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        self._store[session_id] = []
        self._expires_at[session_id] = datetime.utcnow() + self._ttl
        return session_id

    def get_history(self, session_id: str) -> list[dict[str, Any]]:
        if self._is_expired(session_id):
            self.delete(session_id)
            return []
        return list(self._store.get(session_id, []))

    def append(self, session_id: str, role: str, content: str) -> None:
        if self._is_expired(session_id):
            self.delete(session_id)
            return
        self._store.setdefault(session_id, []).append({"role": role, "content": content})
        # 접근 시 TTL 갱신
        self._expires_at[session_id] = datetime.utcnow() + self._ttl

    def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)
        self._expires_at.pop(session_id, None)

    def exists(self, session_id: str) -> bool:
        return session_id in self._store and not self._is_expired(session_id)


# 애플리케이션 전역 싱글턴
import os
from dotenv import load_dotenv

load_dotenv()
_ttl = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
session_store: SessionStore = InMemorySessionStore(ttl_seconds=_ttl)

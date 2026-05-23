import os
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any

from dotenv import load_dotenv

load_dotenv()


class SessionStore(ABC):
    """세션 스토어 추상 인터페이스. Redis 등으로 교체 가능."""

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

    @abstractmethod
    def get_or_create(self, session_id: str | None, initial_context: str = "") -> str:
        """
        session_id가 없거나 만료된 경우:
          - session_id가 None이면 UUID 신규 생성
          - session_id가 있으면 해당 ID 그대로 사용 (BE1 숫자 문자열 수용)
          initial_context가 있으면 system 메시지로 히스토리 초기화.
        반환: 실제 사용할 session_id
        """
        ...


class InMemorySessionStore(SessionStore):
    """
    인메모리 세션 스토어 (현재 구현).
    TTL 만료 시 세션 자동 삭제. 서버 재시작 시 세션 초기화.
    향후 Redis로 교체 시 SessionStore 인터페이스만 구현하면 됨.
    """

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._store: dict[str, list[dict[str, Any]]] = {}
        self._expires_at: dict[str, datetime] = {}
        self._ttl = timedelta(seconds=ttl_seconds)

    def _is_expired(self, session_id: str) -> bool:
        exp = self._expires_at.get(session_id)
        return exp is None or datetime.utcnow() > exp

    def _init_session(self, session_id: str, initial_context: str = "") -> None:
        history: list[dict[str, Any]] = []
        if initial_context:
            history.append({"role": "system", "content": initial_context})
        self._store[session_id] = history
        self._expires_at[session_id] = datetime.utcnow() + self._ttl

    def get_or_create(self, session_id: str | None, initial_context: str = "") -> str:
        """
        BE1이 전달한 session_id(숫자 문자열 등)를 그대로 수용.
        session_id가 None이거나 만료된 경우 새 세션 초기화.
        새 세션 생성 시 session_id가 None이면 UUID 발급, 아니면 전달받은 ID 재사용.
        """
        sid = session_id if session_id else str(uuid.uuid4())
        if not self.exists(sid):
            self._init_session(sid, initial_context)
        return sid

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
        self._expires_at[session_id] = datetime.utcnow() + self._ttl

    def delete(self, session_id: str) -> None:
        self._store.pop(session_id, None)
        self._expires_at.pop(session_id, None)

    def exists(self, session_id: str) -> bool:
        return session_id in self._store and not self._is_expired(session_id)


_ttl = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
session_store: SessionStore = InMemorySessionStore(ttl_seconds=_ttl)

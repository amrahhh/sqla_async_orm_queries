from contextvars import ContextVar
from sqlalchemy.ext.asyncio import AsyncSession


session_context: ContextVar[AsyncSession] = ContextVar("session_context")


def get_session() -> AsyncSession:
    return session_context.get()


def set_session(session: AsyncSession) -> None:
    return session_context.set(session)

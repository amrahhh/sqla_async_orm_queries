from typing import List, TypeVar
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.sql.elements import BinaryExpression

SessionLocal = None
INITIALIZED = False

TModels = TypeVar("TModels", bound="Model")


def init_session(session: AsyncSession):
    global SessionLocal, INITIALIZED
    if isinstance(session, (async_sessionmaker, sessionmaker)) and issubclass(
        session.class_, AsyncSession
    ):
        SessionLocal = session
        INITIALIZED = True
        return True
    raise TypeError("You need to use SQLAlchemy `AsyncSession`")


class Base(DeclarativeBase, AsyncAttrs):
    pass


class Model(Base):
    __abstract__ = True

    @classmethod
    async def create(cls, data: dict):
        async with SessionLocal() as session:
            try:
                data = cls(**data)
                session.add(data)
                await session.commit()
                return data
            except Exception as e:
                await session.rollback()
                raise e

    @classmethod
    async def select_one(cls, *args: BinaryExpression):
        async with SessionLocal() as session:
            result = await session.execute(select(cls).where(*args))
            data = result.scalar()
            return data

    @classmethod
    async def select_all(cls, *args: BinaryExpression):
        async with SessionLocal() as session:
            result = await session.execute(select(cls).where(*args))
            data = result.scalars().all()
            return data

    @classmethod
    async def update(cls, data: dict, *args: BinaryExpression):
        async with SessionLocal() as session:
            try:
                query = update(cls).where(*args).values(**data).returning(cls.id)
                db_data = await session.execute(query)
                db_data = db_data.scalar()
                await session.commit()
                return db_data
            except Exception as e:
                await session.rollback()
                raise e

    @classmethod
    async def delete(cls, *args: BinaryExpression):
        async with SessionLocal() as session:
            try:
                query = delete(cls).where(*args)
                db_data = await session.execute(query)
                await session.commit()
                return db_data
            except Exception as e:
                await session.rollback()
                raise e

    @classmethod
    async def select_with_pagination(
        cls, *args: BinaryExpression, page: int = 1, size: int = 10
    ):
        async with SessionLocal() as session:
            query = select(cls).where(*args).offset((page - 1) * size).limit(size)
            result = await session.execute(query)
            data = result.scalars().all()
            return data

    async def apply(self):
        async with SessionLocal() as session:
            try:
                session.add(self)
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e

    @classmethod
    async def apply_all(self, models: List[TModels]):
        async with SessionLocal() as session:
            try:
                session.add_all(models)
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e

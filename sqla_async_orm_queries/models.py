from typing import List, TypeVar, Callable
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker
from sqlalchemy.orm import (
    DeclarativeBase,
    sessionmaker,
    selectinload
)
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


class Base(AsyncAttrs,DeclarativeBase):
    pass


class Model(Base):
    __abstract__ = True

    @classmethod
    def _build_loader(cls, loader_fields: list[str], loader_func: Callable = None):
        if loader_func is None:
            loader_func = selectinload
        loaders = [loader_func(getattr(cls, i)) for i in loader_fields]
        return loaders

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
    async def select_one(
        cls,
        *args: BinaryExpression,
        load_with: list[str] = None,
        loader_func: Callable = None
    ):
        loaders = []
        async with SessionLocal() as session:
            if load_with:
                loaders = cls._build_loader(load_with, loader_func)
            result = await session.execute(select(cls).where(*args).options(*loaders))
            data = result.scalar()
            return data

    @classmethod
    async def select_all(cls, *args: BinaryExpression,load_with: list[str] = None,loader_func: Callable = None):
        loaders = []
        async with SessionLocal() as session:
            if load_with:
                loaders = cls._build_loader(load_with, loader_func)
            result = await session.execute(select(cls).where(*args).options(*loaders))
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
        cls, *args: BinaryExpression, offset: int = 0, limit: int = 10,load_with: list[str] = None,loader_func: Callable = None
    ):
        if offset < 0: 
            raise Exception("offset can not be a negative")
        async with SessionLocal() as session:
            if load_with:
                loaders = cls._build_loader(load_with, loader_func)
            query = select(cls).where(*args).offset(offset).limit(limit).options(*loaders)
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

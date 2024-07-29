from typing import List, TypeVar, Callable, Union
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker, selectinload
from sqlalchemy.sql.functions import count
from sqlalchemy.sql.elements import BinaryExpression
from sqlalchemy.orm.query import Query
from sqla_async_orm_queries.context import get_session, set_session, session_context

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


class Base(AsyncAttrs, DeclarativeBase):
    pass


class SessionManager:
    def __init__(self, session_factory=None) -> None:
        self.session_factory = session_factory or SessionLocal

    async def __aenter__(self):
        session = self.session_factory()
        await session.begin()
        set_session(session)
        return session

    async def __aexit__(self, exc_type, exc, tb):
        session = get_session()
        if exc_type:
            await session.rollback()
        else:
            await session.commit()
        await session.close()
        set_session(None)


class Model(Base):
    __abstract__ = True

    @staticmethod
    def _order_by(query, order_by):
        if order_by is not None:
            return query.order_by(*order_by)
        return query

    @classmethod
    def _build_loader(cls, loader_fields: list[str], loader_func: Callable = None):
        if loader_func is None:
            loader_func = selectinload
        loaders = [loader_func(getattr(cls, i)) for i in loader_fields]
        return loaders

    @classmethod
    def _build_columns(cls, columns: list[str]):
        return [getattr(cls, i) for i in columns]

    @classmethod
    async def execute_query(
        cls,
        query: Union[Query, str],
        scalar: bool = False,
        all: bool = False,
        session: AsyncSession = None,
    ):
        session = session_context.get(session)
        if session is None:
            async with SessionLocal() as session:
                result = await session.execute(query)
                if scalar and all:
                    data = result.scalars().all()
                elif not scalar and all:
                    data = result.all()
                elif scalar and not all:
                    data = result.scalar()
                else:
                    raise NotImplementedError
                return data
        else:
            result = await session.execute(query)
            if scalar and all:
                data = result.scalars().all()
            elif not scalar and all:
                data = result.all()
            elif scalar and not all:
                data = result.scalar()
            else:
                raise NotImplementedError
            return data

    @classmethod
    async def create(cls, data: dict, session: AsyncSession = None):
        session = session_context.get(session)
        if session is None:
            async with SessionLocal() as session:
                try:
                    data = cls(**data)
                    session.add(data)
                    await session.commit()
                    return data
                except Exception as e:
                    await session.rollback()
                    raise e
        else:
            try:
                data = cls(**data)
                session.add(data)
                return data
            except Exception as e:
                await session.rollback()
                raise e

    @classmethod
    async def select_one(
        cls,
        *args: BinaryExpression,
        order_by: list[str] = None,
        load_with: list[str] = None,
        loader_func: Callable = None,
        columns: list[str] = None,
        session: AsyncSession = None
    ):
        loaders = []
        session = session_context.get(session)
        if session is None:
            async with SessionLocal() as session:
                if load_with:
                    loaders = cls._build_loader(load_with, loader_func)
                if columns:
                    selected_columns = [getattr(cls, col) for col in columns]
                    query = select(*selected_columns).where(*args).options(*loaders)
                else:
                    query = select(cls).where(*args).options(*loaders)

                query = cls._order_by(query, order_by)
                result = await session.execute(query)
                data = result.scalar()

                return data
        else:
            if load_with:
                loaders = cls._build_loader(load_with, loader_func)
            if columns:
                selected_columns = [getattr(cls, col) for col in columns]
                query = select(*selected_columns).where(*args).options(*loaders)
            else:
                query = select(cls).where(*args).options(*loaders)

            query = cls._order_by(query, order_by)
            result = await session.execute(query)
            data = result.scalar()

            return data

    @classmethod
    async def select_all(
        cls,
        *args: BinaryExpression,
        order_by: list[str] = None,
        load_with: list[str] = None,
        loader_func: Callable = None,
        columns: list[str] = None,
        session: AsyncSession = None
    ):
        loaders = []
        session = session_context.get(session)
        if session is None:
            async with SessionLocal() as session:
                if load_with:
                    loaders = cls._build_loader(load_with, loader_func)

                if columns:
                    selected_columns = [getattr(cls, col) for col in columns]
                    query = select(*selected_columns).where(*args).options(*loaders)
                else:
                    query = select(cls).where(*args).options(*loaders)

                query = cls._order_by(query, order_by)
                result = await session.execute(query)
                data = result.scalars().all()

                return data
        else:
            if load_with:
                loaders = cls._build_loader(load_with, loader_func)

            if columns:
                selected_columns = [getattr(cls, col) for col in columns]
                query = select(*selected_columns).where(*args).options(*loaders)
            else:
                query = select(cls).where(*args).options(*loaders)

            query = cls._order_by(query, order_by)
            result = await session.execute(query)
            data = result.scalars().all()

            return data

    @classmethod
    async def update(
        cls, data: dict, *args: BinaryExpression, session: AsyncSession = None
    ):
        session = session_context.get(session)
        if session is None:
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
        else:
            try:
                query = update(cls).where(*args).values(**data).returning(cls.id)
                db_data = await session.execute(query)
                db_data = db_data.scalar()
                return db_data
            except Exception as e:
                await session.rollback()
                raise e

    @classmethod
    async def delete(cls, *args: BinaryExpression, session: AsyncSession = None):
        session = session_context.get(session)
        if session is None:
            async with SessionLocal() as session:
                try:
                    query = delete(cls).where(*args)
                    db_data = await session.execute(query)
                    await session.commit()
                    return db_data
                except Exception as e:
                    await session.rollback()
                    raise e
        else:
            try:
                query = delete(cls).where(*args)
                db_data = await session.execute(query)
                return db_data
            except Exception as e:
                await session.rollback()
                raise e

    @classmethod
    async def get_count(cls, *args: BinaryExpression, session: AsyncSession = None):
        session = session_context.get(session)
        if session is None:
            async with SessionLocal() as session:
                result = await session.execute(select(count(cls.id)).where(*args))
                total_count = result.scalar()
                return total_count
        else:
            result = await session.execute(select(count(cls.id)).where(*args))
            total_count = result.scalar()
            return total_count

    @classmethod
    async def select_with_pagination(
        cls,
        *args: BinaryExpression,
        offset: int = 0,
        limit: int = 10,
        order_by: list[str] = None,
        load_with: list[str] = None,
        loader_func: Callable = None,
        session: AsyncSession = None
    ):
        loaders = []
        if offset < 0:
            raise Exception("offset can not be a negative")
        session = session_context.get(session)
        if session is None:
            async with SessionLocal() as session:
                if load_with:
                    loaders = cls._build_loader(load_with, loader_func)
                query = (
                    select(cls)
                    .where(*args)
                    .offset(offset)
                    .limit(limit)
                    .options(*loaders)
                )
                query = cls._order_by(query, order_by)
                result = await session.execute(query)
                data = result.scalars().all()
                return data
        else:
            if load_with:
                loaders = cls._build_loader(load_with, loader_func)
            query = (
                select(cls).where(*args).offset(offset).limit(limit).options(*loaders)
            )
            query = cls._order_by(query, order_by)
            result = await session.execute(query)
            data = result.scalars().all()
            return data

    async def apply(self, session: AsyncSession = None):
        session = session_context.get(session)
        if session is None:
            async with SessionLocal() as session:
                try:
                    session.add(self)
                    await session.commit()
                except Exception as e:
                    await session.rollback()
                    raise e
        else:
            try:
                session.add(self)
            except Exception as e:
                await session.rollback()
                raise e

    @classmethod
    async def apply_all(self, models: List[TModels], session: AsyncSession = None):
        session = session_context.get(session)
        if session is None:
            async with SessionLocal() as session:
                try:
                    session.add_all(models)
                    await session.commit()
                except Exception as e:
                    await session.rollback()
                    raise e
        else:
            try:
                session.add_all(models)
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e

    @classmethod
    async def select_with_joins(
        cls,
        *args: BinaryExpression,
        join_tables: List[TModels],
        join_conditions: List[BinaryExpression],
        columns: List[str],
        order_by: List[str] = None,
        offset: int = 0,
        limit: int = 10,
        session: AsyncSession = None
    ):
        if offset < 0:
            raise ValueError("Offset cannot be negative")
        session = session_context.get(session)
        if session is None:
            async with SessionLocal() as session:
                query = select(*columns)
                for join_table, condition in zip(join_tables, join_conditions):
                    query = query.join(join_table, condition)
                query = query.where(*args)
                if order_by:
                    query = query.order_by(*order_by)
                query = query.offset(offset).limit(limit)
                result = await session.execute(query)
                data = result.all()
                return data
        else:
            query = select(*columns)
            for join_table, condition in zip(join_tables, join_conditions):
                query = query.join(join_table, condition)
            query = query.where(*args)
            if order_by:
                query = query.order_by(*order_by)
            query = query.offset(offset).limit(limit)
            result = await session.execute(query)
            data = result.all()
            return data

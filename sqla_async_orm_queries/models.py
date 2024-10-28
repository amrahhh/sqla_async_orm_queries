from __future__ import annotations  # For forward references
from typing import List, TypeVar, Callable, Optional, Any, Dict
from sqlalchemy import (
    delete,
    select,
    update,
    func,
    Column,
    Integer,
    String,
    DateTime,
    JSON,
    event,
    Boolean
)
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker
from sqlalchemy.orm import (
    DeclarativeBase,
    selectinload,
    Session,
)
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pydantic import BaseModel as PydanticBaseModel, ValidationError
from functools import wraps
import json

TModels = TypeVar("TModels", bound="Model")


class Base(DeclarativeBase, AsyncAttrs):
    pass


class PydanticModelMixin(PydanticBaseModel):
    class Config:
        from_attributes = True


class SoftDeleteMixin:
    is_deleted = Column(Boolean, default=True)

    @classmethod
    async def soft_delete(cls, *args, session: Optional[AsyncSession] = None):
        await cls.update({"is_deleted": False}, *args, session=session)

def make_serializable(data):
    if isinstance(data, dict):
        return {key: make_serializable(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [make_serializable(item) for item in data]
    elif isinstance(data, datetime):
        return data.isoformat()
    elif hasattr(data, "to_dict"):
        return data.to_dict()
    return data

def transactional(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if 'session' in kwargs and kwargs['session'] is not None:
            return await func(*args, **kwargs)
        else:
            async with cls.get_session() as session:
                try:
                    kwargs['session'] = session
                    result = await func(*args, **kwargs)
                    await session.commit()
                    return result
                except Exception as e:
                    await session.rollback()
                    raise e
    return wrapper

class Model(Base, SoftDeleteMixin):
    __abstract__ = True
    session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    # Define a Pydantic model inside each SQLAlchemy model
    class PydanticModel(PydanticModelMixin):
        pass

    @classmethod
    def init_session(cls, session_factory: async_sessionmaker[AsyncSession]):
        if not isinstance(session_factory, async_sessionmaker):
            raise TypeError(
                "The session_factory must be an instance of async_sessionmaker."
            )
        cls.session_factory = session_factory

    @classmethod
    def _ensure_session_factory(cls):
        if cls.session_factory is None:
            raise RuntimeError(
                "Session factory is not initialized. Call init_session first."
            )

    @staticmethod
    def _order_by(query, order_by, cls):
        if order_by:
            columns = []
            for col in order_by:
                if col.startswith("-"):
                    columns.append(getattr(cls, col[1:]).desc())
                else:
                    columns.append(getattr(cls, col))
            return query.order_by(*columns)
        return query

    @classmethod
    def _build_loader(
        cls, loader_fields: List[str], loader_func: Callable = selectinload
    ):
        loaders = []
        for field in loader_fields:
            if hasattr(cls, field):
                loaders.append(loader_func(getattr(cls, field)))
            else:
                raise AttributeError(f"{cls.__name__} has no attribute '{field}'")
        return loaders

    @classmethod
    @asynccontextmanager
    async def get_session(cls, session: Optional[AsyncSession] = None):
        if session is not None:
            yield session
        else:
            cls._ensure_session_factory()
            async with cls.session_factory() as session:
                async with session.begin():
                    yield session

    @classmethod
    def validate_data(cls, data: dict):
        try:
            cls.PydanticModel(**data)
        except ValidationError as e:
            raise ValueError(f"Validation error: {e.errors()}")

    def to_pydantic(self):
        return self.PydanticModel.model_validate(self)

    @classmethod
    def from_pydantic(cls, pydantic_model):
        return cls(**pydantic_model.dict())

    def to_dict(self, include_relationships=False):
        data = {
            column.name: getattr(self, column.name) for column in self.__table__.columns
        }
        if include_relationships:
            for relation in self.__mapper__.relationships:
                related = getattr(self, relation.key)
                if related is not None:
                    if isinstance(related, list):
                        data[relation.key] = [item.to_dict() for item in related]
                    else:
                        data[relation.key] = related.to_dict()
        return data

    def to_json(self, include_relationships=False):
        return json.dumps(
            self.to_dict(include_relationships=include_relationships),
            default=make_serializable,
        )

    @classmethod
    async def create(cls, data: dict, session: Optional[AsyncSession] = None) -> Model:
        async with cls.get_session(session) as session:
            instance = cls(**data)
            session.add(instance)
            return instance

    @classmethod
    async def bulk_create(
        cls, data_list: List[dict], session: Optional[AsyncSession] = None
    ) -> List[Model]:
        instances = []
        async with cls.get_session(session) as session:
            for data in data_list:
                instance = cls(**data)
                instances.append(instance)
            session.add_all(instances)
        return instances

    @classmethod
    async def select_one(
        cls,
        *args: Any,
        order_by: List[str] = None,
        load_with: List[str] = None,
        loader_func: Callable = selectinload,
        columns: List[str] = None,
        session: Optional[AsyncSession] = None,
        include_inactive=False,
    ) -> Optional[Model]:
        if not include_inactive and hasattr(cls, "is_deleted"):
            args = (*args, cls.is_deleted == True)
        async with cls.get_session(session) as session:
            loaders = cls._build_loader(load_with, loader_func) if load_with else []
            if columns:
                selected_columns = [getattr(cls, col) for col in columns]
                query = select(*selected_columns).options(*loaders)
            else:
                query = select(cls).options(*loaders)
            query = query.where(*args)
            query = cls._order_by(query, order_by, cls)
            result = await session.execute(query)
            return result.one_or_none() if columns else result.scalar_one_or_none()

    @classmethod
    async def select_all(
        cls,
        *args: Any,
        order_by: List[str] = None,
        load_with: List[str] = None,
        loader_func: Callable = selectinload,
        columns: List[str] = None,
        session: Optional[AsyncSession] = None,
        include_inactive=False,
        limit: int = None,
        offset: int = None,
    ) -> List[Model]:
        if not include_inactive and hasattr(cls, "is_deleted"):
            args = (*args, cls.is_deleted == True)
        async with cls.get_session(session) as session:
            loaders = cls._build_loader(load_with, loader_func) if load_with else []
            if columns:
                selected_columns = [getattr(cls, col) for col in columns]
                query = select(*selected_columns).options(*loaders)
            else:
                query = select(cls).options(*loaders)
            query = query.where(*args)
            query = cls._order_by(query, order_by, cls)
            if limit:
                query = query.limit(limit)
            if offset:
                query = query.offset(offset)
            result = await session.execute(query)
            return result.all() if columns else result.scalars().all()

    @classmethod
    async def update(
        cls,
        data: dict,
        *args: Any,
        session: Optional[AsyncSession] = None,
    ) -> List[Any]:
        async with cls.get_session(session) as session:
            query = update(cls).where(*args).values(**data).returning(cls.id)
            result = await session.execute(query)
            return result.scalars().all()

    @classmethod
    async def bulk_update(
        cls,
        data: dict,
        *args: Any,
        session: Optional[AsyncSession] = None,
    ) -> List[Any]:
        async with cls.get_session(session) as session:
            updated_ids = []

            query = update(cls).where(*args).values(**data).returning(cls.id)
            result = await session.execute(query)
            updated_ids.extend(result.scalars().all())
            return updated_ids

    @classmethod
    async def delete(cls, *args: Any, session: Optional[AsyncSession] = None) -> int:
        async with cls.get_session(session) as session:
            query = delete(cls).where(*args)
            result = await session.execute(query)
            return result.rowcount

    @classmethod
    async def bulk_delete(
        cls, conditions_list: List[Any], session: Optional[AsyncSession] = None
    ) -> int:
        async with cls.get_session(session) as session:
            total_deleted = 0
            for conditions in conditions_list:
                query = delete(cls).where(conditions)
                result = await session.execute(query)
                total_deleted += result.rowcount
            return total_deleted

    @classmethod
    async def get_count(cls, *args: Any, session: Optional[AsyncSession] = None) -> int:
        async with cls.get_session(session) as session:
            result = await session.execute(select(func.count(cls.id)).where(*args))
            return result.scalar()

    @classmethod
    async def select_with_pagination(
        cls,
        *args: Any,
        page: int = 1,
        per_page: int = 10,
        order_by: List[str] = None,
        load_with: List[str] = None,
        loader_func: Callable = selectinload,
        session: Optional[AsyncSession] = None,
        include_inactive=False,
    ) -> PaginationResult:
        if page < 1 or per_page < 1:
            raise ValueError("Page and per_page must be positive integers")
        offset = (page - 1) * per_page
        total = await cls.get_count(*args, session=session)
        items = await cls.select_all(
            *args,
            order_by=order_by,
            load_with=load_with,
            loader_func=loader_func,
            session=session,
            offset=offset,
            limit=per_page,
            include_inactive=include_inactive,
        )
        return PaginationResult(items, total, page, per_page)

    @classmethod
    async def transactional(
        cls, operations: Callable, session: Optional[AsyncSession] = None
    ):
        async with cls.get_session(session) as session:
            try:
                await operations(session)
            except Exception as e:
                await session.rollback()
                raise e
            else:
                await session.commit()

    # Dynamic Filters
    @classmethod
    def build_filters(cls, filters: Dict[str, Any]) -> List[Any]:
        conditions = []
        for field, value in filters.items():
            if hasattr(cls, field):
                conditions.append(getattr(cls, field) == value)
            else:
                raise AttributeError(f"{cls.__name__} has no attribute '{field}'")
        return conditions

    @classmethod
    def get_query(cls):
        return select(cls)

    @staticmethod
    def log_operation(mapper, connection, target, operation):
        sync_session = Session(bind=connection)
        data = make_serializable(target.to_dict())
        audit = AuditLog(
            table_name=target.__tablename__,
            operation=operation,
            timestamp=datetime.now(tz=timezone.utc),
            data=data,
        )
        sync_session.add(audit)
        sync_session.flush()

    @classmethod
    def after_insert(cls, mapper, connection, target):
        if hasattr(target, "created_at"):
            target.created_at = datetime.now(tz=timezone.utc)
        cls.log_operation(mapper, connection, target, "insert")

    @classmethod
    def after_update(cls, mapper, connection, target):
        if hasattr(target, "updated_at"):
            target.updated_at = datetime.now(tz=timezone.utc)
        cls.log_operation(mapper, connection, target, "update")

    @classmethod
    def after_delete(cls, mapper, connection, target):
        cls.log_operation(mapper, connection, target, "delete")

    # Attach Event Listeners
    @classmethod
    def attach_listeners(cls):
        event.listen(cls, "after_insert", cls.after_insert)
        event.listen(cls, "after_update", cls.after_update)
        event.listen(cls, "after_delete", cls.after_delete)

    @classmethod
    def detach_listeners(cls):
        event.remove(cls, "after_insert", cls.after_insert)
        event.remove(cls, "after_update", cls.after_update)
        event.remove(cls, "after_delete", cls.after_delete)

    @classmethod
    @contextmanager
    def listeners_disabled(cls):
        cls.detach_listeners()
        try:
            yield
        finally:
            cls.attach_listeners()

    async def save(self, session: Optional[AsyncSession] = None):
        async with self.get_session(session) as session:
            session.add(self)

    async def apply(self, session: Optional[AsyncSession] = None):
        async with self.get_session(session) as session:
            session.add(self)
            # await session.commit()

    @classmethod
    async def save_all(
        cls, models: List[TModels], session: Optional[AsyncSession] = None
    ):
        async with cls.get_session(session) as session:
            for model in models:
                model.validate_data(model.to_dict())
            session.add_all(models)

    @classmethod
    async def execute_query(
        cls,
        query,
        scalar: bool = False,
        all: bool = False,
        session: AsyncSession = None,
    ):
        async with cls.get_session(session) as session:
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


class PaginationResult:
    def __init__(self, items, total, page, per_page):
        self.items = items
        self.total = total
        self.page = page
        self.per_page = per_page

    @property
    def pages(self):
        return (self.total - 1) // self.per_page + 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def has_prev(self):
        return self.page > 1

    def to_dict(self):
        return {
            "items": [item.to_dict() for item in self.items],
            "total": self.total,
            "page": self.page,
            "per_page": self.per_page,
            "pages": self.pages,
            "has_next": self.has_next,
            "has_prev": self.has_prev,
        }


class AuditLog(Model):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    table_name = Column(String)
    operation = Column(String)
    timestamp = Column(DateTime, default=datetime.now(tz=timezone.utc))
    data = Column(JSON)

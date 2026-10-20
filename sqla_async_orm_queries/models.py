from __future__ import annotations  # For forward references

import json
from collections.abc import Callable
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from functools import wraps
from typing import Any, Self, TypeVar

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict, ValidationError
from sqlalchemy import (
	Boolean,
	Column,
	delete,
	event,
	func,
	select,
	update,
)
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker
from sqlalchemy.orm import (
	DeclarativeBase,
	Session,
	selectinload,
)

TModels = TypeVar("TModels", bound="Model")


class Base(DeclarativeBase, AsyncAttrs):
	pass


class PydanticModelMixin(PydanticBaseModel):
	model_config = ConfigDict(from_attributes=True)


class SoftDeleteMixin:
	"""Opt-in soft delete: ``class User(SoftDeleteMixin, Model)``."""

	is_deleted = Column(Boolean(), default=False)

	@classmethod
	async def soft_delete(cls, *args, session: AsyncSession | None = None):
		await cls.update({"is_deleted": True}, *args, session=session)


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
		cls = Model
		if "session" in kwargs and kwargs["session"] is not None:
			return await func(*args, **kwargs)
		else:
			async with cls.get_session() as session:
				try:
					kwargs["session"] = session
					result = await func(*args, **kwargs)
					await session.commit()
					return result
				except Exception:
					await session.rollback()
					raise

	return wrapper


class Model(Base):
	__abstract__ = True
	session_factory: async_sessionmaker[AsyncSession] | None = None

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
			return query.order_by(*order_by)
		return query

	@classmethod
	def _soft_delete_filter(cls, args, include_inactive):
		"""Hide soft-deleted rows unless include_inactive=True."""
		if include_inactive or not hasattr(cls, "is_deleted"):
			return args
		return (*args, cls.is_deleted.is_not(True))

	@classmethod
	def _build_loader(
		cls, loader_fields: list[str], loader_func: Callable = selectinload
	):
		"""Supports nested paths: ``load_with=["images.media"]``."""
		loaders = []
		for field in loader_fields:
			model, loader = cls, None
			for name in field.split("."):
				if not hasattr(model, name):
					raise AttributeError(
						f"{model.__name__} has no attribute '{name}'"
					)
				attr = getattr(model, name)
				loader = (
					loader_func(attr)
					if loader is None
					else getattr(loader, loader_func.__name__)(attr)
				)
				model = attr.property.mapper.class_
			loaders.append(loader)
		return loaders

	@classmethod
	@asynccontextmanager
	async def get_session(cls, session: AsyncSession | None = None):
		if session is not None:
			yield session
		else:
			cls._ensure_session_factory()
			async with cls.session_factory() as session, session.begin():
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
		return cls(**pydantic_model.model_dump())

	def to_dict(self, include_relationships=False):
		data = {
			column.name: getattr(self, column.name)
			for column in self.__table__.columns
		}
		if include_relationships:
			for relation in self.__mapper__.relationships:
				related = getattr(self, relation.key)
				if related is not None:
					if isinstance(related, list):
						data[relation.key] = [
							item.to_dict() for item in related
						]
					else:
						data[relation.key] = related.to_dict()
		return data

	def to_json(self, include_relationships=False):
		return json.dumps(
			self.to_dict(include_relationships=include_relationships),
			default=make_serializable,
		)

	@classmethod
	async def create(
		cls, data: dict, session: AsyncSession | None = None
	) -> Self:
		async with cls.get_session(session) as session:
			instance = cls(**data)
			session.add(instance)
			await session.flush()  # id and defaults are available right away
			return instance

	@classmethod
	async def bulk_create(
		cls, data_list: list[dict], session: AsyncSession | None = None
	) -> list[Self]:
		instances = []
		async with cls.get_session(session) as session:
			for data in data_list:
				instance = cls(**data)
				instances.append(instance)
			session.add_all(instances)
			await session.flush()
		return instances

	@classmethod
	async def select_one(
		cls,
		*args: Any,
		order_by: list[Any] | None = None,
		load_with: list[str] | None = None,
		loader_func: Callable = selectinload,
		columns: list[str] | None = None,
		session: AsyncSession | None = None,
		include_inactive=False,
	) -> Self | None:
		args = cls._soft_delete_filter(args, include_inactive)
		async with cls.get_session(session) as session:
			loaders = (
				cls._build_loader(load_with, loader_func) if load_with else []
			)
			if columns:
				selected_columns = [getattr(cls, col) for col in columns]
				query = select(*selected_columns).options(*loaders)
			else:
				query = select(cls).options(*loaders)
			query = query.where(*args)
			query = cls._order_by(query, order_by, cls)
			query = query.limit(1)
			if columns:
				result = await session.execute(query)
				row = result.first()
				return row
			else:
				result = await session.scalars(query)
				return result.first()

	@classmethod
	async def select_all(
		cls,
		*args: Any,
		order_by: list[Any] | None = None,
		load_with: list[str] | None = None,
		loader_func: Callable = selectinload,
		columns: list[str] | None = None,
		session: AsyncSession | None = None,
		include_inactive=False,
		limit: int | None = None,
		offset: int | None = None,
	) -> list[Self]:
		args = cls._soft_delete_filter(args, include_inactive)
		async with cls.get_session(session) as session:
			loaders = (
				cls._build_loader(load_with, loader_func) if load_with else []
			)
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
			if columns:
				result = await session.execute(query)
				return result.all()
			else:
				result = await session.scalars(query)
				return result.all()

	@classmethod
	async def update(
		cls,
		data: dict,
		*args: Any,
		session: AsyncSession | None = None,
		returning: Any = None,
	) -> list[Any]:
		"""Returns updated ids, or what `returning` asks for: the model
		(updated instances) or columns, e.g. ``returning=[User.name]``."""
		columns = (
			returning
			if isinstance(returning, (list, tuple))
			else [returning or cls.id]
		)
		async with cls.get_session(session) as session:
			query = update(cls).where(*args).values(**data).returning(*columns)
			result = await session.execute(query)
			return (
				result.scalars().all() if len(columns) == 1 else result.all()
			)

	@classmethod
	async def bulk_update(
		cls,
		data: dict,
		*args: Any,
		session: AsyncSession | None = None,
	) -> list[Any]:
		async with cls.get_session(session) as session:
			updated_ids = []

			query = update(cls).where(*args).values(**data).returning(cls.id)
			result = await session.execute(query)
			updated_ids.extend(result.scalars().all())
			return updated_ids

	@classmethod
	async def delete(
		cls, *args: Any, session: AsyncSession | None = None
	) -> int:
		async with cls.get_session(session) as session:
			query = delete(cls).where(*args)
			result = await session.execute(query)
			return result.rowcount

	@classmethod
	async def bulk_delete(
		cls, conditions_list: list[Any], session: AsyncSession | None = None
	) -> int:
		async with cls.get_session(session) as session:
			total_deleted = 0
			for conditions in conditions_list:
				query = delete(cls).where(conditions)
				result = await session.execute(query)
				total_deleted += result.rowcount
			return total_deleted

	@classmethod
	async def get_count(
		cls,
		*args: Any,
		session: AsyncSession | None = None,
		include_inactive=False,
	) -> int:
		args = cls._soft_delete_filter(args, include_inactive)
		async with cls.get_session(session) as session:
			result = await session.execute(
				select(func.count(cls.id)).where(*args)
			)
			return result.scalar()

	@classmethod
	async def select_with_pagination(
		cls,
		*args: Any,
		page: int = 1,
		per_page: int = 10,
		order_by: list[Any] | None = None,
		load_with: list[str] | None = None,
		loader_func: Callable = selectinload,
		session: AsyncSession | None = None,
		include_inactive=False,
	) -> PaginationResult:
		if page < 1 or per_page < 1:
			raise ValueError("Page and per_page must be positive integers")
		offset = (page - 1) * per_page
		total = await cls.get_count(
			*args, session=session, include_inactive=include_inactive
		)
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
		cls, operations: Callable, session: AsyncSession | None = None
	):
		async with cls.get_session(session) as session:
			try:
				await operations(session)
			except Exception:
				await session.rollback()
				raise
			else:
				await session.commit()

	# Dynamic Filters
	@classmethod
	def build_filters(cls, filters: dict[str, Any]) -> list[Any]:
		conditions = []
		for field, value in filters.items():
			if hasattr(cls, field):
				conditions.append(getattr(cls, field) == value)
			else:
				raise AttributeError(
					f"{cls.__name__} has no attribute '{field}'"
				)
		return conditions

	@classmethod
	def get_query(cls):
		return select(cls)

	@staticmethod
	def log_operation(mapper, connection, target, operation):
		# Opt-in: the audit module is only loaded when auditing is used.
		from .audit import AuditLog

		sync_session = Session(bind=connection)
		data = make_serializable(target.to_dict())
		audit = AuditLog(
			table_name=target.__tablename__,
			operation=operation,
			timestamp=datetime.now(tz=UTC),
			data=data,
		)
		sync_session.add(audit)
		sync_session.flush()

	@classmethod
	def after_insert(cls, mapper, connection, target):
		if hasattr(target, "created_at"):
			target.created_at = datetime.now(tz=UTC)
		cls.log_operation(mapper, connection, target, "insert")

	@classmethod
	def after_update(cls, mapper, connection, target):
		if hasattr(target, "updated_at"):
			target.updated_at = datetime.now(tz=UTC)
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

	async def save(self, session: AsyncSession | None = None):
		async with self.get_session(session) as session:
			session.add(self)

	async def apply(self, session: AsyncSession | None = None):
		async with self.get_session(session) as session:
			session.add(self)

	@classmethod
	async def save_all(
		cls, models: list[TModels], session: AsyncSession | None = None
	):
		async with cls.get_session(session) as session:
			for model in models:
				model.validate_data(model.to_dict())
			session.add_all(models)

	@classmethod
	async def execute_query_read(
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

	@classmethod
	async def execute_query_write(
		cls,
		query,
		session: AsyncSession = None,
	):
		async with cls.get_session(session) as session:
			result = await session.execute(query)
			return result


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


def __getattr__(name):
	# Backward compatibility: `from sqla_async_orm_queries.models import AuditLog`
	# still works, but the audit_logs table is only registered when asked for.
	if name == "AuditLog":
		from .audit import AuditLog

		return AuditLog
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

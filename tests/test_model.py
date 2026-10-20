import subprocess
import sys
import warnings
from datetime import datetime, timezone
from typing import Optional

import pytest
import sqlalchemy
from pydantic import Field
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import relationship

# Import your Model classes here
# Assuming the codebase is in a file named 'models.py'
from sqla_async_orm_queries.models import (  # AuditLog: old import path still works
	AuditLog,
	Model,
	PydanticModelMixin,
	SoftDeleteMixin,
)

# Define a test database URL (in-memory SQLite)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Create the async engine and  factory
engine = create_async_engine(TEST_DATABASE_URL, echo=True)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

# Initialize the session factory in your Model
Model.init_session(AsyncSessionLocal)


# Define test models
class User(SoftDeleteMixin, Model):
	__tablename__ = "users"
	id = Column(Integer, primary_key=True, autoincrement=True)
	name = Column(String, nullable=False)
	email = Column(String, unique=True, nullable=False)
	is_active = Column(Boolean, default=True)
	created_at = Column(
		DateTime, default=lambda: datetime.now(tz=timezone.utc)
	)

	class PydanticModel(PydanticModelMixin):
		id: Optional[int] = None
		name: Optional[str] = None
		email: Optional[str] = None
		is_active: Optional[bool] = True
		created_at: Optional[datetime] = Field(
			default_factory=lambda: datetime.now(tz=timezone.utc)
		)


# Attach event listeners for audit logging
User.attach_listeners()


@pytest.fixture(scope="session", autouse=True)
async def setup_database():
	# Create the tables
	async with engine.begin() as conn:
		await conn.run_sync(Model.metadata.create_all)
	yield
	async with engine.begin() as conn:
		await conn.run_sync(Model.metadata.drop_all)
	await engine.dispose()


# Test cases
@pytest.mark.asyncio
async def test_create_user(setup_database):
	user_data = {"name": "John Doe", "email": "john@example.com"}
	user: User = await User.create(user_data)
	assert user.id is not None
	assert user.name == "John Doe"
	assert user.email == "john@example.com"


@pytest.mark.asyncio
async def test_read_user():
	user: User = await User.select_one(User.email == "john@example.com")
	assert user.is_deleted == False
	assert user is not None
	assert user.name == "John Doe"


@pytest.mark.asyncio
async def test_update_user():
	await User.update({"name": "Jane Doe"}, User.email == "john@example.com")
	user: User = await User.select_one(User.email == "john@example.com")
	assert user.name == "Jane Doe"


@pytest.mark.asyncio
async def test_soft_delete_user():
	await User.soft_delete(User.email == "john@example.com")
	user = await User.select_one(
		User.email == "john@example.com", include_inactive=True
	)
	assert user is not None
	assert user.is_deleted is True


@pytest.mark.asyncio
async def test_pagination():
	# Create multiple users
	users_data = [
		{"name": f"User {i}", "email": f"user{i}@example.com"}
		for i in range(1, 21)
	]
	await User.bulk_create(users_data)

	# Paginate
	pagination = await User.select_with_pagination(page=2, per_page=5)
	assert pagination.page == 2
	assert pagination.per_page == 5
	assert len(pagination.items) == 5
	# 21 users exist, but john@example.com was soft-deleted earlier
	assert pagination.total == 20
	assert pagination.pages == 4
	assert pagination.has_next == True
	assert pagination.has_prev == True


@pytest.mark.asyncio
async def test_validation():
	# Missing 'email' field
	invalid_user_data = {"name": "Invalid User"}
	with pytest.raises(sqlalchemy.exc.IntegrityError) as excinfo:
		await User.create(invalid_user_data)
	assert "IntegrityError" in str(excinfo.value)


@pytest.mark.asyncio
async def test_event_listener():
	# Create a user to trigger the event listener
	user_data = {"name": "Event User", "email": "event@example.com"}
	await User.create(user_data)

	# Check if an audit log was created
	audit_logs = await AuditLog.select_all()
	assert len(audit_logs) > 0
	audit_log = audit_logs[-1]
	assert audit_log.operation == "insert"
	assert audit_log.table_name == "users"
	assert audit_log.data["email"] == "event@example.com"


@pytest.mark.asyncio
async def test_detach_listeners():
	# Detach listeners
	User.detach_listeners()

	# Create a user without triggering the event listener
	user_data = {"name": "No Audit User", "email": "noaudit@example.com"}
	await User.create(user_data)

	# Reattach listeners
	User.attach_listeners()

	# Check if no new audit log was created
	audit_logs = await AuditLog.select_all()
	assert all(
		log.data.get("email") != "noaudit@example.com" for log in audit_logs
	)


@pytest.mark.asyncio
async def test_serialization():
	user = await User.select_one(User.email == "event@example.com")
	user_dict = user.to_dict()
	assert isinstance(user_dict, dict)
	assert user_dict["email"] == "event@example.com"

	user_json = user.to_json()
	assert isinstance(user_json, str)
	assert '"email": "event@example.com"' in user_json


@pytest.mark.asyncio
async def test_dynamic_filters():
	filters = {"name": "Event User"}
	conditions = User.build_filters(filters)
	users = await User.select_all(*conditions)
	assert len(users) == 1
	assert users[0].email == "event@example.com"


@pytest.mark.asyncio
async def test_transactional():
	async def operations(session):
		await User.create(
			{"name": "Transact User", "email": "transact@example.com"},
			session=session,
		)
		raise Exception("Intentional Error")

	with pytest.raises(Exception) as excinfo:
		async with User.get_session() as session:
			await User.transactional(operations, session)
	assert "Intentional Error" in str(excinfo.value)

	# Ensure that the user was not created due to rollback
	user = await User.select_one(User.email == "transact@example.com")
	assert user is None


@pytest.mark.asyncio
async def test_bulk_create():
	users_data = [
		{"name": "Bulk User 1", "email": "bulk1@example.com"},
		{"name": "Bulk User 2", "email": "bulk2@example.com"},
	]
	users = await User.bulk_create(users_data)
	assert len(users) == 2
	emails = [user.email for user in users]
	assert "bulk1@example.com" in emails
	assert "bulk2@example.com" in emails


@pytest.mark.asyncio
async def test_bulk_update():
	await User.bulk_update(
		{"name": "Updated Bulk User 2"},
		User.email.like("bulk%@example.com"),
	)
	users = await User.select_all(User.email.like("bulk%@example.com"))
	names = [user.name for user in users]
	assert "Updated Bulk User 2" in names


@pytest.mark.asyncio
async def test_bulk_delete():
	await User.bulk_delete(
		[User.email == "bulk1@example.com", User.email == "bulk2@example.com"]
	)
	users = await User.select_all(User.email.like("bulk%@example.com"))
	assert len(users) == 0


@pytest.mark.asyncio
async def test_soft_delete_with_include_inactive():
	# Create a user
	inactive_user_data = {
		"name": "Inactive User",
		"email": "inactive@example.com",
	}
	active_user_data = {"name": "Active User", "email": "active@example.com"}
	await User.create(inactive_user_data)
	await User.create(active_user_data)

	# Soft delete the user
	await User.soft_delete(User.email == "inactive@example.com")

	# Select including inactive users
	user = await User.select_one(
		User.email == "inactive@example.com", include_inactive=True
	)
	assert user is not None
	assert user.is_deleted == True

	# Select excluding inactive users
	user = await User.select_one(User.email == "active@example.com")
	assert user is not None
	assert user.is_deleted == False


@pytest.mark.asyncio
async def test_event_listener_with_detach_context():
	async def create_user_without_audit():
		with User.listeners_disabled():
			await User.create(
				{
					"name": "No Audit Context",
					"email": "noauditcontext@example.com",
				}
			)

	await create_user_without_audit()

	audit_logs = await AuditLog.select_all()
	emails = [log.data.get("email") for log in audit_logs]
	assert "noauditcontext@example.com" not in emails


@pytest.mark.asyncio
async def test_execute_query_write_commits_its_own_session():
	await User.execute_query_write(
		sqlalchemy.insert(User).values(name="Query Write", email="querywrite@example.com")
	)

	user = await User.select_one(User.email == "querywrite@example.com")
	assert user is not None


@pytest.mark.asyncio
async def test_execute_query_write_joins_the_callers_transaction():
	async with AsyncSessionLocal() as session:
		await User.create(
			{"name": "Rolled Back", "email": "rolledback@example.com"},
			session=session,
		)
		await User.execute_query_write(
			sqlalchemy.insert(User).values(name="Rolled Back 2", email="rolledback2@example.com"),
			session=session,
		)
		await session.rollback()

	emails = ["rolledback@example.com", "rolledback2@example.com"]
	assert await User.select_one(User.email.in_(emails)) is None


@pytest.mark.asyncio
async def test_execute_query_write_is_saved_when_the_caller_commits():
	async with AsyncSessionLocal() as session:
		await User.execute_query_write(
			sqlalchemy.insert(User).values(name="Committed", email="committed@example.com"),
			session=session,
		)
		await session.commit()

	assert await User.select_one(User.email == "committed@example.com") is not None


# Nested relationships for load_with="books.pages"
class Shelf(Model):
	__tablename__ = "shelves"
	id = Column(Integer, primary_key=True, autoincrement=True)
	name = Column(String)
	books = relationship("Book", back_populates="shelf")


class Book(Model):
	__tablename__ = "books"
	id = Column(Integer, primary_key=True, autoincrement=True)
	shelf_id = Column(Integer, ForeignKey("shelves.id"))
	shelf = relationship("Shelf", back_populates="books")
	pages = relationship("Page")


class Page(Model):
	__tablename__ = "pages"
	id = Column(Integer, primary_key=True, autoincrement=True)
	book_id = Column(Integer, ForeignKey("books.id"))


@pytest.mark.asyncio
async def test_create_has_id_inside_the_callers_transaction():
	async with AsyncSessionLocal() as session:
		user = await User.create(
			{"name": "Flushed", "email": "flushed@example.com"}, session=session
		)
		assert user.id is not None
		await session.rollback()

	assert await User.select_one(User.email == "flushed@example.com") is None


@pytest.mark.asyncio
async def test_update_returning_instances_and_columns():
	await User.create({"name": "Before", "email": "returning@example.com"})

	users = await User.update(
		{"name": "After"}, User.email == "returning@example.com", returning=User
	)
	names = await User.update(
		{"name": "After 2"},
		User.email == "returning@example.com",
		returning=[User.name],
	)

	assert [u.name for u in users] == ["After"]
	assert names == ["After 2"]


@pytest.mark.asyncio
async def test_load_with_nested_relationships():
	shelf = await Shelf.create({"name": "Fiction"})
	book = await Book.create({"shelf_id": shelf.id})
	await Page.bulk_create([{"book_id": book.id}, {"book_id": book.id}])

	shelf = await Shelf.select_one(
		Shelf.id == shelf.id, load_with=["books.pages"]
	)

	assert len(shelf.books[0].pages) == 2


def test_soft_delete_is_opt_in():
	assert "is_deleted" not in Shelf.__table__.c
	assert not hasattr(Shelf, "soft_delete")
	assert "is_deleted" in User.__table__.c


def test_audit_log_is_opt_in():
	check = (
		"import sqla_async_orm_queries.models as m;"
		"print('audit_logs' in m.Model.metadata.tables);"
		"import sqla_async_orm_queries.audit;"
		"print('audit_logs' in m.Model.metadata.tables)"
	)
	out = subprocess.run(
		[sys.executable, "-c", check], capture_output=True, text=True, check=True
	)
	assert out.stdout.split() == ["False", "True"]


@pytest.mark.asyncio
async def test_soft_deleted_rows_are_hidden_by_default():
	await User.bulk_create(
		[
			{"name": "Kept", "email": "kept@example.com"},
			{"name": "Gone", "email": "gone@example.com"},
		]
	)
	await User.soft_delete(User.email == "gone@example.com")
	emails = User.email.in_(["kept@example.com", "gone@example.com"])

	visible = await User.select_all(emails)
	everything = await User.select_all(emails, include_inactive=True)

	assert [u.email for u in visible] == ["kept@example.com"]
	assert len(everything) == 2
	assert await User.select_one(User.email == "gone@example.com") is None
	assert await User.get_count(emails) == 1
	assert await User.get_count(emails, include_inactive=True) == 2


def test_from_pydantic_has_no_deprecation_warning():
	with warnings.catch_warnings():
		warnings.simplefilter("error")
		user = User.from_pydantic(
			User.PydanticModel(name="Py", email="py@example.com")
		)
	assert user.email == "py@example.com"

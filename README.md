# SQLAlchemy ORM with Async Support

This project provides an abstract base class `Model` with advanced CRUD operations, audit logging, and support for SQLAlchemy's async ORM functionality. It includes several useful features such as soft delete functionality, Pydantic model integration for validation, and audit logging with event listeners.

## Key Features

- **Async Session Management**: Provides session management using async SQLAlchemy.
- **CRUD Operations**: Includes create, read, update, and delete operations.
- **Soft Delete** (opt-in): Ability to soft-delete records by marking them as inactive.
- **Audit Logging** (opt-in): Logs changes to models (insert, update, delete).
- **Pydantic Model Integration**: Supports data validation using Pydantic models.
- **Event Listeners**: Event listeners automatically trigger audit logging on inserts, updates, and deletes.
- **Transaction Management**: Supports transactional operations with rollback on failure.
- **Pagination Support**: Allows for paginated queries and returns results with metadata.
- **Bulk Operations**: Provides bulk create, update, and delete functionality.

### Installation
```sh
pip install sqla-async-orm-queries
```

Alternatively, if you prefer to use poetry for package dependencies:
```sh
poetry shell
poetry add sqla-async-orm-queries
```

Usage Examples
Before using this code, ensure you have the following dependency installed:

Python 3.11 or above


## How to Use

### 1. Define a Model

To define your own model, inherit from the `Model` class and define your fields using SQLAlchemy's `Column` types. Each model can also define its own Pydantic schema for validation purposes.

```python
from typing import Optional

from sqlalchemy import Column, Integer, String
from sqla_async_orm_queries.models import Model, PydanticModelMixin

class User(Model):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)

    class PydanticModel(PydanticModelMixin):
        id: Optional[int]
        name: str
        email: str
```

### 2. Initialize the Session

You need to initialize the session factory to enable database operations. Make sure to provide an `async_sessionmaker` for managing async sessions.

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqla_async_orm_queries.models import Model, PydanticModelMixin

DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(DATABASE_URL)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

Model.init_session(SessionLocal)
```

### 3. Perform CRUD Operations

CRUD operations are supported out of the box. You can create, read, update, delete, and soft delete records using the provided methods.

```python
# Create a new user
user_data = {'name': 'John Doe', 'email': 'john@example.com'}
user = await User.create(user_data)

# Read a user
user = await User.select_one(User.id == 1)

# Update a user
await User.update({'name': 'Jane Doe'}, User.id == 1)

# Soft delete a user (the model needs SoftDeleteMixin: class User(SoftDeleteMixin, Model))
await User.soft_delete(User.id == 1)
```

### 4. Audit Logging

Audit logging is opt-in. Import `AuditLog` (this adds the `audit_logs` table) and attach listeners to the models you want logged:

```python
from sqla_async_orm_queries.audit import AuditLog

User.attach_listeners()

audit_logs = await AuditLog.select_all()
```

### 5. Transaction Management

The `transactional` method provides an easy way to run a set of operations inside a transaction. If any error occurs, the transaction will be rolled back.

```python
async def my_operations(session):
    await User.create({'name': 'New User', 'email': 'new_user@example.com'}, session=session)

await User.transactional(my_operations)
```

If you pass your own `session`, methods don't commit — you do, once, at the end:

```python
async with SessionLocal() as session:
    await User.create({'name': 'New User', 'email': 'new_user@example.com'}, session=session)
    await User.execute_query_write(update(User).where(User.id == 1).values(name='Jane'), session=session)
    await session.commit()
```

### 6. Bulk Operations

You can create, update, and delete multiple records in a single transaction using the `bulk_create`, `bulk_update`, and `bulk_delete` methods.

```python
# Bulk create users
users_data = [{'name': 'User 1', 'email': 'user1@example.com'}, {'name': 'User 2', 'email': 'user2@example.com'}]
await User.bulk_create(users_data)

# Bulk delete users
await User.bulk_delete([User.id == 1, User.id == 2])
```

### 7. Pagination

Paginate through results using the `select_with_pagination` method:

```python
pagination = await User.select_with_pagination(page=2, per_page=10)
print(pagination.items)  # The users on the second page
```

## Upgrading to 3.0

Soft delete and audit logging are now opt-in. If you use them, add `SoftDeleteMixin` to those models and import `sqla_async_orm_queries.audit`. Requires Python 3.11+. Install your database driver (e.g. `asyncpg`) yourself.

## Installation

```bash
pip install sqla-async-orm-queries
pip install asyncpg  # or your database driver, e.g. aiosqlite
```

## Running Tests

```bash
poetry install
make test
```

## License

This project is licensed under the MIT License.

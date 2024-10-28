# SQLAlchemy ORM with Async Support

This project provides an abstract base class `Model` with advanced CRUD operations, audit logging, and support for SQLAlchemy's async ORM functionality. It includes several useful features such as soft delete functionality, Pydantic model integration for validation, and audit logging with event listeners.

## Key Features

- **Async Session Management**: Provides session management using async SQLAlchemy.
- **CRUD Operations**: Includes create, read, update, and delete operations.
- **Soft Delete**: Ability to soft-delete records by marking them as inactive.
- **Audit Logging**: Automatically logs changes to models (insert, update, delete).
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

Python 3.8 or above


## How to Use

### 1. Define a Model

To define your own model, inherit from the `Model` class and define your fields using SQLAlchemy's `Column` types. Each model can also define its own Pydantic schema for validation purposes.

```python
from sqlalchemy import Column, Integer, String
from sqla_async_orm_queries.models import  Model, PydanticModelMixin, AuditLog

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
from sqla_async_orm_queries.models import  Model, PydanticModelMixin, AuditLog

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

# Soft delete a user
await User.soft_delete(User.id == 1)
```

### 4. Audit Logging

The `AuditLog` model automatically logs any insert, update, or delete operation. The logs are stored in the `audit_logs` table.

```python
# View audit logs
audit_logs = await AuditLog.select_all()
```

### 5. Transaction Management

The `transactional` method provides an easy way to run a set of operations inside a transaction. If any error occurs, the transaction will be rolled back.

```python
async def my_operations(session):
    await User.create({'name': 'New User', 'email': 'new_user@example.com'}, session=session)

await User.transactional(my_operations)
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

## Installation

1. Install the necessary dependencies:

```bash
pip install sqlalchemy aiosqlite pydantic
```

2. Copy or clone this repository and define your models by inheriting from `Model`.

## Running Tests

You can run tests using `pytest` and `pytest-asyncio` for testing asynchronous operations. 

1. Install the test dependencies:

```bash
pip install pytest pytest-asyncio
```

2. Run the tests:

```bash
pytest
```

## License

This project is licensed under the MIT License.

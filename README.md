# SQLAlchemy Async ORM Queries
This is a simple implementation of an asynchronous ORM (Object-Relational Mapping) with SQLAlchemy, designed to work with asynchronous operations in Python. The code provided here demonstrates basic CRUD (Create, Read, Update, Delete) operations using SQLAlchemy's async features.

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

Python 3.7 or above

### Usage

Create your async engine 
```python
import asyncio
from sqlalchemy import Column, String, Integer, and_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqla_async_orm_queries import Model, init_session


engine = create_async_engine(
    DATABASE_URL,
    echo=True,
)
```
Create your session. Use async_sessionmaker
```python
SessionLocal = async_sessionmaker(
    expire_on_commit=True,
    class_=AsyncSession,
    bind=engine,
)
```

Declare your model
```python
class Test(Model):
    __tablename__ = "test"

    id = Column(Integer, primary_key=True, nullable=False)
    country = Column(String())
    name = Column(String())
    surname = Column(String())
```

Initialized your session
```python
init_session(SessionLocal)
```

Example of creating an entry
```python
await Test.create({"id": 1, "country": "AZ", "name": "Amrah", "surname": "Baghirov"})
```

Example of selecting all entries
```python
all_entries = await Test.select_all()

specific_entries = await Test.select_all(Test.name=="Amrah")
```

Example of selecting one entry
```python
entry = await Test.select_one(Test.country == "AZ")

# You can use and_ & or_ operation
entry = await Test.select_one(and_(Test.country == "AZ", Test.name == "Amrah"))
```

Example of updating an entry
```python
updated_entry = await Test.update({"name": "Ulvi"}, Test.country == "AZ")
```

Example of deleting an entry
```python
await Test.delete(Test.country == "AZ")
```

Example of selecting all entries with pagination
```python
all_entries_pagination = await Test.select_with_pagination(page=1, size=1)
```

Example of selecting all entries with pagination and args
```python
all_entries_pagination_and_criteria = await Test.select_with_pagination(
    Test.name == "Amrah", page=1, size=1
)
```

Example of self-updating 
```python
entry = await Test.select_one(Test.country == "AZ")
entry.country = "EN"
await entry.apply()
```
You can check full example in `examples` folder
import asyncio
from sqlalchemy import Column, String, Integer, and_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqla_async_orm_queries import Model, init_session


# create your engine
engine = create_async_engine(
    "postgresql+asyncpg://test_user:12345@localhost/test_db",
    echo=True,
)

# create your SessionLocal
SessionLocal = async_sessionmaker(
    expire_on_commit=True,
    class_=AsyncSession,
    bind=engine,
)


class Test(Model):
    __tablename__ = "test"

    id = Column(Integer, primary_key=True, nullable=False)
    country = Column(String())
    name = Column(String())
    surname = Column(String())


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)


async def main():
    await create_tables()

    # initialized session
    init_session(SessionLocal)

    # Example of creating an entry
    await Test.create(
        {"id": 11, "country": "AZ", "name": "Amrah", "surname": "Baghirov"}
    )
    await Test.create(
        {"id": 12, "country": "EN", "name": "Shukran", "surname": "Jabbarov"}
    )
    await Test.create(
        {"id": 13, "country": "RU", "name": "Amrah", "surname": "Suleymanli"}
    )

    # Example of selecting all entries
    all_entries = await Test.select_all()
    print("all entries:", all_entries)

    specific_entries = await Test.select_all(Test.name == "Kerim")
    print("specific entries:", specific_entries)

    # Example of selecting one entry
    entry = await Test.select_one(Test.country == "AZ")
    print("entry", entry)

    entry = await Test.select_one(and_(Test.country == "AZ", Test.name == "Amrah"))
    print("entry", entry)

    # Example of updating an entry
    updated_entry = await Test.update({"name": "Ulvi"}, Test.country == "AZ")
    print("updated entry", updated_entry)

    # Example of deleting an entry
    await Test.delete(Test.country == "AZ")

    # Check if the entry has been deleted
    all_entries_after_deletion = await Test.select_all()
    print("all entries after deletion:", all_entries_after_deletion)

    # Example of selecting all entries with pagination
    all_entries_pagination = await Test.select_with_pagination(page=1, size=1)
    print("all entries with pagination", all_entries_pagination)

    # Example of selecting all entries with pagination and args
    all_entries_pagination_and_criteria = await Test.select_with_pagination(
        Test.name == "Amrah", page=1, size=1
    )
    print("all entries with pagination", all_entries_pagination_and_criteria)

    # Example of self-updating
    entry = await Test.select_one(Test.country == "AZ")
    entry.country = "EN"
    await entry.apply()
    print("updated entry", entry)


if __name__ == "__main__":
    asyncio.run(main())

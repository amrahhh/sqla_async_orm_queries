.PHONY: install lint format check all test

install:
	poetry install

lint:
	ruff check sqla_async_orm_queries

format:
	ruff format sqla_async_orm_queries

check:
	ruff check sqla_async_orm_queries
	ruff format --check sqla_async_orm_queries

all:
	ruff check --fix sqla_async_orm_queries && ruff format sqla_async_orm_queries

test:
	python -m pytest tests/ -v

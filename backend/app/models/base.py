"""Declarative base shared by ORM models and Alembic."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class every mapped table inherits from."""

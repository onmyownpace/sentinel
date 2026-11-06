"""Live PostgreSQL check.

This test is skipped when nothing is listening. A skip means the check did not
run. It is not evidence that the database is healthy.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.database import create_db_engine


@pytest.mark.integration
async def test_configured_database_answers_select_one() -> None:
    engine = create_db_engine(get_settings())
    try:
        try:
            async with engine.connect() as connection:
                result = await connection.execute(text("SELECT 1"))
                value = result.scalar_one()
        except (OSError, SQLAlchemyError) as exc:
            pytest.skip(
                "PostgreSQL is not reachable, so this check did not run "
                f"({exc.__class__.__name__}). Start Docker Compose to exercise it."
            )
    finally:
        await engine.dispose()

    assert value == 1

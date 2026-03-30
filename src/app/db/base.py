from __future__ import annotations

from typing import Any

try:
    from sqlalchemy import MetaData
    from sqlalchemy.orm import DeclarativeBase
except ModuleNotFoundError:
    class MetaData:  # type: ignore[no-redef]
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.naming_convention = _kwargs.get("naming_convention", {})

    class DeclarativeBase:  # type: ignore[no-redef]
        metadata: MetaData


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

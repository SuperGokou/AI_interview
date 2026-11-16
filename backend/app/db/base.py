"""数据库连接与会话(单一职责:engine / SessionLocal / Base / get_db)。"""

from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _tune_sqlite(dbapi_connection, _record) -> None:
    """WAL lets a live interview write transcripts while the admin UI reads;
    busy_timeout makes concurrent writers wait instead of failing with 'database is locked'."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


def _make_engine(database_url: str):
    if database_url.startswith("sqlite"):
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            future=True,
        )
        if ":memory:" not in database_url:
            event.listen(engine, "connect", _tune_sqlite)
        return engine
    # Postgres (e.g. Supabase). Robust parse: last '@' splits creds from host,
    # first ':' splits user from password — tolerates special chars in password.
    scheme, rest = database_url.split("://", 1)
    userinfo, hostpart = rest.rsplit("@", 1)
    user, _, password = userinfo.partition(":")
    hostport, _, dbpart = hostpart.partition("/")
    host, _, port_s = hostport.partition(":")
    database = (dbpart.split("?", 1)[0]) or "postgres"
    port = int(port_s) if port_s else 5432
    url = URL.create(
        "postgresql+psycopg",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database,
    )
    # sslmode=require for Supabase; prepare_threshold=None disables prepared
    # statements so the connection works through the Supabase pooler (pgbouncer
    # transaction mode) as well as the session pooler — needed on IPv4-only hosts
    # like Render (the IPv6 direct host db.<ref>.supabase.co is unreachable there).
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"sslmode": "require", "prepare_threshold": None},
        future=True,
    )


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _add_missing_columns() -> None:
    """Add nullable columns that newer releases introduced on existing tables.

    The project has no migration tool; create_all never alters a table that
    already exists. Only nullable columns are added, which is safe on a live
    database with rows. Anything else still needs a real migration.
    """
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing or column.primary_key or not column.nullable:
                    continue
                column_type = column.type.compile(dialect=engine.dialect)
                connection.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}')
                )


def init_db() -> None:
    """创建所有表(开发期用;生产用迁移)。导入 models 以注册映射。"""
    from app.db import models  # noqa: F401  确保模型已注册到 Base.metadata
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    # create_all skips tables that already exist, so indexes added in a later
    # release would never reach an upgraded database. Create them explicitly.
    for table in Base.metadata.tables.values():
        for index in table.indexes:
            index.create(bind=engine, checkfirst=True)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖:每请求一个会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

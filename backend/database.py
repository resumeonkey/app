from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from backend.config import get_settings

settings = get_settings()

_url = settings.database_url
# SQLite requires check_same_thread=False; PostgreSQL does not accept that arg
_connect_args = {"check_same_thread": False} if _url.startswith("sqlite") else {}
engine = create_engine(_url, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from backend.models import master, adaptation, context  # noqa — registers all models
    Base.metadata.create_all(bind=engine)
    _migrate_add_columns()


def _migrate_add_columns():
    """
    Idempotent: add new columns that create_all won't add to existing tables.
    Safe to run on every startup (checks information_schema first).
    """
    migrations = [
        # table,              column,          definition
        ("adaptations",       "job_url",        "TEXT"),
        ("adaptations",       "applied_at",     "TIMESTAMP WITH TIME ZONE"),
        ("master_resumes",    "english_level",  "TEXT DEFAULT 'any'"),
        ("master_resumes",    "profile_tags",   "TEXT"),
    ]
    with engine.connect() as conn:
        for table, col, defn in migrations:
            try:
                # PostgreSQL: check if column already exists
                from sqlalchemy import text
                exists = conn.execute(text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name=:t AND column_name=:c"
                ), {"t": table, "c": col}).fetchone()
                if not exists:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {defn}'))
                    conn.commit()
            except Exception:
                # SQLite or already exists — ignore
                try:
                    conn.rollback()
                except Exception:
                    pass

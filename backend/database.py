from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from backend.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
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
    from backend.models import master, adaptation  # noqa — registers models
    Base.metadata.create_all(bind=engine)

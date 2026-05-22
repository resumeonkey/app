import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Boolean, DateTime
from backend.database import Base


class UserContext(Base):
    __tablename__ = "user_contexts"

    id         = Column(String,   primary_key=True, default=lambda: str(uuid.uuid4()))
    title      = Column(String,   nullable=False)
    content    = Column(Text,     nullable=False)
    is_active  = Column(Boolean,  default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

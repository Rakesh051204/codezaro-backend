from sqlalchemy import Column, Integer, String, DateTime, Text, Enum, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class UserTier(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    TEAM = "team"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    tier = Column(Enum(UserTier), default=UserTier.FREE, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    reviews = relationship("Review", back_populates="user", cascade="all, delete-orphan")
    usage = relationship("Usage", back_populates="user", cascade="all, delete-orphan")

class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    code = Column(Text, nullable=False)
    language = Column(String, nullable=True)
    review_result = Column(Text, nullable=True)  # JSON or plain text
    model_used = Column(String, nullable=True)   # e.g., "claude-3-haiku"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="reviews")

class Usage(Base):
    __tablename__ = "usage"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    month = Column(String, nullable=False)  # format: YYYY-MM
    review_count = Column(Integer, default=0)

    user = relationship("User", back_populates="usage")

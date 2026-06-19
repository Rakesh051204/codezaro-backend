from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from app.models import UserTier

# ---- Auth ----
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenRefresh(BaseModel):
    refresh_token: str

# ---- User ----
class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str]
    tier: UserTier
    created_at: datetime

    class Config:
        from_attributes = True

# ---- Review ----
class ReviewCreate(BaseModel):
    code: str
    language: Optional[str] = None

class ReviewResponse(BaseModel):
    id: int
    code: str
    language: Optional[str]
    review_result: Optional[str]
    model_used: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

# ---- Usage ----
class UsageResponse(BaseModel):
    month: str
    review_count: int
    tier: UserTier
    limit: int

    class Config:
        from_attributes = True

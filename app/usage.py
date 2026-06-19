from sqlalchemy.orm import Session
from datetime import datetime
from app.models import User, Usage, UserTier
from app.config import settings
from fastapi import HTTPException, status

def get_month() -> str:
    """Return current month as YYYY-MM"""
    return datetime.utcnow().strftime("%Y-%m")

def get_usage_limit(tier: UserTier) -> int:
    """Return monthly limit per tier"""
    if tier == UserTier.FREE:
        return settings.FREE_MONTHLY_LIMIT
    elif tier == UserTier.PRO:
        return settings.PRO_MONTHLY_LIMIT
    elif tier == UserTier.TEAM:
        return settings.TEAM_MONTHLY_LIMIT
    return 0

def check_usage_limit(user: User, db: Session) -> bool:
    """Return True if user can make another review, False if limit reached"""
    month = get_month()
    usage = db.query(Usage).filter(Usage.user_id == user.id, Usage.month == month).first()
    current_count = usage.review_count if usage else 0
    limit = get_usage_limit(user.tier)
    return current_count < limit

def increment_usage(user: User, db: Session) -> None:
    """Increment review count for current month, create record if not exists"""
    month = get_month()
    usage = db.query(Usage).filter(Usage.user_id == user.id, Usage.month == month).first()
    if not usage:
        usage = Usage(user_id=user.id, month=month, review_count=0)
        db.add(usage)
    usage.review_count += 1
    db.commit()

def get_usage_info(user: User, db: Session) -> dict:
    """Return usage info: month, count, limit, tier"""
    month = get_month()
    usage = db.query(Usage).filter(Usage.user_id == user.id, Usage.month == month).first()
    count = usage.review_count if usage else 0
    limit = get_usage_limit(user.tier)
    return {
        "month": month,
        "review_count": count,
        "limit": limit,
        "tier": user.tier.value
    }

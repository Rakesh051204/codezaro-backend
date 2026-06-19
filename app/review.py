import json
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.models import User, Review
from app.schemas import ReviewCreate, ReviewResponse
from app.usage import check_usage_limit, increment_usage, get_usage_info
from app.config import settings
from groq import Groq

router = APIRouter(prefix="/review", tags=["review"])

# Initialize Groq client (free tier, no credit card needed)
client = Groq(api_key=settings.GROQ_API_KEY)

def run_review(code: str, language: str = None) -> str:
    """Call Groq API to review code"""
    if not settings.GROQ_API_KEY:
        # Mock response for development (API key not set)
        return "CodeZaro AI (dev mode): This code looks good. Add a real API key in settings to enable full reviews."

    prompt = f"Review the following {language or 'code'} for bugs, security issues, and improvements. Provide concise feedback.\n\n```{language or ''}\n{code}\n```"
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error during review: {str(e)}"

@router.post("/", response_model=ReviewResponse)
def create_review(
    review_data: ReviewCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Check usage limit
    if not check_usage_limit(current_user, db):
        usage_info = get_usage_info(current_user, db)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "message": "Monthly review limit reached. Upgrade to Pro for more.",
                "usage": usage_info
            }
        )

    # 2. Perform review (could be background, but we keep sync for simplicity)
    review_result = run_review(review_data.code, review_data.language)

    # 3. Store review
    new_review = Review(
        user_id=current_user.id,
        code=review_data.code,
        language=review_data.language,
        review_result=review_result,
        model_used="CodeZaro AI"
    )
    db.add(new_review)
    db.commit()
    db.refresh(new_review)

    # 4. Increment usage
    increment_usage(current_user, db)

    return new_review

@router.get("/usage")
def get_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current usage info for the user"""
    return get_usage_info(current_user, db)

@router.get("/history")
def get_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 10,
    offset: int = 0
):
    """Get user's review history"""
    reviews = db.query(Review).filter(Review.user_id == current_user.id).order_by(Review.created_at.desc()).offset(offset).limit(limit).all()
    return reviews
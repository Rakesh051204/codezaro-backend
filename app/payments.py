from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.models import User, UserTier  # <-- import UserTier
from app.config import settings
import stripe

router = APIRouter(prefix="/payments", tags=["payments"])

stripe.api_key = settings.STRIPE_SECRET_KEY

@router.post("/create-checkout")
def create_checkout(current_user: User = Depends(get_current_user)):
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price": "price_1TlSJB4cGrYPt8vrty7Bfehv",  # Replace with your Price ID
                    "quantity": 1,
                }
            ],
            mode="subscription",
            success_url="https://codezaro-frontend.onrender.com/review?success=true",
            cancel_url="https://codezaro-frontend.onrender.com/review?canceled=true",
            client_reference_id=str(current_user.id),
            metadata={"user_id": str(current_user.id)},
        )
        return {"url": checkout_session.url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("user_id")
        if user_id:
            user = db.query(User).filter(User.id == int(user_id)).first()
            if user:
                user.tier = UserTier.PRO  # or "PRO" if you use strings
                db.commit()
                print(f"User {user_id} upgraded to PRO")

    return {"status": "success"}
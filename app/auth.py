from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.database import get_db
from app.config import settings
from app.models import User, UserTier
from app.schemas import UserRegister, UserLogin, Token, TokenRefresh

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict):
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = data.copy()
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

@router.post("/register", response_model=Token)
def register(user: UserRegister, db: Session = Depends(get_db)):
    # Check if user exists
    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = get_password_hash(user.password)
    new_user = User(
        email=user.email,
        hashed_password=hashed,
        full_name=user.full_name,
        tier=UserTier.FREE
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    # Generate tokens
    access_token = create_access_token(data={"sub": str(new_user.id)})
    refresh_token = create_refresh_token(data={"sub": str(new_user.id)})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == form_data.username).first()
    if not db_user or not verify_password(form_data.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    access_token = create_access_token(data={"sub": str(db_user.id)})
    refresh_token = create_refresh_token(data={"sub": str(db_user.id)})
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

@router.post("/refresh", response_model=Token)
def refresh(refresh_data: TokenRefresh, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(status_code=401, detail="Invalid refresh token")
    try:
        payload = jwt.decode(refresh_data.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "refresh":
            raise credentials_exception
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise credentials_exception
    new_access = create_access_token(data={"sub": str(user.id)})
    new_refresh = create_refresh_token(data={"sub": str(user.id)})
    return {"access_token": new_access, "refresh_token": new_refresh, "token_type": "bearer"}
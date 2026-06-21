from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app import models  # ensure models are imported so tables are created
from app.auth import router as auth_router
from app.review import router as review_router
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables if not exist (safe)
    Base.metadata.create_all(bind=engine)
    yield
    # Shutdown: nothing special

app = FastAPI(title="CodeZaro API", version="0.1.0", lifespan=lifespan)

# CORS (allow dev frontend origins explicitly — required because allow_credentials=True)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:5173",
        "https://codezaro-frontend.onrender.com",   # <-- added your live frontend
        "https://codezaro-backend.onrender.com",    # optional, for self-reference
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(review_router)

@app.get("/")
def root():
    return {"message": "Welcome to CodeZaro API"}

@app.get("/health")
def health():
    return {"status": "ok"}
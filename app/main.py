from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app import models
from app.auth import router as auth_router
from app.review import router as review_router
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="CodeZaro API", version="0.1.0", lifespan=lifespan)

# CORS – allow frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:5173",
        "https://codezaro-frontend.onrender.com",    # <-- your live frontend
        "https://codezaro-backend.onrender.com",     # optional
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(review_router)

@app.get("/")
def root():
    return {"message": "Welcome to CodeZaro API"}

@app.get("/health")
def health():
    return {"status": "ok"}
import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

try:
    from .auth_core import init_auth_db, router
except ImportError:
    from auth_core import init_auth_db, router


load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI(title="MediBot Auth Service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("AUTH_CORS_ORIGINS", "*").split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
init_auth_db()
app.include_router(router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "auth"}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response("", media_type="text/plain")

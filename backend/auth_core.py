import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - optional unless Postgres is configured
    psycopg = None
    dict_row = None

try:
    from .http_clients import async_client
except ImportError:
    from http_clients import async_client


BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BACKEND_DIR, "data")

from dotenv import load_dotenv
load_dotenv(os.path.join(BACKEND_DIR, ".env"), override=True)

AUTH_DB_PATH = os.getenv("AUTH_DB_PATH", os.path.join(DATA_DIR, "medibot_auth.sqlite3"))
AUTH_DATABASE_URL = (
    os.getenv("AUTH_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or ""
).strip()
AUTH_SECRET = os.getenv("AUTH_SECRET") or os.getenv("SECRET_KEY") or "dev-medibot-change-me"
TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", str(60 * 60 * 24 * 7)))
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()


def _database_backend() -> str:
    if not AUTH_DATABASE_URL:
        return "sqlite"
    scheme = urlparse(AUTH_DATABASE_URL).scheme.lower()
    if scheme in {"postgres", "postgresql", "postgresql+psycopg"}:
        return "postgres"
    return "sqlite"


DB_BACKEND = _database_backend()


class RegisterRequest(BaseModel):
    name: str = Field(default="", max_length=120)
    email: str = Field(max_length=254)
    password: str = Field(min_length=6, max_length=256)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        clean = value.strip().lower()
        if "@" not in clean or "." not in clean.rsplit("@", 1)[-1]:
            raise ValueError("Enter a valid email address")
        return clean


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        clean = value.strip().lower()
        if "@" not in clean or "." not in clean.rsplit("@", 1)[-1]:
            raise ValueError("Enter a valid email address")
        return clean


class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=20)


class ChatHistoryRequest(BaseModel):
    messages: list[Dict[str, Any]] = Field(default_factory=list)


def _sqlite_connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(AUTH_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(AUTH_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _postgres_connect():
    if psycopg is None:
        raise RuntimeError("psycopg is required when AUTH_DATABASE_URL points to Postgres")
    return psycopg.connect(AUTH_DATABASE_URL, autocommit=False, row_factory=dict_row)


@contextmanager
def _connect() -> Iterator[Any]:
    conn = _postgres_connect() if DB_BACKEND == "postgres" else _sqlite_connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _one(query: str, params: tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(query, params).fetchone()
    if row is None:
        return None
    return dict(row)


def init_auth_db() -> None:
    users_sql = """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            name TEXT,
            password_hash TEXT,
            provider TEXT NOT NULL DEFAULT 'password',
            provider_sub TEXT,
            picture TEXT,
            created_at BIGINT NOT NULL,
            updated_at BIGINT NOT NULL
        )
    """
    history_sql = """
        CREATE TABLE IF NOT EXISTS chat_histories (
            user_id TEXT PRIMARY KEY,
            messages_json TEXT NOT NULL,
            updated_at BIGINT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """

    with _connect() as conn:
        conn.execute(users_sql)
        conn.execute(history_sql)
        if DB_BACKEND == "postgres":
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        else:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 180_000)
    return f"pbkdf2_sha256${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: Optional[str]) -> bool:
    if not stored:
        return False
    try:
        method, salt_b64, digest_b64 = stored.split("$", 2)
        if method != "pbkdf2_sha256":
            return False
        expected = _unb64(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _unb64(salt_b64), 180_000)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def create_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _b64(hmac.new(AUTH_SECRET.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_token(token: str) -> str:
    try:
        body, sig = token.split(".", 1)
        expected = _b64(hmac.new(AUTH_SECRET.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad signature")
        payload = json.loads(_unb64(body))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("expired")
        return str(payload["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def storage_label() -> str:
    return "Postgres" if DB_BACKEND == "postgres" else AUTH_DB_PATH


def _public_user(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row.get("name") or row["email"],
        "provider": row["provider"],
        "picture": row.get("picture"),
    }


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    placeholder = "%s" if DB_BACKEND == "postgres" else "?"
    return _one(f"SELECT * FROM users WHERE id = {placeholder}", (user_id,))


def require_user(authorization: str = Header(default="")) -> Dict[str, Any]:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = verify_token(token)
    row = get_user_by_id(user_id)
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return _public_user(row)


def _auth_response(row: Dict[str, Any]) -> Dict[str, Any]:
    user = _public_user(row)
    return {"token": create_token(user["id"]), "user": user, "storage": storage_label()}


async def verify_google_credential(credential: str) -> Dict[str, Any]:
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google login is not configured")
    async with async_client(timeout=10) as client:
        res = await client.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": credential})
    if res.status_code >= 400:
        raise HTTPException(status_code=401, detail="Google credential rejected")
    payload = res.json()
    if payload.get("aud") != GOOGLE_CLIENT_ID or payload.get("email_verified") not in ("true", True):
        raise HTTPException(status_code=401, detail="Google credential not valid for this app")
    return payload


router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/auth/config")
def auth_config():
    return {
        "google_client_id": GOOGLE_CLIENT_ID,
        "google_enabled": bool(GOOGLE_CLIENT_ID),
        "storage": storage_label(),
        "storage_backend": DB_BACKEND,
    }


@router.post("/auth/register")
def register(payload: RegisterRequest):
    init_auth_db()
    now = int(time.time())
    user_id = secrets.token_urlsafe(18)
    placeholder = "%s" if DB_BACKEND == "postgres" else "?"
    try:
        with _connect() as conn:
            conn.execute(
                f"""
                INSERT INTO users (id, email, name, password_hash, provider, created_at, updated_at)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, 'password', {placeholder}, {placeholder})
                """,
                (
                    user_id,
                    payload.email.lower(),
                    payload.name.strip() or payload.email,
                    hash_password(payload.password),
                    now,
                    now,
                ),
            )
        row = get_user_by_id(user_id)
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate key" in str(exc).lower():
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        raise
    return _auth_response(row)


@router.post("/auth/login")
def login(payload: LoginRequest):
    init_auth_db()
    placeholder = "%s" if DB_BACKEND == "postgres" else "?"
    row = _one(f"SELECT * FROM users WHERE email = {placeholder}", (payload.email.lower(),))
    if not row or not verify_password(payload.password, row.get("password_hash")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _auth_response(row)


@router.post("/auth/google")
async def google_login(payload: GoogleLoginRequest):
    init_auth_db()
    info = await verify_google_credential(payload.credential)
    email = info["email"].lower()
    now = int(time.time())
    placeholder = "%s" if DB_BACKEND == "postgres" else "?"

    with _connect() as conn:
        row = conn.execute(f"SELECT * FROM users WHERE email = {placeholder}", (email,)).fetchone()
        if row:
            row = dict(row)
            conn.execute(
                f"""
                UPDATE users
                SET name = {placeholder}, provider = {placeholder}, provider_sub = {placeholder}, picture = {placeholder}, updated_at = {placeholder}
                WHERE id = {placeholder}
                """,
                (
                    info.get("name") or row.get("name"),
                    "google",
                    info.get("sub"),
                    info.get("picture"),
                    now,
                    row["id"],
                ),
            )
            row = conn.execute(f"SELECT * FROM users WHERE id = {placeholder}", (row["id"],)).fetchone()
        else:
            user_id = secrets.token_urlsafe(18)
            conn.execute(
                f"""
                INSERT INTO users (id, email, name, provider, provider_sub, picture, created_at, updated_at)
                VALUES ({placeholder}, {placeholder}, {placeholder}, 'google', {placeholder}, {placeholder}, {placeholder}, {placeholder})
                """,
                (
                    user_id,
                    email,
                    info.get("name") or email,
                    info.get("sub"),
                    info.get("picture"),
                    now,
                    now,
                ),
            )
            row = conn.execute(f"SELECT * FROM users WHERE id = {placeholder}", (user_id,)).fetchone()
    return _auth_response(dict(row))


@router.get("/auth/me")
def me(user: Dict[str, Any] = Depends(require_user)):
    return {"user": user, "storage": storage_label()}


@router.get("/chat-history")
def get_chat_history(user: Dict[str, Any] = Depends(require_user)):
    init_auth_db()
    placeholder = "%s" if DB_BACKEND == "postgres" else "?"
    row = _one(
        f"SELECT messages_json, updated_at FROM chat_histories WHERE user_id = {placeholder}",
        (user["id"],),
    )
    if not row:
        return {"messages": [], "updated_at": None, "storage": storage_label()}
    return {"messages": json.loads(row["messages_json"]), "updated_at": row["updated_at"], "storage": storage_label()}


@router.put("/chat-history")
def save_chat_history(payload: ChatHistoryRequest, user: Dict[str, Any] = Depends(require_user)):
    init_auth_db()
    now = int(time.time())
    messages_json = json.dumps(payload.messages[-250:], separators=(",", ":"))
    placeholder = "%s" if DB_BACKEND == "postgres" else "?"

    if DB_BACKEND == "postgres":
        upsert_sql = f"""
            INSERT INTO chat_histories (user_id, messages_json, updated_at)
            VALUES ({placeholder}, {placeholder}, {placeholder})
            ON CONFLICT(user_id) DO UPDATE
            SET messages_json = EXCLUDED.messages_json, updated_at = EXCLUDED.updated_at
        """
    else:
        upsert_sql = f"""
            INSERT INTO chat_histories (user_id, messages_json, updated_at)
            VALUES ({placeholder}, {placeholder}, {placeholder})
            ON CONFLICT(user_id) DO UPDATE SET messages_json = excluded.messages_json, updated_at = excluded.updated_at
        """

    with _connect() as conn:
        conn.execute(upsert_sql, (user["id"], messages_json, now))

    return {"ok": True, "updated_at": now, "storage": storage_label()}

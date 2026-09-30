"""Authentication (JWT + PBKDF2), RBAC, field-level encryption (Fernet/AES), rate limiting."""
import base64, hashlib, hmac, os, time
from collections import defaultdict, deque

import jwt
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config

_key = config.DATA_KEY or base64.urlsafe_b64encode(hashlib.sha256(b"dev-only-data-key").digest()).decode()
fernet = Fernet(_key.encode())
bearer = HTTPBearer(auto_error=False)
ROLES = ("admin", "coordinator", "auditor")


def hash_password(pw, salt=None):
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(pw, stored):
    try:
        s, h = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), base64.b64decode(s), 200_000)
        return hmac.compare_digest(dk, base64.b64decode(h))
    except Exception:
        return False


def create_token(username, role):
    now = int(time.time())
    return jwt.encode({"sub": username, "role": role, "iat": now, "exp": now + config.JWT_TTL_MIN * 60},
                      config.JWT_SECRET, algorithm="HS256")


def encrypt(s: str) -> str:
    return fernet.encrypt(s.encode()).decode()


def decrypt(s: str) -> str:
    return fernet.decrypt(s.encode()).decode()


def current_user(cred: HTTPAuthorizationCredentials = Depends(bearer)):
    if not cred:
        raise HTTPException(401, "Missing bearer token")
    try:
        return jwt.decode(cred.credentials, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")


def require(*roles):
    def dep(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, f"Role '{user['role']}' not permitted")
        return user
    return dep


_hits = defaultdict(deque)


def rate_limit(request: Request):
    ip = request.client.host if request.client else "?"
    q = _hits[ip]; now = time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= config.LOGIN_RATE_PER_MIN:
        raise HTTPException(429, "Too many login attempts")
    q.append(now)

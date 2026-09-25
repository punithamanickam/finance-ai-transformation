"""Authentication and role-based access.

* Passwords: PBKDF2-HMAC-SHA256 with a per-user salt.
* Sessions: HMAC-SHA256 signed bearer tokens (`user|role|bu|expiry`) keyed by AVCC_SECRET_KEY.
* Roles: CFO (everything, including the audit log), FINANCE (all portfolio data), BU (only its own business unit's
  initiatives and the aggregates computed from them).

This is a deliberately small, dependency-free implementation for a local prototype. In an enterprise deployment
the same `Principal` would come from the corporate identity provider (OIDC / SAML) instead of local passwords.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass

from src import settings

ROLES = {
    "CFO": {"read:portfolio", "read:all_bus", "run:copilot", "run:scenario", "run:report", "read:audit"},
    "FINANCE": {"read:portfolio", "read:all_bus", "run:copilot", "run:scenario", "run:report"},
    "BU": {"read:portfolio", "run:copilot", "run:scenario"},
}

_DEV_KEY = secrets.token_bytes(32)


def _key() -> bytes:
    return settings.SECRET_KEY.encode() if settings.SECRET_KEY else _DEV_KEY


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: str
    bu_id: str | None = None

    def can(self, permission: str) -> bool:
        return permission in ROLES.get(self.role, set())

    @property
    def scope(self) -> str | None:
        """BU filter to apply to data, or None for the whole portfolio."""
        return None if self.can("read:all_bus") else self.bu_id


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"pbkdf2${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt)).split("$")[2], digest)


def issue_token(p: Principal, ttl: int | None = None) -> str:
    exp = int(time.time()) + (ttl or settings.TOKEN_TTL_SECONDS)
    body = f"{p.user_id}|{p.role}|{p.bu_id or ''}|{exp}"
    sig = hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{body}|{sig}".encode()).decode()


def verify_token(token: str) -> Principal | None:
    try:
        user, role, bu, exp, sig = base64.urlsafe_b64decode(token.encode()).decode().split("|")
    except Exception:
        return None
    body = f"{user}|{role}|{bu}|{exp}"
    if not hmac.compare_digest(hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest(), sig):
        return None
    if int(exp) < time.time() or role not in ROLES:
        return None
    return Principal(user, role, bu or None)

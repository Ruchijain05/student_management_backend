import hashlib
import hmac
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.enums import UserRole
from app.models import User

password_hash = PasswordHash.recommended()
bearer_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/token", auto_error=False
)
DatabaseSession = Annotated[Session, Depends(get_db)]


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def hash_password_reset_otp(otp: str, user_id: int) -> str:
    if len(settings.secret_key) < 32:
        raise RuntimeError(
            "SECRET_KEY must contain at least 32 characters; set a strong random "
            "key in .env"
        )
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        f"{user_id}:{otp}".encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def create_access_token(user: User) -> str:
    if len(settings.secret_key) < 32:
        raise RuntimeError(
            "SECRET_KEY must contain at least 32 characters; set a strong random "
            "key in .env"
        )
    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    return jwt.encode(
        {"sub": str(user.id), "ver": user.token_version, "exp": expires_at},
        settings.secret_key,
        algorithm="HS256",
    )


def get_current_user(
    access_token: Annotated[str | None, Depends(bearer_scheme)],
    db: DatabaseSession,
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if access_token is None:
        raise unauthorized
    if len(settings.secret_key) < 32:
        raise RuntimeError(
            "SECRET_KEY must contain at least 32 characters; set a strong random "
            "key in .env"
        )
    try:
        payload = jwt.decode(
            access_token,
            settings.secret_key,
            algorithms=["HS256"],
        )
        user_id = int(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise unauthorized from exc

    user = db.get(User, user_id)
    if user is None or payload.get("ver", 0) != user.token_version:
        raise unauthorized
    return user


def require_role(role: UserRole) -> Callable[..., User]:
    def role_dependency(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"{role.value} role required",
            )
        return current_user

    return role_dependency


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]

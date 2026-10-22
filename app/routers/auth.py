import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.enums import UserRole
from app.models import PasswordResetToken, Student, User
from app.schemas import (
    LoginRequest,
    OAuth2TokenResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    TokenResponse,
    UserRead,
)
from app.security import (
    CurrentUser,
    create_access_token,
    hash_password,
    hash_password_reset_otp,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
DatabaseSession = Annotated[Session, Depends(get_db)]
PASSWORD_RESET_OTP_TTL = timedelta(minutes=5)
PASSWORD_RESET_COOLDOWN = timedelta(minutes=1)
PASSWORD_RESET_MAX_ATTEMPTS = 5
PASSWORD_RESET_MESSAGE = (
    "If an account exists for that email, a password reset OTP has been "
    "generated."
)


def _local_otp_output_enabled() -> bool:
    return (
        settings.app_env == "development"
        and settings.password_reset_otp_console_enabled
    )


@router.post(
    "/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
def register_student(
    registration: RegisterRequest, db: DatabaseSession
) -> TokenResponse:
    email = str(registration.email).lower()
    student = Student(
        first_name=registration.first_name,
        last_name=registration.last_name,
        email=email,
    )
    db.add(student)
    try:
        db.flush()
        user = User(
            email=email,
            password_hash=hash_password(registration.password),
            role=UserRole.STUDENT,
            student=student,
        )
        db.add(user)
        db.flush()
        access_token = create_access_token(user)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc
    db.refresh(user)
    return TokenResponse(access_token=access_token, user=user)


@router.post("/login", response_model=TokenResponse)
def login(credentials: LoginRequest, db: DatabaseSession) -> TokenResponse:
    user = _authenticate_user(str(credentials.email), credentials.password, db)
    return TokenResponse(access_token=create_access_token(user), user=user)


@router.post(
    "/token", response_model=OAuth2TokenResponse, include_in_schema=False
)
def swagger_token(
    credentials: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DatabaseSession,
) -> OAuth2TokenResponse:
    user = _authenticate_user(credentials.username, credentials.password, db)
    return OAuth2TokenResponse(access_token=create_access_token(user))


def _authenticate_user(email: str, password: str, db: Session) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.post("/password-reset/request")
def request_password_reset(
    request: PasswordResetRequest,
    db: DatabaseSession,
) -> dict[str, str]:
    user = db.scalar(
        select(User).where(User.email == str(request.email).lower())
    )
    if user is None:
        return {"message": PASSWORD_RESET_MESSAGE}

    now = datetime.now(UTC).replace(tzinfo=None)
    if _local_otp_output_enabled():
        db.execute(
            update(User)
            .where(User.id == user.id)
            .values(password_reset_requested_at=now)
        )
    else:
        allowed = db.execute(
            update(User)
            .where(
                User.id == user.id,
                or_(
                    User.password_reset_requested_at.is_(None),
                    User.password_reset_requested_at
                    <= now - PASSWORD_RESET_COOLDOWN,
                ),
            )
            .values(password_reset_requested_at=now)
        )
        if allowed.rowcount != 1:
            return {"message": PASSWORD_RESET_MESSAGE}

    otp = f"{secrets.randbelow(1_000_000):06d}"
    token_hash = hash_password_reset_otp(otp, user.id)
    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=now + PASSWORD_RESET_OTP_TTL,
    )
    db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id
        )
    )
    db.add(reset_token)
    db.commit()

    if _local_otp_output_enabled():
        print(
            f"Local password reset OTP for {user.email}: {otp}",
            flush=True,
        )
    return {"message": PASSWORD_RESET_MESSAGE}


@router.post("/password-reset/confirm")
def confirm_password_reset(
    request: PasswordResetConfirm, db: DatabaseSession
) -> dict[str, str]:
    now = datetime.now(UTC).replace(tzinfo=None)
    email = str(request.email).lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset OTP",
        )

    reset_token = db.scalar(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.expires_at > now,
        )
        .with_for_update()
    )
    if reset_token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset OTP",
        )

    if reset_token.attempt_count >= PASSWORD_RESET_MAX_ATTEMPTS:
        db.delete(reset_token)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset OTP",
        )

    token_hash = hash_password_reset_otp(request.otp, user.id)
    if not hmac.compare_digest(reset_token.token_hash, token_hash):
        if reset_token.attempt_count + 1 >= PASSWORD_RESET_MAX_ATTEMPTS:
            db.delete(reset_token)
        else:
            reset_token.attempt_count += 1
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset OTP",
        )

    consumed = db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.id == reset_token.id,
            PasswordResetToken.expires_at > now,
            PasswordResetToken.attempt_count < PASSWORD_RESET_MAX_ATTEMPTS,
        )
    )
    if consumed.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset OTP",
        )

    user.password_hash = hash_password(request.new_password)
    user.token_version += 1
    db.commit()
    return {"message": "Password has been reset"}


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: CurrentUser) -> User:
    return current_user
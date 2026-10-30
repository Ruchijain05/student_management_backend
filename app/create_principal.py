from getpass import getpass

from pydantic import TypeAdapter
from pydantic.networks import EmailStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.enums import UserRole
from app.models import User
from app.security import hash_password


def main() -> None:
    email = str(
        TypeAdapter(EmailStr).validate_python(input("Principal email: "))
    ).lower()
    password = getpass(
        "Principal password (at least 8 characters, including a letter, a "
        "number, and a special character): "
    )
    confirmation = getpass("Confirm principal password: ")
    if (
        len(password) < 8
        or not any(character.isalpha() for character in password)
        or not any(character.isdigit() for character in password)
        or not any(not character.isalnum() for character in password)
    ):
        raise SystemExit(
            "Password must be at least 8 characters and include a letter, "
            "a number, and a special character."
        )
    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)) is not None:
            raise SystemExit("An account with that email already exists.")
        db.add(
            User(
                email=email,
                password_hash=hash_password(password),
                role=UserRole.PRINCIPAL,
            )
        )
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise SystemExit("Could not create the principal account.") from exc
    print(f"Created principal account for {email}.")


if __name__ == "__main__":
    main()

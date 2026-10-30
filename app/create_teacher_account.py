from getpass import getpass

from pydantic import TypeAdapter
from pydantic.networks import EmailStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.enums import UserRole
from app.models import Teacher, User
from app.security import hash_password


def main() -> None:
    email = str(
        TypeAdapter(EmailStr).validate_python(input("Teacher email: "))
    ).lower()
    password = getpass(
        "Teacher password (at least 8 characters, including a letter, a "
        "number, and a special character): "
    )
    confirmation = getpass("Confirm teacher password: ")
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
        teacher = db.scalar(select(Teacher).where(Teacher.email == email))
        if teacher is None:
            raise SystemExit(
                "No teacher record has that email. Create the teacher record "
                "as Admin first."
            )
        if db.scalar(select(User).where(User.email == email)) is not None:
            raise SystemExit("An account with that email already exists.")
        db.add(
            User(
                email=email,
                password_hash=hash_password(password),
                role=UserRole.TEACHER,
                teacher_id=teacher.id,
            )
        )
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise SystemExit("Could not create the teacher account.") from exc
    print(f"Created teacher login for {email}.")


if __name__ == "__main__":
    main()

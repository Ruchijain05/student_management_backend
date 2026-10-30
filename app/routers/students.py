from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.department_access import department_student_ids
from app.teacher_access import teacher_student_ids
from app.enums import UserRole
from app.models import FeeAssignment, Student, User
from app.schemas import StudentCreate, StudentRead, StudentUpdate
from app.security import AdminUser, CurrentUser

router = APIRouter(prefix="/students", tags=["students"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def get_student_or_404(student_id: int, db: Session) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student not found"
        )
    return student


def ensure_student_access(student: Student, current_user: User) -> None:
    if (
        current_user.role == UserRole.STUDENT
        and current_user.student_id != student.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not your student record"
        )


@router.post("", response_model=StudentRead, status_code=status.HTTP_201_CREATED)
def create_student(
    student_data: StudentCreate, db: DatabaseSession, _: AdminUser
) -> Student:
    data = student_data.model_dump()
    data["email"] = str(student_data.email).lower()
    student = Student(**data)
    db.add(student)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A student with this email already exists",
        ) from exc
    db.refresh(student)
    return student


@router.get("", response_model=list[StudentRead])
def list_students(
    db: DatabaseSession,
    current_user: CurrentUser,
    q: Annotated[str | None, Query(max_length=100)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[Student]:
    statement = select(Student)
    if current_user.role == UserRole.STUDENT:
        if current_user.student_id is None:
            return []
        statement = statement.where(Student.id == current_user.student_id)
    elif current_user.role == UserRole.HOD:
        statement = statement.where(Student.id.in_(department_student_ids(current_user)))
    elif current_user.role == UserRole.TEACHER:
        statement = statement.where(Student.id.in_(teacher_student_ids(current_user)))
    if q and q.strip():
        search = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                Student.first_name.ilike(search),
                Student.last_name.ilike(search),
                Student.email.ilike(search),
            )
        )
    statement = statement.order_by(Student.id).offset(offset).limit(limit)
    return list(db.scalars(statement).all())


@router.get("/{student_id}", response_model=StudentRead)
def read_student(
    student_id: int, db: DatabaseSession, current_user: CurrentUser
) -> Student:
    student = get_student_or_404(student_id, db)
    ensure_student_access(student, current_user)
    if (
        current_user.role == UserRole.HOD
        and db.scalar(
            select(Student.id)
            .where(
                Student.id == student_id,
                Student.id.in_(department_student_ids(current_user)),
            )
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Student not found")
    if (
        current_user.role == UserRole.TEACHER
        and db.scalar(
            select(Student.id)
            .where(
                Student.id == student_id,
                Student.id.in_(teacher_student_ids(current_user)),
            )
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@router.patch("/{student_id}", response_model=StudentRead)
def update_student(
    student_id: int,
    student_data: StudentUpdate,
    db: DatabaseSession,
    _: AdminUser,
) -> Student:
    student = get_student_or_404(student_id, db)
    changes = student_data.model_dump(exclude_unset=True)
    if any(
        changes.get(field) is None
        for field in ("first_name", "last_name")
        if field in changes
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="first_name and last_name cannot be null",
        )
    if "email" in changes and changes["email"] is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="email cannot be null",
        )
    email = changes.pop("email", None)
    if email is not None:
        email = str(email).lower()
        student.email = email
        if student.user is not None:
            student.user.email = email
    for field, value in changes.items():
        setattr(student, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A student with this email already exists",
        ) from exc
    db.refresh(student)
    return student


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_student(student_id: int, db: DatabaseSession, _: AdminUser) -> None:
    student = get_student_or_404(student_id, db)
    if db.scalar(
        select(FeeAssignment.id)
        .where(FeeAssignment.student_id == student_id)
        .limit(1)
    ) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot delete this student because fee assignments or payment "
                "history exist. Preserve the financial records by keeping this student."
            ),
        )
    db.delete(student)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot delete this student because related financial records "
                "exist. Preserve the financial records by keeping this student."
            ),
        ) from exc

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.enums import UserRole
from app.models import Course, Enrollment, Student, User
from app.schemas import EnrollmentCreate, EnrollmentRead, EnrollmentUpdate
from app.security import AdminUser, CurrentUser

router = APIRouter(prefix="/enrollments", tags=["enrollments"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def get_enrollment_or_404(enrollment_id: int, db: Session) -> Enrollment:
    enrollment = db.get(Enrollment, enrollment_id)
    if enrollment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found"
        )
    return enrollment


def ensure_enrollment_access(enrollment: Enrollment, user: User) -> None:
    if user.role == UserRole.STUDENT and user.student_id != enrollment.student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your enrollment",
        )


def ensure_references_exist(
    student_id: int, course_id: int, db: Session
) -> None:
    if db.get(Student, student_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student not found"
        )
    if db.get(Course, course_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )


@router.post(
    "", response_model=EnrollmentRead, status_code=status.HTTP_201_CREATED
)
def create_enrollment(
    enrollment_data: EnrollmentCreate,
    db: DatabaseSession,
    _: AdminUser,
) -> Enrollment:
    ensure_references_exist(
        enrollment_data.student_id, enrollment_data.course_id, db
    )
    enrollment = Enrollment(**enrollment_data.model_dump())
    db.add(enrollment)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This student is already enrolled in this course",
        ) from exc
    db.refresh(enrollment)
    return enrollment


@router.get("", response_model=list[EnrollmentRead])
def list_enrollments(
    db: DatabaseSession,
    current_user: CurrentUser,
    student_id: Annotated[int | None, Query(gt=0)] = None,
    course_id: Annotated[int | None, Query(gt=0)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[Enrollment]:
    statement = select(Enrollment)
    if current_user.role == UserRole.STUDENT:
        if current_user.student_id is None:
            return []
        statement = statement.where(Enrollment.student_id == current_user.student_id)
    elif student_id is not None:
        statement = statement.where(Enrollment.student_id == student_id)
    if course_id is not None:
        statement = statement.where(Enrollment.course_id == course_id)
    statement = statement.order_by(Enrollment.id).offset(offset).limit(limit)
    return list(db.scalars(statement).all())


@router.get("/{enrollment_id}", response_model=EnrollmentRead)
def read_enrollment(
    enrollment_id: int, db: DatabaseSession, current_user: CurrentUser
) -> Enrollment:
    enrollment = get_enrollment_or_404(enrollment_id, db)
    ensure_enrollment_access(enrollment, current_user)
    return enrollment


@router.patch("/{enrollment_id}", response_model=EnrollmentRead)
def update_enrollment(
    enrollment_id: int,
    enrollment_data: EnrollmentUpdate,
    db: DatabaseSession,
    _: AdminUser,
) -> Enrollment:
    enrollment = get_enrollment_or_404(enrollment_id, db)
    changes = enrollment_data.model_dump(exclude_unset=True)
    student_id = changes.get("student_id", enrollment.student_id)
    course_id = changes.get("course_id", enrollment.course_id)
    if student_id is None or course_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="student_id and course_id cannot be null",
        )
    ensure_references_exist(student_id, course_id, db)
    for field, value in changes.items():
        setattr(enrollment, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This student is already enrolled in this course",
        ) from exc
    db.refresh(enrollment)
    return enrollment


@router.delete("/{enrollment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_enrollment(
    enrollment_id: int, db: DatabaseSession, _: AdminUser
) -> None:
    enrollment = get_enrollment_or_404(enrollment_id, db)
    db.delete(enrollment)
    db.commit()

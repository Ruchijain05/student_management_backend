from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Course, Enrollment, User


def department_course_ids(user: User):
    if user.department_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="HOD account has no assigned department",
        )
    return select(Course.id).where(Course.department_id == user.department_id)


def department_student_ids(user: User):
    if user.department_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="HOD account has no assigned department",
        )
    return (
        select(Enrollment.student_id)
        .join(Course, Course.id == Enrollment.course_id)
        .where(Course.department_id == user.department_id)
    )


def ensure_course_in_department(
    course_id: int, user: User, db: Session
) -> None:
    if user.department_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="HOD account has no assigned department",
        )
    if db.scalar(
        select(Course.id).where(
            Course.id == course_id,
            Course.department_id == user.department_id,
        )
    ) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department record not found",
        )

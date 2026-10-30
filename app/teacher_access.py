from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Enrollment, TeacherCourse, User


def teacher_course_ids(user: User):
    if user.teacher_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher account has no linked teacher record",
        )
    return select(TeacherCourse.course_id).where(
        TeacherCourse.teacher_id == user.teacher_id
    )


def teacher_student_ids(user: User):
    return select(Enrollment.student_id).where(
        Enrollment.course_id.in_(teacher_course_ids(user))
    )


def ensure_teacher_course(course_id: int, user: User, db: Session) -> None:
    if user.teacher_id is None or db.scalar(
        select(TeacherCourse.id).where(
            TeacherCourse.teacher_id == user.teacher_id,
            TeacherCourse.course_id == course_id,
        )
    ) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assigned course record not found",
        )


def ensure_course_student_enrolled(
    course_id: int, student_id: int, db: Session
) -> None:
    if db.scalar(
        select(Enrollment.id).where(
            Enrollment.course_id == course_id,
            Enrollment.student_id == student_id,
        )
    ) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Student must be enrolled in the assigned course",
        )

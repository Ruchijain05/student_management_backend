from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.enums import AttendanceStatus, UserRole
from app.models import Attendance, Course, Enrollment, Mark, Student
from app.schemas import AdminDashboard, StudentDashboard
from app.security import CurrentUser

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("/admin", response_model=AdminDashboard)
def admin_dashboard(
    db: DatabaseSession, current_user: CurrentUser
) -> AdminDashboard:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="admin role required"
        )
    return AdminDashboard(
        total_students=db.scalar(select(func.count()).select_from(Student)) or 0,
        total_courses=db.scalar(select(func.count()).select_from(Course)) or 0,
        total_enrollments=db.scalar(
            select(func.count()).select_from(Enrollment)
        )
        or 0,
        attendance_records_today=db.scalar(
            select(func.count())
            .select_from(Attendance)
            .where(Attendance.attendance_date == date.today())
        )
        or 0,
        total_assessments=db.scalar(select(func.count()).select_from(Mark)) or 0,
    )


@router.get("/student", response_model=StudentDashboard)
def student_dashboard(
    db: DatabaseSession, current_user: CurrentUser
) -> StudentDashboard:
    if (
        current_user.role != UserRole.STUDENT
        or current_user.student_id is None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Linked student account required",
        )
    student_id = current_user.student_id
    records = list(
        db.scalars(
            select(Attendance).where(Attendance.student_id == student_id)
        ).all()
    )
    attendance_percentage = (
        100
        * sum(
            record.status in (AttendanceStatus.PRESENT, AttendanceStatus.LATE)
            for record in records
        )
        / len(records)
        if records
        else 0.0
    )
    marks = list(
        db.scalars(select(Mark).where(Mark.student_id == student_id)).all()
    )
    average_percentage = (
        sum(float(mark.score / mark.max_score * 100) for mark in marks) / len(marks)
        if marks
        else None
    )
    return StudentDashboard(
        student_id=student_id,
        enrolled_courses=db.scalar(
            select(func.count())
            .select_from(Enrollment)
            .where(Enrollment.student_id == student_id)
        )
        or 0,
        attendance_records=len(records),
        attendance_percentage=round(attendance_percentage, 2),
        assessments_recorded=len(marks),
        average_percentage=(
            round(average_percentage, 2)
            if average_percentage is not None
            else None
        ),
    )

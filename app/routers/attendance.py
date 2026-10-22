from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.academic import ensure_student_enrolled
from app.enums import UserRole
from app.models import Attendance, User
from app.schemas import AttendanceCreate, AttendanceRead, AttendanceUpdate
from app.security import AdminUser, CurrentUser

router = APIRouter(prefix="/attendance", tags=["attendance"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def get_record_or_404(record_id: int, db: Session) -> Attendance:
    record = db.get(Attendance, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendance record not found",
        )
    return record


def ensure_attendance_access(record: Attendance, user: User) -> None:
    if user.role == UserRole.STUDENT and user.student_id != record.student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your attendance record",
        )


@router.post("", response_model=AttendanceRead, status_code=status.HTTP_201_CREATED)
def create_attendance(
    attendance_data: AttendanceCreate,
    db: DatabaseSession,
    _: AdminUser,
) -> Attendance:
    ensure_student_enrolled(
        attendance_data.student_id, attendance_data.course_id, db
    )
    record = Attendance(**attendance_data.model_dump())
    db.add(record)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attendance is already recorded for this student, course, and date",
        ) from exc
    db.refresh(record)
    return record


@router.get("", response_model=list[AttendanceRead])
def list_attendance(
    db: DatabaseSession,
    current_user: CurrentUser,
    student_id: Annotated[int | None, Query(gt=0)] = None,
    course_id: Annotated[int | None, Query(gt=0)] = None,
    attendance_date: date | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[Attendance]:
    statement = select(Attendance)
    if current_user.role == UserRole.STUDENT:
        if current_user.student_id is None:
            return []
        statement = statement.where(Attendance.student_id == current_user.student_id)
    elif student_id is not None:
        statement = statement.where(Attendance.student_id == student_id)
    if course_id is not None:
        statement = statement.where(Attendance.course_id == course_id)
    if attendance_date is not None:
        statement = statement.where(Attendance.attendance_date == attendance_date)
    statement = (
        statement.order_by(Attendance.attendance_date.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


@router.get("/{record_id}", response_model=AttendanceRead)
def read_attendance(
    record_id: int, db: DatabaseSession, current_user: CurrentUser
) -> Attendance:
    record = get_record_or_404(record_id, db)
    ensure_attendance_access(record, current_user)
    return record


@router.patch("/{record_id}", response_model=AttendanceRead)
def update_attendance(
    record_id: int,
    attendance_data: AttendanceUpdate,
    db: DatabaseSession,
    _: AdminUser,
) -> Attendance:
    record = get_record_or_404(record_id, db)
    record.status = attendance_data.status
    db.commit()
    db.refresh(record)
    return record


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attendance(record_id: int, db: DatabaseSession, _: AdminUser) -> None:
    record = get_record_or_404(record_id, db)
    db.delete(record)
    db.commit()

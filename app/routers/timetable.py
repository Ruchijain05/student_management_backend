from datetime import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.department_access import department_course_ids, ensure_course_in_department
from app.teacher_access import ensure_teacher_course, teacher_course_ids
from app.enums import UserRole
from app.models import Course, CourseTimetableEntry, Enrollment, User
from app.schemas import (
    TimetableEntryCreate,
    TimetableEntryRead,
    TimetableEntryUpdate,
)
from app.security import AdminUser, CurrentUser

router = APIRouter(prefix="/timetable", tags=["timetable"])
DatabaseSession = Annotated[Session, Depends(get_db)]
WEEKDAY_ORDER = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
)


def get_entry_or_404(entry_id: int, db: Session) -> CourseTimetableEntry:
    entry = db.get(CourseTimetableEntry, entry_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Timetable entry not found",
        )
    return entry


def ensure_entry_access(
    entry: CourseTimetableEntry, user: User, db: Session
) -> None:
    if user.role == UserRole.STUDENT and (
        user.student_id is None
        or db.scalar(
            select(Enrollment.id).where(
                Enrollment.student_id == user.student_id,
                Enrollment.course_id == entry.course_id,
            )
        )
        is None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Timetable entry not found",
        )
    if user.role == UserRole.HOD:
        ensure_course_in_department(entry.course_id, user, db)
    if user.role == UserRole.TEACHER:
        ensure_teacher_course(entry.course_id, user, db)


def ensure_no_overlap(
    course_id: int,
    weekday: str,
    start_time: time,
    end_time: time,
    db: Session,
    exclude_entry_id: int | None = None,
) -> None:
    statement = select(CourseTimetableEntry.id).where(
        CourseTimetableEntry.course_id == course_id,
        CourseTimetableEntry.weekday == weekday,
        CourseTimetableEntry.start_time < end_time,
        CourseTimetableEntry.end_time > start_time,
    )
    if exclude_entry_id is not None:
        statement = statement.where(
            CourseTimetableEntry.id != exclude_entry_id
        )
    if db.scalar(statement) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This class overlaps another schedule for the course",
        )


@router.post(
    "", response_model=TimetableEntryRead, status_code=status.HTTP_201_CREATED
)
def create_timetable_entry(
    entry_data: TimetableEntryCreate,
    db: DatabaseSession,
    _: AdminUser,
) -> CourseTimetableEntry:
    if db.get(Course, entry_data.course_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )
    ensure_no_overlap(
        entry_data.course_id,
        entry_data.weekday,
        entry_data.start_time,
        entry_data.end_time,
        db,
    )
    entry = CourseTimetableEntry(**entry_data.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("", response_model=list[TimetableEntryRead])
def list_timetable_entries(
    db: DatabaseSession,
    current_user: CurrentUser,
    course_id: Annotated[int | None, Query(gt=0)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[CourseTimetableEntry]:
    statement = select(CourseTimetableEntry).options(
        joinedload(CourseTimetableEntry.course)
    )
    if current_user.role == UserRole.STUDENT:
        if current_user.student_id is None:
            return []
        statement = (
            statement.join(
                Enrollment,
                Enrollment.course_id == CourseTimetableEntry.course_id,
            )
            .where(Enrollment.student_id == current_user.student_id)
        )
    elif current_user.role == UserRole.HOD:
        statement = statement.where(
            CourseTimetableEntry.course_id.in_(department_course_ids(current_user))
        )
    elif current_user.role == UserRole.TEACHER:
        statement = statement.where(
            CourseTimetableEntry.course_id.in_(teacher_course_ids(current_user))
        )
    elif course_id is not None:
        statement = statement.where(
            CourseTimetableEntry.course_id == course_id
        )
    weekday_order = case(
        {day: index for index, day in enumerate(WEEKDAY_ORDER)},
        value=CourseTimetableEntry.weekday,
        else_=len(WEEKDAY_ORDER),
    )
    statement = (
        statement.order_by(
            weekday_order, CourseTimetableEntry.start_time, CourseTimetableEntry.id
        )
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).unique().all())


@router.get("/{entry_id}", response_model=TimetableEntryRead)
def read_timetable_entry(
    entry_id: int, db: DatabaseSession, current_user: CurrentUser
) -> CourseTimetableEntry:
    entry = get_entry_or_404(entry_id, db)
    ensure_entry_access(entry, current_user, db)
    return entry


@router.patch("/{entry_id}", response_model=TimetableEntryRead)
def update_timetable_entry(
    entry_id: int,
    entry_data: TimetableEntryUpdate,
    db: DatabaseSession,
    _: AdminUser,
) -> CourseTimetableEntry:
    entry = get_entry_or_404(entry_id, db)
    changes = entry_data.model_dump(exclude_unset=True)
    required_fields = (
        "course_id",
        "weekday",
        "start_time",
        "end_time",
        "classroom_number",
    )
    if any(
        changes.get(field) is None for field in required_fields if field in changes
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Timetable entry fields cannot be null",
        )

    course_id = changes.get("course_id", entry.course_id)
    weekday = changes.get("weekday", entry.weekday)
    start_time = changes.get("start_time", entry.start_time)
    end_time = changes.get("end_time", entry.end_time)
    if db.get(Course, course_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )
    if end_time <= start_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_time must be later than start_time",
        )
    ensure_no_overlap(
        course_id,
        weekday,
        start_time,
        end_time,
        db,
        exclude_entry_id=entry.id,
    )
    for field, value in changes.items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_timetable_entry(
    entry_id: int, db: DatabaseSession, _: AdminUser
) -> None:
    entry = get_entry_or_404(entry_id, db)
    db.delete(entry)
    db.commit()

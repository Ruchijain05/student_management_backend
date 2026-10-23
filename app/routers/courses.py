from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Course, FeeAssignment
from app.schemas import CourseCreate, CourseRead, CourseUpdate
from app.security import AdminUser, CurrentUser

router = APIRouter(prefix="/courses", tags=["courses"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def get_course_or_404(course_id: int, db: Session) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )
    return course


@router.post("", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(
    course_data: CourseCreate, db: DatabaseSession, _: AdminUser
) -> Course:
    course = Course(**course_data.model_dump())
    db.add(course)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A course with this code already exists",
        ) from exc
    db.refresh(course)
    return course


@router.get("", response_model=list[CourseRead])
def list_courses(
    db: DatabaseSession,
    _: CurrentUser,
    q: Annotated[str | None, Query(max_length=100)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[Course]:
    statement = select(Course)
    if q and q.strip():
        search = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                Course.code.ilike(search),
                Course.title.ilike(search),
                Course.description.ilike(search),
            )
        )
    statement = statement.order_by(Course.id).offset(offset).limit(limit)
    return list(db.scalars(statement).all())


@router.get("/{course_id}", response_model=CourseRead)
def read_course(course_id: int, db: DatabaseSession, _: CurrentUser) -> Course:
    return get_course_or_404(course_id, db)


@router.patch("/{course_id}", response_model=CourseRead)
def update_course(
    course_id: int,
    course_data: CourseUpdate,
    db: DatabaseSession,
    _: AdminUser,
) -> Course:
    course = get_course_or_404(course_id, db)
    changes = course_data.model_dump(exclude_unset=True)
    if any(changes.get(field) is None for field in ("code", "title") if field in changes):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="code and title cannot be null",
        )
    if "course_fee" in changes:
        assignments = db.scalars(
            select(FeeAssignment)
            .options(selectinload(FeeAssignment.payments))
            .where(FeeAssignment.course_id == course_id)
        ).all()
        if changes["course_fee"] is None and assignments:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="A course fee cannot be cleared while student fee assignments exist",
            )
        if changes["course_fee"] is not None:
            for assignment in assignments:
                paid_fee = sum(
                    (payment.amount for payment in assignment.payments),
                    start=0,
                )
                if changes["course_fee"] < paid_fee:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail=(
                            "Course fee cannot be less than payments already "
                            "recorded for an enrolled student"
                        ),
                    )
                assignment.total_fee = changes["course_fee"]
    for field, value in changes.items():
        setattr(course, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A course with this code already exists",
        ) from exc
    db.refresh(course)
    return course


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(course_id: int, db: DatabaseSession, _: AdminUser) -> None:
    course = get_course_or_404(course_id, db)
    db.delete(course)
    db.commit()

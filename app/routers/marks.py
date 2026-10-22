from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.academic import ensure_student_enrolled
from app.database import get_db
from app.enums import UserRole
from app.models import Mark, User
from app.schemas import MarkCreate, MarkRead, MarkUpdate
from app.security import AdminUser, CurrentUser

router = APIRouter(prefix="/marks", tags=["marks"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def get_mark_or_404(mark_id: int, db: Session) -> Mark:
    mark = db.get(Mark, mark_id)
    if mark is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Mark not found"
        )
    return mark


def ensure_mark_access(mark: Mark, user: User) -> None:
    if user.role == UserRole.STUDENT and user.student_id != mark.student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not your mark"
        )


@router.post("", response_model=MarkRead, status_code=status.HTTP_201_CREATED)
def create_mark(
    mark_data: MarkCreate, db: DatabaseSession, _: AdminUser
) -> Mark:
    ensure_student_enrolled(mark_data.student_id, mark_data.course_id, db)
    mark = Mark(**mark_data.model_dump())
    db.add(mark)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This assessment already has a mark for the student",
        ) from exc
    db.refresh(mark)
    return mark


@router.get("", response_model=list[MarkRead])
def list_marks(
    db: DatabaseSession,
    current_user: CurrentUser,
    student_id: Annotated[int | None, Query(gt=0)] = None,
    course_id: Annotated[int | None, Query(gt=0)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[Mark]:
    statement = select(Mark)
    if current_user.role == UserRole.STUDENT:
        if current_user.student_id is None:
            return []
        statement = statement.where(Mark.student_id == current_user.student_id)
    elif student_id is not None:
        statement = statement.where(Mark.student_id == student_id)
    if course_id is not None:
        statement = statement.where(Mark.course_id == course_id)
    statement = statement.order_by(Mark.id).offset(offset).limit(limit)
    return list(db.scalars(statement).all())


@router.get("/{mark_id}", response_model=MarkRead)
def read_mark(mark_id: int, db: DatabaseSession, current_user: CurrentUser) -> Mark:
    mark = get_mark_or_404(mark_id, db)
    ensure_mark_access(mark, current_user)
    return mark


@router.patch("/{mark_id}", response_model=MarkRead)
def update_mark(
    mark_id: int, mark_data: MarkUpdate, db: DatabaseSession, _: AdminUser
) -> Mark:
    mark = get_mark_or_404(mark_id, db)
    changes = mark_data.model_dump(exclude_unset=True)
    score = changes.get("score", mark.score)
    max_score = changes.get("max_score", mark.max_score)
    if score is None or max_score is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="score and max_score cannot be null",
        )
    if score > max_score:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="score cannot be greater than max_score",
        )
    if "assessment_name" in changes and changes["assessment_name"] is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="assessment_name cannot be null",
        )
    for field, value in changes.items():
        setattr(mark, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This assessment already has a mark for the student",
        ) from exc
    db.refresh(mark)
    return mark


@router.delete("/{mark_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mark(mark_id: int, db: DatabaseSession, _: AdminUser) -> None:
    mark = get_mark_or_404(mark_id, db)
    db.delete(mark)
    db.commit()

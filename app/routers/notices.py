from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.enums import UserRole
from app.models import Notice
from app.schemas import NoticeCreate, NoticeRead, NoticeUpdate
from app.security import AdminUser, CurrentUser

router = APIRouter(prefix="/notices", tags=["notices"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def get_notice_or_404(notice_id: int, db: Session) -> Notice:
    notice = db.get(Notice, notice_id)
    if notice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notice not found",
        )
    return notice


@router.post("", response_model=NoticeRead, status_code=status.HTTP_201_CREATED)
def create_notice(
    notice_data: NoticeCreate,
    db: DatabaseSession,
    _: AdminUser,
) -> Notice:
    notice = Notice(**notice_data.model_dump())
    db.add(notice)
    db.commit()
    db.refresh(notice)
    return notice


@router.get("", response_model=list[NoticeRead])
def list_notices(
    db: DatabaseSession,
    _: CurrentUser,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[Notice]:
    if _.role == UserRole.HOD:
        raise HTTPException(status_code=403, detail="Campus notices are not available to HOD accounts")
    if _.role == UserRole.TEACHER:
        raise HTTPException(status_code=403, detail="Campus notices are not available to teachers")
    statement = (
        select(Notice)
        .order_by(Notice.notice_date.desc(), Notice.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


@router.get("/{notice_id}", response_model=NoticeRead)
def read_notice(
    notice_id: int,
    db: DatabaseSession,
    _: CurrentUser,
) -> Notice:
    if _.role == UserRole.HOD:
        raise HTTPException(status_code=403, detail="Campus notices are not available to HOD accounts")
    if _.role == UserRole.TEACHER:
        raise HTTPException(status_code=403, detail="Campus notices are not available to teachers")
    return get_notice_or_404(notice_id, db)


@router.patch("/{notice_id}", response_model=NoticeRead)
def update_notice(
    notice_id: int,
    notice_data: NoticeUpdate,
    db: DatabaseSession,
    _: AdminUser,
) -> Notice:
    notice = get_notice_or_404(notice_id, db)
    changes = notice_data.model_dump(exclude_unset=True)
    required_fields = ("title", "description", "notice_date")
    if any(
        changes.get(field) is None
        for field in required_fields
        if field in changes
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="title, description, and notice_date cannot be null",
        )
    for field, value in changes.items():
        setattr(notice, field, value)
    db.commit()
    db.refresh(notice)
    return notice


@router.delete("/{notice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notice(
    notice_id: int,
    db: DatabaseSession,
    _: AdminUser,
) -> None:
    notice = get_notice_or_404(notice_id, db)
    db.delete(notice)
    db.commit()

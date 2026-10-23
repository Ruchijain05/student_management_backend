from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.enums import SportsLevel, UserRole
from app.models import SportsAchievement, Student, User
from app.schemas import (
    SportsAchievementCreate,
    SportsAchievementRead,
    SportsAchievementUpdate,
)
from app.security import AdminUser, CurrentUser

router = APIRouter(prefix="/sports", tags=["sports"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def get_achievement_or_404(
    achievement_id: int, db: Session
) -> SportsAchievement:
    achievement = db.get(SportsAchievement, achievement_id)
    if achievement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sports achievement not found",
        )
    return achievement


def ensure_achievement_access(
    achievement: SportsAchievement, user: User
) -> None:
    if user.role == UserRole.STUDENT and user.student_id != achievement.student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your sports achievement",
        )


@router.post(
    "", response_model=SportsAchievementRead, status_code=status.HTTP_201_CREATED
)
def create_achievement(
    achievement_data: SportsAchievementCreate,
    db: DatabaseSession,
    _: AdminUser,
) -> SportsAchievement:
    if db.get(Student, achievement_data.student_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student not found"
        )
    achievement = SportsAchievement(**achievement_data.model_dump())
    db.add(achievement)
    db.commit()
    db.refresh(achievement)
    return achievement


@router.get("", response_model=list[SportsAchievementRead])
def list_achievements(
    db: DatabaseSession,
    current_user: CurrentUser,
    student_id: Annotated[int | None, Query(gt=0)] = None,
    sport_name: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    level: SportsLevel | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[SportsAchievement]:
    statement = select(SportsAchievement)
    if current_user.role == UserRole.STUDENT:
        if current_user.student_id is None:
            return []
        statement = statement.where(
            SportsAchievement.student_id == current_user.student_id
        )
    elif student_id is not None:
        statement = statement.where(SportsAchievement.student_id == student_id)
    if sport_name is not None:
        statement = statement.where(
            SportsAchievement.sport_name.ilike(f"%{sport_name.strip()}%")
        )
    if level is not None:
        statement = statement.where(SportsAchievement.level == level)
    statement = (
        statement.order_by(
            SportsAchievement.achievement_date.desc(), SportsAchievement.id.desc()
        )
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement).all())


@router.get("/{achievement_id}", response_model=SportsAchievementRead)
def read_achievement(
    achievement_id: int, db: DatabaseSession, current_user: CurrentUser
) -> SportsAchievement:
    achievement = get_achievement_or_404(achievement_id, db)
    ensure_achievement_access(achievement, current_user)
    return achievement


@router.patch("/{achievement_id}", response_model=SportsAchievementRead)
def update_achievement(
    achievement_id: int,
    achievement_data: SportsAchievementUpdate,
    db: DatabaseSession,
    _: AdminUser,
) -> SportsAchievement:
    achievement = get_achievement_or_404(achievement_id, db)
    changes = achievement_data.model_dump(exclude_unset=True)
    required_fields = ("sport_name", "level", "achievement_date")
    if any(changes.get(field) is None for field in required_fields if field in changes):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="sport_name, level, and achievement_date cannot be null",
        )
    for field, value in changes.items():
        setattr(achievement, field, value)
    db.commit()
    db.refresh(achievement)
    return achievement


@router.delete("/{achievement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_achievement(
    achievement_id: int, db: DatabaseSession, _: AdminUser
) -> None:
    achievement = get_achievement_or_404(achievement_id, db)
    db.delete(achievement)
    db.commit()

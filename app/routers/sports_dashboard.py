from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.enums import SportsLevel
from app.models import SportsAchievement, Student
from app.schemas import (
    SportsDashboard,
    SportsRecentAchievement,
    SportsSportSummary,
)
from app.security import AdminUser

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("/sports", response_model=SportsDashboard)
def sports_dashboard(db: DatabaseSession, _: AdminUser) -> SportsDashboard:
    total_athletes = db.scalar(
        select(func.count(func.distinct(SportsAchievement.student_id)))
    ) or 0
    total_achievements = db.scalar(
        select(func.count()).select_from(SportsAchievement)
    ) or 0

    level_stats = {
        level: (athlete_count, achievement_count)
        for level, athlete_count, achievement_count in db.execute(
            select(
                SportsAchievement.level,
                func.count(func.distinct(SportsAchievement.student_id)),
                func.count(SportsAchievement.id),
            )
            .group_by(SportsAchievement.level)
        ).all()
    }
    sport_rows = db.execute(
        select(
            SportsAchievement.sport_name,
            func.count(func.distinct(SportsAchievement.student_id)),
            func.count(SportsAchievement.id),
        )
        .group_by(SportsAchievement.sport_name)
        .order_by(SportsAchievement.sport_name)
    ).all()
    sport_breakdown = [
        SportsSportSummary(
            sport_name=sport_name,
            athlete_count=athlete_count,
            achievement_count=achievement_count,
        )
        for sport_name, athlete_count, achievement_count in sport_rows
    ]

    recent_rows = db.execute(
        select(SportsAchievement, Student.first_name, Student.last_name)
        .join(Student, SportsAchievement.student_id == Student.id)
        .order_by(
            SportsAchievement.achievement_date.desc(), SportsAchievement.id.desc()
        )
        .limit(10)
    ).all()
    recent_achievements = [
        SportsRecentAchievement(
            id=achievement.id,
            student_id=achievement.student_id,
            student_name=f"{first_name} {last_name}",
            sport_name=achievement.sport_name,
            level=achievement.level,
            event_name=achievement.event_name,
            competition_name=achievement.competition_name,
            achievement_date=achievement.achievement_date,
            result=achievement.result,
        )
        for achievement, first_name, last_name in recent_rows
    ]

    return SportsDashboard(
        total_athletes=total_athletes,
        total_achievements=total_achievements,
        district_athletes=level_stats.get(SportsLevel.DISTRICT, (0, 0))[0],
        state_athletes=level_stats.get(SportsLevel.STATE, (0, 0))[0],
        national_athletes=level_stats.get(SportsLevel.NATIONAL, (0, 0))[0],
        district_achievements=level_stats.get(SportsLevel.DISTRICT, (0, 0))[1],
        state_achievements=level_stats.get(SportsLevel.STATE, (0, 0))[1],
        national_achievements=level_stats.get(SportsLevel.NATIONAL, (0, 0))[1],
        sport_breakdown=sport_breakdown,
        recent_achievements=recent_achievements,
    )

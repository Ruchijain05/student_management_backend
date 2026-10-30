from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.department_access import department_course_ids
from app.teacher_access import teacher_course_ids
from app.enums import UserRole
from app.models import Course, Mark
from app.schemas import CourseResult
from app.security import CurrentUser

router = APIRouter(prefix="/results", tags=["results"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def grade_for_percentage(percentage: float) -> str:
    if percentage >= 90:
        return "A"
    if percentage >= 80:
        return "B"
    if percentage >= 70:
        return "C"
    if percentage >= 60:
        return "D"
    return "F"


@router.get("", response_model=list[CourseResult])
def list_results(
    db: DatabaseSession,
    current_user: CurrentUser,
    student_id: Annotated[int | None, Query(gt=0)] = None,
) -> list[CourseResult]:
    if current_user.role == UserRole.STUDENT:
        if current_user.student_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Student account has no linked student record",
            )
        student_id = current_user.student_id
    statement = select(Mark, Course).join(Course, Course.id == Mark.course_id)
    if current_user.role == UserRole.HOD:
        statement = statement.where(Course.id.in_(department_course_ids(current_user)))
    elif current_user.role == UserRole.TEACHER:
        statement = statement.where(Course.id.in_(teacher_course_ids(current_user)))
    if student_id is not None:
        statement = statement.where(Mark.student_id == student_id)

    grouped: dict[tuple[int, int], dict[str, object]] = defaultdict(
        lambda: {"percentages": [], "course": None}
    )
    for mark, course in db.execute(statement.order_by(Mark.student_id, Course.id)):
        item = grouped[(mark.student_id, course.id)]
        percentages = item["percentages"]
        if isinstance(percentages, list):
            percentages.append(float(mark.score / mark.max_score * 100))
        item["course"] = course

    results: list[CourseResult] = []
    for (result_student_id, course_id), item in grouped.items():
        percentages = item["percentages"]
        course = item["course"]
        if not isinstance(percentages, list) or not isinstance(course, Course):
            continue
        average = sum(percentages) / len(percentages)
        results.append(
            CourseResult(
                student_id=result_student_id,
                course_id=course_id,
                course_code=course.code,
                course_title=course.title,
                assessment_count=len(percentages),
                average_percentage=round(average, 2),
                grade=grade_for_percentage(average),
            )
        )
    return results

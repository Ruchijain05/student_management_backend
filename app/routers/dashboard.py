from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.enums import AttendanceStatus, UserRole
from app.models import Attendance, Course, Department, Enrollment, Mark, Student, Teacher, TeacherCourse
from app.schemas import AdminDashboard, HODDashboard, PrincipalDashboard, StudentDashboard, TeacherDashboard
from app.security import CurrentUser, HODUser, PrincipalUser, TeacherUser

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


@router.get("/principal", response_model=PrincipalDashboard)
def principal_dashboard(
    db: DatabaseSession, _: PrincipalUser
) -> PrincipalDashboard:
    result_groups = (
        select(Mark.student_id, Mark.course_id)
        .group_by(Mark.student_id, Mark.course_id)
        .subquery()
    )
    return PrincipalDashboard(
        total_students=db.scalar(select(func.count()).select_from(Student)) or 0,
        total_courses=db.scalar(select(func.count()).select_from(Course)) or 0,
        total_attendance=db.scalar(
            select(func.count()).select_from(Attendance)
        )
        or 0,
        total_marks=db.scalar(select(func.count()).select_from(Mark)) or 0,
        total_results=db.scalar(
            select(func.count()).select_from(result_groups)
        )
        or 0,
    )


@router.get("/hod", response_model=HODDashboard)
def hod_dashboard(db: DatabaseSession, current_user: HODUser) -> HODDashboard:
    department_id = current_user.department_id
    department = db.get(Department, department_id)
    if department is None:
        raise HTTPException(status_code=403, detail="Assigned department not found")
    dept_courses = select(Course.id).where(Course.department_id == department_id)
    dept_students = (
        select(Enrollment.student_id)
        .join(Course, Course.id == Enrollment.course_id)
        .where(Course.department_id == department_id)
        .distinct()
    )
    result_groups = (
        select(Mark.student_id, Mark.course_id)
        .join(Course, Course.id == Mark.course_id)
        .where(Course.department_id == department_id)
        .group_by(Mark.student_id, Mark.course_id)
        .subquery()
    )
    return HODDashboard(
        department_id=department_id,
        department_name=department.name,
        total_students=db.scalar(
            select(func.count()).select_from(dept_students.subquery())
        )
        or 0,
        total_courses=db.scalar(
            select(func.count()).select_from(Course).where(
                Course.department_id == department_id
            )
        )
        or 0,
        total_teachers=db.scalar(
            select(func.count()).select_from(Teacher).where(
                Teacher.department_id == department_id
            )
        )
        or 0,
        total_enrollments=db.scalar(
            select(func.count()).select_from(Enrollment).where(
                Enrollment.course_id.in_(dept_courses)
            )
        )
        or 0,
        total_attendance=db.scalar(
            select(func.count()).select_from(Attendance).where(
                Attendance.course_id.in_(dept_courses)
            )
        )
        or 0,
        total_marks=db.scalar(
            select(func.count()).select_from(Mark).where(
                Mark.course_id.in_(dept_courses)
            )
        )
        or 0,
        total_results=db.scalar(
            select(func.count()).select_from(result_groups)
        )
        or 0,
    )


@router.get("/teacher", response_model=TeacherDashboard)
def teacher_dashboard(
    db: DatabaseSession, current_user: TeacherUser
) -> TeacherDashboard:
    course_ids = select(TeacherCourse.course_id).where(
        TeacherCourse.teacher_id == current_user.teacher_id
    )
    students = (
        select(Enrollment.student_id)
        .where(Enrollment.course_id.in_(course_ids))
        .distinct()
    )
    result_groups = (
        select(Mark.student_id, Mark.course_id)
        .where(Mark.course_id.in_(course_ids))
        .group_by(Mark.student_id, Mark.course_id)
        .subquery()
    )
    return TeacherDashboard(
        total_courses=db.scalar(
            select(func.count()).select_from(TeacherCourse).where(
                TeacherCourse.teacher_id == current_user.teacher_id
            )
        )
        or 0,
        total_students=db.scalar(
            select(func.count()).select_from(students.subquery())
        )
        or 0,
        total_enrollments=db.scalar(
            select(func.count()).select_from(Enrollment).where(
                Enrollment.course_id.in_(course_ids)
            )
        )
        or 0,
        total_attendance=db.scalar(
            select(func.count()).select_from(Attendance).where(
                Attendance.course_id.in_(course_ids)
            )
        )
        or 0,
        total_marks=db.scalar(
            select(func.count()).select_from(Mark).where(
                Mark.course_id.in_(course_ids)
            )
        )
        or 0,
        total_results=db.scalar(select(func.count()).select_from(result_groups)) or 0,
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

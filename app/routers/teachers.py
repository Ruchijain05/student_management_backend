from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.enums import UserRole
from app.models import Course, Department, Teacher, TeacherCourse, User
from app.schemas import (
    CourseRead,
    TeacherCourseCreate,
    TeacherCourseRead,
    TeacherCreate,
    TeacherRead,
    TeacherUpdate,
)
from app.security import AdminUser, CurrentUser

router = APIRouter(prefix="/teachers", tags=["teachers"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def teacher_or_404(teacher_id: int, db: Session) -> Teacher:
    teacher = db.get(Teacher, teacher_id)
    if teacher is None:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return teacher


def ensure_department_exists(department_id: int, db: Session) -> None:
    if db.get(Department, department_id) is None:
        raise HTTPException(status_code=404, detail="Department not found")


@router.post("", response_model=TeacherRead, status_code=201)
def create_teacher(
    data: TeacherCreate, db: DatabaseSession, _: AdminUser
) -> Teacher:
    ensure_department_exists(data.department_id, db)
    teacher_data = data.model_dump()
    teacher_data["email"] = str(data.email).lower()
    teacher = Teacher(**teacher_data)
    db.add(teacher)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Teacher email already exists") from exc
    db.refresh(teacher)
    return teacher


@router.get("", response_model=list[TeacherRead])
def list_teachers(
    db: DatabaseSession,
    current_user: CurrentUser,
    department_id: Annotated[int | None, Query(gt=0)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[Teacher]:
    statement = select(Teacher)
    if current_user.role == UserRole.HOD:
        if current_user.department_id is None:
            return []
        statement = statement.where(Teacher.department_id == current_user.department_id)
    elif current_user.role == UserRole.TEACHER:
        statement = statement.where(Teacher.id == current_user.teacher_id)
    elif current_user.role == UserRole.ADMIN:
        if department_id is not None:
            statement = statement.where(Teacher.department_id == department_id)
    else:
        raise HTTPException(status_code=403, detail="Teacher access denied")
    return list(db.scalars(statement.order_by(Teacher.name).offset(offset).limit(limit)).all())


@router.get("/assignments", response_model=list[TeacherCourseRead])
def list_teacher_assignments(
    db: DatabaseSession,
    _: AdminUser,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> list[TeacherCourse]:
    return list(
        db.scalars(
            select(TeacherCourse).order_by(
                TeacherCourse.teacher_id, TeacherCourse.course_id
            ).offset(offset).limit(limit)
        ).all()
    )


@router.get("/{teacher_id}", response_model=TeacherRead)
def read_teacher(
    teacher_id: int, db: DatabaseSession, current_user: CurrentUser
) -> Teacher:
    teacher = teacher_or_404(teacher_id, db)
    if current_user.role not in (UserRole.ADMIN, UserRole.HOD, UserRole.TEACHER) or (
        current_user.role == UserRole.HOD
        and current_user.department_id != teacher.department_id
    ) or (
        current_user.role == UserRole.TEACHER
        and current_user.teacher_id != teacher.id
    ):
        raise HTTPException(status_code=404, detail="Teacher not found")
    return teacher


@router.get("/{teacher_id}/courses", response_model=list[CourseRead])
def list_teacher_courses(
    teacher_id: int, db: DatabaseSession, current_user: CurrentUser
) -> list[Course]:
    teacher = teacher_or_404(teacher_id, db)
    if current_user.role == UserRole.TEACHER and current_user.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="Teacher not found")
    if current_user.role == UserRole.HOD and current_user.department_id != teacher.department_id:
        raise HTTPException(status_code=404, detail="Teacher not found")
    if current_user.role not in (UserRole.ADMIN, UserRole.HOD, UserRole.TEACHER):
        raise HTTPException(status_code=403, detail="Teacher course access denied")
    return list(
        db.scalars(
            select(Course)
            .join(TeacherCourse, TeacherCourse.course_id == Course.id)
            .where(TeacherCourse.teacher_id == teacher_id)
            .order_by(Course.id)
        ).all()
    )


@router.post(
    "/{teacher_id}/courses",
    response_model=TeacherCourseRead,
    status_code=201,
)
def assign_teacher_course(
    teacher_id: int,
    data: TeacherCourseCreate,
    db: DatabaseSession,
    _: AdminUser,
) -> TeacherCourse:
    teacher = teacher_or_404(teacher_id, db)
    course = db.get(Course, data.course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.department_id != teacher.department_id:
        raise HTTPException(
            status_code=422,
            detail="Teacher and course must belong to the same department",
        )
    assignment = TeacherCourse(teacher_id=teacher_id, course_id=data.course_id)
    db.add(assignment)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Teacher is already assigned to this course") from exc
    db.refresh(assignment)
    return assignment


@router.delete("/{teacher_id}/courses/{course_id}", status_code=204)
def remove_teacher_course(
    teacher_id: int,
    course_id: int,
    db: DatabaseSession,
    _: AdminUser,
) -> None:
    assignment = db.scalar(
        select(TeacherCourse).where(
            TeacherCourse.teacher_id == teacher_id,
            TeacherCourse.course_id == course_id,
        )
    )
    if assignment is None:
        raise HTTPException(status_code=404, detail="Teacher course assignment not found")
    db.delete(assignment)
    db.commit()


@router.patch("/{teacher_id}", response_model=TeacherRead)
def update_teacher(
    teacher_id: int,
    data: TeacherUpdate,
    db: DatabaseSession,
    _: AdminUser,
) -> Teacher:
    teacher = teacher_or_404(teacher_id, db)
    changes = data.model_dump(exclude_unset=True)
    if any(
        changes.get(field) is None
        for field in ("name", "email", "department_id")
        if field in changes
    ):
        raise HTTPException(
            status_code=422,
            detail="name, email, and department_id cannot be null",
        )
    if changes.get("department_id") is not None:
        ensure_department_exists(changes["department_id"], db)
    if changes.get("email") is not None:
        changes["email"] = str(changes["email"]).lower()
    for field, value in changes.items():
        setattr(teacher, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Teacher email already exists") from exc
    db.refresh(teacher)
    return teacher


@router.delete("/{teacher_id}", status_code=204)
def delete_teacher(teacher_id: int, db: DatabaseSession, _: AdminUser) -> None:
    teacher = teacher_or_404(teacher_id, db)
    db.delete(teacher)
    db.commit()

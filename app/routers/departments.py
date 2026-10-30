from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.enums import UserRole
from app.models import Course, Department, Teacher, User
from app.schemas import DepartmentCreate, DepartmentRead, DepartmentUpdate
from app.security import AdminUser, CurrentUser

router = APIRouter(prefix="/departments", tags=["departments"])
DatabaseSession = Annotated[Session, Depends(get_db)]


def department_or_404(department_id: int, db: Session) -> Department:
    department = db.get(Department, department_id)
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    return department


@router.post("", response_model=DepartmentRead, status_code=201)
def create_department(
    data: DepartmentCreate, db: DatabaseSession, _: AdminUser
) -> Department:
    department = Department(name=data.name)
    db.add(department)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Department already exists") from exc
    db.refresh(department)
    return department


@router.get("", response_model=list[DepartmentRead])
def list_departments(
    db: DatabaseSession,
    current_user: CurrentUser,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[Department]:
    statement = select(Department)
    if current_user.role == UserRole.HOD:
        if current_user.department_id is None:
            return []
        statement = statement.where(Department.id == current_user.department_id)
    elif current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Department access denied")
    return list(db.scalars(statement.order_by(Department.name).offset(offset).limit(limit)).all())


@router.get("/{department_id}", response_model=DepartmentRead)
def read_department(
    department_id: int, db: DatabaseSession, current_user: CurrentUser
) -> Department:
    department = department_or_404(department_id, db)
    if current_user.role not in (UserRole.ADMIN, UserRole.HOD) or (
        current_user.role == UserRole.HOD
        and current_user.department_id != department.id
    ):
        raise HTTPException(status_code=404, detail="Department not found")
    return department


@router.patch("/{department_id}", response_model=DepartmentRead)
def update_department(
    department_id: int,
    data: DepartmentUpdate,
    db: DatabaseSession,
    _: AdminUser,
) -> Department:
    department = department_or_404(department_id, db)
    if data.name is not None:
        department.name = data.name
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Department already exists") from exc
    db.refresh(department)
    return department


@router.delete("/{department_id}", status_code=204)
def delete_department(
    department_id: int, db: DatabaseSession, _: AdminUser
) -> None:
    department = department_or_404(department_id, db)
    is_referenced = any(
        db.scalar(
            select(model.id)
            .where(model.department_id == department_id)
            .limit(1)
        )
        is not None
        for model in (User, Course, Teacher)
    )
    if is_referenced:
        raise HTTPException(
            status_code=409,
            detail="Department is still assigned to an account, course, or teacher",
        )
    db.delete(department)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Department is still assigned to users, courses, or teachers",
        ) from exc

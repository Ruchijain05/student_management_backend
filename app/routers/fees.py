from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.database import get_db
from app.department_access import department_course_ids, ensure_course_in_department
from app.enums import UserRole
from app.models import Course, Enrollment, FeeAssignment, FeePayment, Student
from app.schemas import (
    FeeAssignmentCreate,
    FeeAssignmentRead,
    FeePaymentCreate,
    FeePaymentRecordResponse,
    FeePaymentRead,
)
from app.security import AdminUser, CurrentUser

router = APIRouter(prefix="/fees", tags=["fees"])
DatabaseSession = Annotated[Session, Depends(get_db)]
ZERO = Decimal("0.00")


def fee_assignment_or_404(fee_id: int, db: Session) -> FeeAssignment:
    assignment = db.scalar(
        select(FeeAssignment)
        .options(
            joinedload(FeeAssignment.student),
            joinedload(FeeAssignment.course),
            selectinload(FeeAssignment.payments),
        )
        .where(FeeAssignment.id == fee_id)
    )
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fee assignment not found",
        )
    return assignment


def fee_read(assignment: FeeAssignment) -> FeeAssignmentRead:
    paid_fee = sum(
        (payment.amount for payment in assignment.payments), start=ZERO
    )
    pending_fee = max(assignment.total_fee - paid_fee, ZERO)
    fee_status = (
        "Paid"
        if pending_fee == ZERO
        else "Partial"
        if paid_fee > ZERO
        else "Pending"
    )
    return FeeAssignmentRead(
        id=assignment.id,
        student_id=assignment.student_id,
        course_id=assignment.course_id,
        student_name=(
            f"{assignment.student.first_name} {assignment.student.last_name}"
        ),
        course_code=assignment.course.code,
        course_title=assignment.course.title,
        total_fee=assignment.total_fee,
        paid_fee=paid_fee,
        pending_fee=pending_fee,
        status=fee_status,
        payments=[
            FeePaymentRead.model_validate(payment)
            for payment in sorted(
                assignment.payments,
                key=lambda item: (item.payment_date, item.id),
                reverse=True,
            )
        ],
    )


def ensure_student_is_enrolled(student_id: int, course_id: int, db: Session) -> None:
    enrollment_id = db.scalar(
        select(Enrollment.id).where(
            Enrollment.student_id == student_id,
            Enrollment.course_id == course_id,
        )
    )
    if enrollment_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Student must be enrolled in the course before fees are assigned",
        )


@router.post(
    "", response_model=FeeAssignmentRead, status_code=status.HTTP_201_CREATED
)
def create_fee_assignment(
    fee_data: FeeAssignmentCreate,
    db: DatabaseSession,
    _: AdminUser,
) -> FeeAssignmentRead:
    if db.get(Student, fee_data.student_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Student not found"
        )
    course = db.get(Course, fee_data.course_id)
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )
    if course.course_fee is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Set this course's fee in Courses before assigning fees",
        )
    ensure_student_is_enrolled(fee_data.student_id, fee_data.course_id, db)
    assignment = FeeAssignment(
        **fee_data.model_dump(), total_fee=course.course_fee
    )
    db.add(assignment)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Fees have already been assigned for this student and course",
        ) from exc
    return fee_read(fee_assignment_or_404(assignment.id, db))


@router.get("", response_model=list[FeeAssignmentRead])
def list_fee_assignments(
    db: DatabaseSession,
    current_user: CurrentUser,
    student_id: Annotated[int | None, Query(gt=0)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[FeeAssignmentRead]:
    if current_user.role == UserRole.TEACHER:
        raise HTTPException(status_code=403, detail="Fee records are not available to teachers")
    statement = select(FeeAssignment).options(
        joinedload(FeeAssignment.student),
        joinedload(FeeAssignment.course),
        selectinload(FeeAssignment.payments),
    )
    if current_user.role == UserRole.STUDENT:
        if current_user.student_id is None:
            return []
        statement = statement.where(
            FeeAssignment.student_id == current_user.student_id
        )
    elif current_user.role == UserRole.HOD:
        statement = statement.where(
            FeeAssignment.course_id.in_(department_course_ids(current_user))
        )
    elif student_id is not None:
        statement = statement.where(FeeAssignment.student_id == student_id)
    statement = (
        statement.order_by(FeeAssignment.student_id, FeeAssignment.course_id)
        .offset(offset)
        .limit(limit)
    )
    return [fee_read(item) for item in db.scalars(statement).unique().all()]


@router.get("/{fee_id}", response_model=FeeAssignmentRead)
def read_fee_assignment(
    fee_id: int, db: DatabaseSession, current_user: CurrentUser
) -> FeeAssignmentRead:
    if current_user.role == UserRole.TEACHER:
        raise HTTPException(status_code=403, detail="Fee records are not available to teachers")
    assignment = fee_assignment_or_404(fee_id, db)
    if (
        current_user.role == UserRole.STUDENT
        and current_user.student_id != assignment.student_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fee assignment not found",
        )
    if current_user.role == UserRole.HOD:
        ensure_course_in_department(assignment.course_id, current_user, db)
    return fee_read(assignment)


@router.post(
    "/{fee_id}/payments",
    response_model=FeePaymentRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_fee_payment(
    fee_id: int,
    payment_data: FeePaymentCreate,
    db: DatabaseSession,
    _: AdminUser,
    response: Response,
) -> FeePaymentRecordResponse:
    assignment = fee_assignment_or_404(fee_id, db)
    idempotency_key = str(payment_data.idempotency_key)
    existing_payment = db.scalar(
        select(FeePayment).where(FeePayment.idempotency_key == idempotency_key)
    )
    if existing_payment is not None:
        response.status_code = status.HTTP_200_OK
        return payment_idempotency_response(
            existing_payment, fee_id, payment_data
        )

    paid_fee = sum((payment.amount for payment in assignment.payments), start=ZERO)
    if payment_data.amount > assignment.total_fee - paid_fee:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Payment cannot exceed the pending fee balance",
        )
    payment = FeePayment(
        fee_assignment_id=fee_id,
        **payment_data.model_dump(exclude={"idempotency_key"}),
        idempotency_key=idempotency_key,
    )
    db.add(payment)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing_payment = db.scalar(
            select(FeePayment).where(
                FeePayment.idempotency_key == idempotency_key
            )
        )
        if existing_payment is not None:
            response.status_code = status.HTTP_200_OK
            return payment_idempotency_response(
                existing_payment, fee_id, payment_data
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment could not be recorded because a conflicting record exists",
        ) from exc
    db.refresh(payment)
    return FeePaymentRecordResponse.model_validate(payment)


def payment_idempotency_response(
    payment: FeePayment,
    fee_id: int,
    payment_data: FeePaymentCreate,
) -> FeePaymentRecordResponse:
    if (
        payment.fee_assignment_id != fee_id
        or payment.amount != payment_data.amount
        or payment.payment_date != payment_data.payment_date
        or payment.payment_method != payment_data.payment_method
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This idempotency key was already used for a different payment",
        )
    return FeePaymentRecordResponse.model_validate(payment).model_copy(
        update={"replayed": True}
    )

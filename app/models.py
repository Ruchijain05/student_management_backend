from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Numeric,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import AttendanceStatus, SportsLevel, UserRole


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )

    enrollments: Mapped[list["Enrollment"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    attendance_records: Mapped[list["Attendance"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    marks: Mapped[list["Mark"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    sports_achievements: Mapped[list["SportsAchievement"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    user: Mapped["User | None"] = relationship(
        back_populates="student", cascade="all, delete-orphan", uselist=False
    )
    fee_assignments: Mapped[list["FeeAssignment"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    course_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    enrollments: Mapped[list["Enrollment"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    attendance_records: Mapped[list["Attendance"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    marks: Mapped[list["Mark"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    timetable_entries: Mapped[list["CourseTimetableEntry"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    fee_assignments: Mapped[list["FeeAssignment"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="uq_student_course"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )

    student: Mapped[Student] = relationship(back_populates="enrollments")
    course: Mapped[Course] = relationship(back_populates="enrollments")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SqlEnum(
            UserRole,
            native_enum=False,
            length=10,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        default=UserRole.STUDENT,
        nullable=False,
    )
    token_version: Mapped[int] = mapped_column(
        default=0, server_default="0", nullable=False
    )
    password_reset_requested_at: Mapped[datetime | None] = mapped_column(DateTime)
    student_id: Mapped[int | None] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )

    student: Mapped[Student | None] = relationship(back_populates="user")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(
        default=0, server_default="0", nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "course_id",
            "attendance_date",
            name="uq_attendance_student_course_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[AttendanceStatus] = mapped_column(
        SqlEnum(
            AttendanceStatus,
            native_enum=False,
            length=10,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )

    student: Mapped[Student] = relationship(back_populates="attendance_records")
    course: Mapped[Course] = relationship(back_populates="attendance_records")


class Mark(Base):
    __tablename__ = "marks"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "course_id",
            "assessment_name",
            name="uq_mark_student_course_assessment",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    assessment_name: Mapped[str] = mapped_column(String(100), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    max_score: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )

    student: Mapped[Student] = relationship(back_populates="marks")
    course: Mapped[Course] = relationship(back_populates="marks")


class SportsAchievement(Base):
    __tablename__ = "sports_achievements"

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sport_name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[SportsLevel] = mapped_column(
        SqlEnum(
            SportsLevel,
            native_enum=False,
            length=10,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    event_name: Mapped[str | None] = mapped_column(String(100))
    competition_name: Mapped[str | None] = mapped_column(String(150))
    achievement_date: Mapped[date] = mapped_column(Date, nullable=False)
    result: Mapped[str | None] = mapped_column(String(100))

    student: Mapped[Student] = relationship(back_populates="sports_achievements")


class Notice(Base):
    __tablename__ = "notices"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    notice_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)


class CourseTimetableEntry(Base):
    __tablename__ = "course_timetable_entries"
    __table_args__ = (
        CheckConstraint(
            "weekday IN ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday')",
            name="ck_course_timetable_weekday",
        ),
        CheckConstraint(
            "end_time > start_time", name="ck_course_timetable_time_range"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    weekday: Mapped[str] = mapped_column(String(9), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    classroom_number: Mapped[str] = mapped_column(String(50), nullable=False)

    course: Mapped[Course] = relationship(back_populates="timetable_entries")


class FeeAssignment(Base):
    __tablename__ = "fee_assignments"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "course_id", name="uq_fee_assignment_student_course"
        ),
        CheckConstraint("total_fee > 0", name="ck_fee_assignment_total_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    total_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    student: Mapped[Student] = relationship(back_populates="fee_assignments")
    course: Mapped[Course] = relationship(back_populates="fee_assignments")
    payments: Mapped[list["FeePayment"]] = relationship(
        back_populates="fee_assignment", cascade="all, delete-orphan"
    )


class FeePayment(Base):
    __tablename__ = "fee_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_fee_payment_amount_positive"),
        CheckConstraint(
            "payment_method IN ('cash', 'card', 'upi', 'bank_transfer')",
            name="ck_fee_payment_method",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fee_assignment_id: Mapped[int] = mapped_column(
        ForeignKey("fee_assignments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)

    fee_assignment: Mapped[FeeAssignment] = relationship(
        back_populates="payments"
    )

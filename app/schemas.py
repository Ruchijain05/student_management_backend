from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AliasPath,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    model_validator,
)

from app.enums import AttendanceStatus, SportsLevel, UserRole

StudentName = Annotated[
    str, StringConstraints(min_length=1, max_length=100, strip_whitespace=True)
]
CourseCode = Annotated[
    str, StringConstraints(min_length=1, max_length=20, strip_whitespace=True)
]
CourseTitle = Annotated[
    str, StringConstraints(min_length=1, max_length=150, strip_whitespace=True)
]
AssessmentName = Annotated[
    str, StringConstraints(min_length=1, max_length=100, strip_whitespace=True)
]
NumericPassword = Annotated[
    str, StringConstraints(min_length=6, max_length=8, pattern=r"^[0-9]{6,8}$")
]


class StudentCreate(BaseModel):
    first_name: StudentName
    last_name: StudentName
    email: EmailStr


class StudentUpdate(BaseModel):
    first_name: StudentName | None = None
    last_name: StudentName | None = None
    email: EmailStr | None = None


class StudentRead(StudentCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CourseCreate(BaseModel):
    code: CourseCode
    title: CourseTitle
    description: str | None = Field(default=None, max_length=500)
    course_fee: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    department_id: int | None = Field(default=None, gt=0)


class CourseUpdate(BaseModel):
    code: CourseCode | None = None
    title: CourseTitle | None = None
    description: str | None = Field(default=None, max_length=500)
    course_fee: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    department_id: int | None = Field(default=None, gt=0)


class CourseRead(CourseCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class EnrollmentCreate(BaseModel):
    student_id: int = Field(gt=0)
    course_id: int = Field(gt=0)


class EnrollmentUpdate(BaseModel):
    student_id: int | None = Field(default=None, gt=0)
    course_id: int | None = Field(default=None, gt=0)


class EnrollmentRead(EnrollmentCreate):
    id: int
    enrolled_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RegisterRequest(StudentCreate):
    password: NumericPassword

    model_config = ConfigDict(extra="forbid")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserRead(BaseModel):
    id: int
    email: EmailStr
    role: UserRole
    student_id: int | None
    department_id: int | None = None
    teacher_id: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class OAuth2TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordResetRequest(BaseModel):
    email: EmailStr

    model_config = ConfigDict(extra="forbid")


class PasswordResetConfirm(BaseModel):
    email: EmailStr
    otp: Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]
    new_password: NumericPassword

    model_config = ConfigDict(extra="forbid")


class AttendanceCreate(BaseModel):
    student_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    attendance_date: date
    status: AttendanceStatus


class AttendanceUpdate(BaseModel):
    status: AttendanceStatus


class AttendanceRead(AttendanceCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class MarkCreate(BaseModel):
    student_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    assessment_name: AssessmentName
    score: Decimal = Field(ge=0, max_digits=7, decimal_places=2)
    max_score: Decimal = Field(gt=0, max_digits=7, decimal_places=2)

    @model_validator(mode="after")
    def score_does_not_exceed_maximum(self) -> "MarkCreate":
        if self.score > self.max_score:
            raise ValueError("score cannot be greater than max_score")
        return self


class MarkUpdate(BaseModel):
    assessment_name: AssessmentName | None = None
    score: Decimal | None = Field(
        default=None, ge=0, max_digits=7, decimal_places=2
    )
    max_score: Decimal | None = Field(
        default=None, gt=0, max_digits=7, decimal_places=2
    )


class MarkRead(MarkCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


SportName = Annotated[
    str, StringConstraints(min_length=1, max_length=100, strip_whitespace=True)
]
EventName = Annotated[
    str, StringConstraints(min_length=1, max_length=100, strip_whitespace=True)
]
CompetitionName = Annotated[
    str, StringConstraints(min_length=1, max_length=150, strip_whitespace=True)
]
AchievementResult = Annotated[
    str, StringConstraints(min_length=1, max_length=100, strip_whitespace=True)
]
NoticeTitle = Annotated[
    str, StringConstraints(min_length=1, max_length=150, strip_whitespace=True)
]
NoticeDescription = Annotated[
    str, StringConstraints(min_length=1, max_length=2000, strip_whitespace=True)
]
TimetableWeekday = Literal[
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"
]
ClassroomNumber = Annotated[
    str, StringConstraints(min_length=1, max_length=50, strip_whitespace=True)
]
PaymentMethod = Literal["cash", "card", "upi", "bank_transfer"]


class FeeAssignmentCreate(BaseModel):
    student_id: int = Field(gt=0)
    course_id: int = Field(gt=0)

    model_config = ConfigDict(extra="forbid")


class FeePaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    payment_date: date
    payment_method: PaymentMethod
    idempotency_key: UUID


class FeePaymentRead(BaseModel):
    id: int
    amount: Decimal
    payment_date: date
    payment_method: PaymentMethod
    idempotency_key: UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class FeePaymentRecordResponse(FeePaymentRead):
    replayed: bool = False


class FeeAssignmentRead(BaseModel):
    id: int
    student_id: int
    course_id: int
    student_name: str
    course_code: str
    course_title: str
    total_fee: Decimal
    paid_fee: Decimal
    pending_fee: Decimal
    status: Literal["Paid", "Partial", "Pending"]
    payments: list[FeePaymentRead]


class TimetableEntryCreate(BaseModel):
    course_id: int = Field(gt=0)
    weekday: TimetableWeekday
    start_time: time
    end_time: time
    classroom_number: ClassroomNumber

    @model_validator(mode="after")
    def end_time_after_start_time(self) -> "TimetableEntryCreate":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be later than start_time")
        return self


class TimetableEntryUpdate(BaseModel):
    course_id: int | None = Field(default=None, gt=0)
    weekday: TimetableWeekday | None = None
    start_time: time | None = None
    end_time: time | None = None
    classroom_number: ClassroomNumber | None = None

    @model_validator(mode="after")
    def end_time_after_start_time(self) -> "TimetableEntryUpdate":
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise ValueError("end_time must be later than start_time")
        return self


class TimetableEntryRead(TimetableEntryCreate):
    id: int
    course_code: str = Field(validation_alias=AliasPath("course", "code"))
    course_title: str = Field(validation_alias=AliasPath("course", "title"))

    model_config = ConfigDict(from_attributes=True)


class NoticeCreate(BaseModel):
    title: NoticeTitle
    description: NoticeDescription
    notice_date: date


class NoticeUpdate(BaseModel):
    title: NoticeTitle | None = None
    description: NoticeDescription | None = None
    notice_date: date | None = None


class NoticeRead(NoticeCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class SportsAchievementCreate(BaseModel):
    student_id: int = Field(gt=0)
    sport_name: SportName
    level: SportsLevel
    event_name: EventName | None = None
    competition_name: CompetitionName | None = None
    achievement_date: date
    result: AchievementResult | None = None


class SportsAchievementUpdate(BaseModel):
    sport_name: SportName | None = None
    level: SportsLevel | None = None
    event_name: EventName | None = None
    competition_name: CompetitionName | None = None
    achievement_date: date | None = None
    result: AchievementResult | None = None


class SportsAchievementRead(SportsAchievementCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class SportsSportSummary(BaseModel):
    sport_name: str
    athlete_count: int
    achievement_count: int


class SportsRecentAchievement(BaseModel):
    id: int
    student_id: int
    student_name: str
    sport_name: str
    level: SportsLevel
    event_name: str | None
    competition_name: str | None
    achievement_date: date
    result: str | None


class SportsDashboard(BaseModel):
    total_athletes: int
    total_achievements: int
    district_athletes: int
    state_athletes: int
    national_athletes: int
    district_achievements: int
    state_achievements: int
    national_achievements: int
    sport_breakdown: list[SportsSportSummary]
    recent_achievements: list[SportsRecentAchievement]


class CourseResult(BaseModel):
    student_id: int
    course_id: int
    course_code: str
    course_title: str
    assessment_count: int
    average_percentage: float
    grade: str


class AdminDashboard(BaseModel):
    total_students: int
    total_courses: int
    total_enrollments: int
    attendance_records_today: int
    total_assessments: int


class PrincipalDashboard(BaseModel):
    total_students: int
    total_courses: int
    total_attendance: int
    total_marks: int
    total_results: int


class DepartmentCreate(BaseModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=150, strip_whitespace=True)]


class DepartmentUpdate(BaseModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=150, strip_whitespace=True)] | None = None


class DepartmentRead(DepartmentCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class TeacherCreate(BaseModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)]
    email: EmailStr
    department_id: int = Field(gt=0)


class TeacherUpdate(BaseModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)] | None = None
    email: EmailStr | None = None
    department_id: int | None = Field(default=None, gt=0)


class TeacherRead(TeacherCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class TeacherCourseCreate(BaseModel):
    course_id: int = Field(gt=0)


class TeacherCourseRead(BaseModel):
    id: int
    teacher_id: int
    course_id: int

    model_config = ConfigDict(from_attributes=True)


class HODDashboard(BaseModel):
    department_id: int
    department_name: str
    total_students: int
    total_courses: int
    total_teachers: int
    total_enrollments: int
    total_attendance: int
    total_marks: int
    total_results: int


class TeacherDashboard(BaseModel):
    total_courses: int
    total_students: int
    total_enrollments: int
    total_attendance: int
    total_marks: int
    total_results: int


class StudentDashboard(BaseModel):
    student_id: int
    enrolled_courses: int
    attendance_records: int
    attendance_percentage: float
    assessments_recorded: int
    average_percentage: float | None

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    model_validator,
)

from app.enums import AttendanceStatus, UserRole

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


class CourseUpdate(BaseModel):
    code: CourseCode | None = None
    title: CourseTitle | None = None
    description: str | None = Field(default=None, max_length=500)


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


class StudentDashboard(BaseModel):
    student_id: int
    enrolled_courses: int
    attendance_records: int
    attendance_percentage: float
    assessments_recorded: int
    average_percentage: float | None

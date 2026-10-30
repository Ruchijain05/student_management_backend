from collections.abc import Generator
from datetime import date, timedelta
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.enums import UserRole
from app.main import app
from app.models import Course, FeeAssignment, Student, TeacherCourse, User
from app.security import hash_password


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    monkeypatch.setattr("app.security.settings.secret_key", "t" * 48)

    def override_get_db() -> Generator[Session, None, None]:
        with TestingSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestingSession() as session:
        session.add(
            User(
                email="admin@example.com",
                password_hash=hash_password("correct-horse-battery"),
                role=UserRole.ADMIN,
            )
        )
        session.add(
            User(
                email="principal@example.com",
                password_hash=hash_password("principal-password"),
                role=UserRole.PRINCIPAL,
            )
        )
        session.commit()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_teacher_course_assignments_use_association_table() -> None:
    assert "teacher_id" not in Course.__table__.columns
    assert {"teacher_id", "course_id"} <= set(TeacherCourse.__table__.columns.keys())
    assert Course.teacher_assignments.property.mapper.class_ is TeacherCourse


def add_hod_account(
    email: str, password: str, department_id: int | None
) -> None:
    database = app.dependency_overrides[get_db]()
    session = next(database)
    try:
        session.add(
            User(
                email=email,
                password_hash=hash_password(password),
                role=UserRole.HOD,
                department_id=department_id,
            )
        )
        session.commit()
    finally:
        database.close()


def add_teacher_account(email: str, password: str, teacher_id: int) -> None:
    database = app.dependency_overrides[get_db]()
    session = next(database)
    try:
        session.add(
            User(
                email=email,
                password_hash=hash_password(password),
                role=UserRole.TEACHER,
                teacher_id=teacher_id,
            )
        )
        session.commit()
    finally:
        database.close()


def test_swagger_oauth_login_and_authorized_openapi(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()
    scheme = openapi["components"]["securitySchemes"]["OAuth2PasswordBearer"]
    assert scheme["flows"]["password"]["tokenUrl"] == "/api/v1/auth/token"
    assert openapi["paths"]["/api/v1/auth/me"]["get"]["security"] == [
        {"OAuth2PasswordBearer": []}
    ]

    response = client.post(
        "/api/v1/auth/token",
        data={
            "username": "admin@example.com",
            "password": "correct-horse-battery",
        },
    )
    assert response.status_code == 200
    token_response = response.json()
    assert set(token_response) == {"access_token", "token_type"}
    assert token_response["token_type"] == "bearer"
    token = token_response["access_token"]
    current_user = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert current_user.status_code == 200
    assert current_user.json()["role"] == "admin"


def test_password_reset_is_generic_single_use_and_revokes_jwts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("app.config.settings.app_env", "development")
    monkeypatch.setattr(
        "app.config.settings.password_reset_otp_console_enabled", True
    )
    previous_headers = login(
        client, "admin@example.com", "correct-horse-battery"
    )

    unknown = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "unknown@example.com"},
    )
    unknown_output = capsys.readouterr().out
    known = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "admin@example.com"},
    )
    known_output = capsys.readouterr().out
    assert unknown.status_code == known.status_code == 200
    assert unknown.json() == known.json()
    assert unknown_output == ""
    match = re.search(r"Local password reset OTP for admin@example\.com: (\d{6})", known_output)
    assert match is not None
    otp = match.group(1)
    assert otp not in known.text

    repeated = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "admin@example.com"},
    )
    repeated_output = capsys.readouterr().out
    assert repeated.json() == known.json()
    repeated_match = re.search(
        r"Local password reset OTP for admin@example\.com: (\d{6})",
        repeated_output,
    )
    assert repeated_match is not None
    assert repeated_match.group(1) not in repeated.text

    reset = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "email": "admin@example.com",
            "otp": repeated_match.group(1),
            "new_password": "654321",
        },
    )
    assert reset.status_code == 200
    assert client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "email": "admin@example.com",
            "otp": otp,
            "new_password": "123456",
        },
    ).status_code == 400
    assert client.get("/api/v1/auth/me", headers=previous_headers).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@example.com",
            "password": "correct-horse-battery",
        },
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@example.com",
            "password": "654321",
        },
    ).status_code == 200


def test_password_reset_validates_email_otp_and_password(
    client: TestClient,
) -> None:
    assert client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "not-an-email"},
    ).status_code == 422
    assert client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "email": "admin@example.com",
            "otp": "abc123",
            "new_password": "123456",
        },
    ).status_code == 422
    assert client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "email": "admin@example.com",
            "otp": "12345",
            "new_password": "123456",
        },
    ).status_code == 422
    for password in ("12345", "123456789", "1234a6", "１２３４５６"):
        assert client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "email": "admin@example.com",
                "otp": "123456",
                "new_password": password,
            },
        ).status_code == 422


def test_password_reset_otp_expires(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("app.config.settings.app_env", "development")
    monkeypatch.setattr(
        "app.config.settings.password_reset_otp_console_enabled", True
    )
    monkeypatch.setattr(
        "app.routers.auth.PASSWORD_RESET_OTP_TTL", timedelta(seconds=-1)
    )
    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "admin@example.com"},
    )
    match = re.search(
        r"Local password reset OTP for admin@example\.com: (\d{6})",
        capsys.readouterr().out,
    )
    assert response.status_code == 200
    assert match is not None
    assert client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "email": "admin@example.com",
            "otp": match.group(1),
            "new_password": "654321",
        },
    ).status_code == 400


def test_password_reset_otp_has_limited_verification_attempts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("app.config.settings.app_env", "development")
    monkeypatch.setattr(
        "app.config.settings.password_reset_otp_console_enabled", True
    )
    request = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "admin@example.com"},
    )
    match = re.search(
        r"Local password reset OTP for admin@example\.com: (\d{6})",
        capsys.readouterr().out,
    )
    assert request.status_code == 200
    assert match is not None
    otp = match.group(1)

    for _ in range(5):
        assert client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "email": "admin@example.com",
                "otp": "000000" if otp != "000000" else "000001",
                "new_password": "654321",
            },
        ).status_code == 400
    assert client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "email": "admin@example.com",
            "otp": otp,
            "new_password": "654321",
        },
    ).status_code == 400


def test_password_reset_otp_hash_is_scoped_to_user(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("app.config.settings.app_env", "development")
    monkeypatch.setattr(
        "app.config.settings.password_reset_otp_console_enabled", True
    )
    monkeypatch.setattr("app.routers.auth.secrets.randbelow", lambda _: 123456)
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Second",
            "last_name": "Student",
            "email": "second@example.com",
            "password": "123456",
        },
    )
    assert registration.status_code == 201

    first = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "admin@example.com"},
    )
    second = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "second@example.com"},
    )
    assert first.status_code == second.status_code == 200
    capsys.readouterr()

    for email in ("admin@example.com", "second@example.com"):
        response = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={
                "email": email,
                "otp": "123456",
                "new_password": "654321",
            },
        )
        assert response.status_code == 200


def test_password_reset_otp_is_not_printed_outside_development(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("app.config.settings.app_env", "production")
    monkeypatch.setattr(
        "app.config.settings.password_reset_otp_console_enabled", True
    )
    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "admin@example.com"},
    )
    assert response.status_code == 200
    assert capsys.readouterr().out == ""


def test_registration_requires_six_to_eight_ascii_digits(
    client: TestClient,
) -> None:
    payload = {
        "first_name": "Test",
        "last_name": "User",
        "email": "numeric@example.com",
    }
    for password in ("12345", "123456789", "12a456", "１２３４５６"):
        assert client.post(
            "/api/v1/auth/register",
            json={**payload, "password": password},
        ).status_code == 422

    registration = client.post(
        "/api/v1/auth/register",
        json={**payload, "password": "123456"},
    )
    assert registration.status_code == 201
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "numeric@example.com", "password": "123456"},
    ).status_code == 200


def test_roles_search_attendance_marks_results_and_dashboards(
    client: TestClient,
) -> None:
    assert client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Unauthorised",
            "last_name": "Principal",
            "email": "untrusted.principal@example.com",
            "password": "246810",
            "role": "principal",
        },
    ).status_code == 422
    signup = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "password": "246810",
        },
    )
    assert signup.status_code == 201
    student_headers = {
        "Authorization": f"Bearer {signup.json()['access_token']}"
    }
    student_id = signup.json()["user"]["student_id"]

    assert client.post(
        "/api/v1/courses",
        json={"code": "CS101", "title": "Computer Science"},
        headers=student_headers,
    ).status_code == 403
    assert client.get("/api/v1/students", headers=student_headers).json()[0][
        "id"
    ] == student_id

    admin_headers = login(
        client, "admin@example.com", "correct-horse-battery"
    )
    assert client.patch(
        f"/api/v1/students/{student_id}",
        json={"email": "ada.updated@example.com"},
        headers=admin_headers,
    ).status_code == 200
    assert client.post(
        "/api/v1/auth/login",
        json={
            "email": "ada.updated@example.com",
            "password": "246810",
        },
    ).status_code == 200
    assert client.post(
        "/api/v1/auth/login",
        json={
            "email": "ada@example.com",
            "password": "246810",
        },
    ).status_code == 401
    other_student = client.post(
        "/api/v1/students",
        json={
            "first_name": "Grace",
            "last_name": "Hopper",
            "email": "grace@example.com",
        },
        headers=admin_headers,
    ).json()
    assert client.get(
        f"/api/v1/students/{other_student['id']}", headers=student_headers
    ).status_code == 403
    course_response = client.post(
        "/api/v1/courses",
        json={"code": "CS101", "title": "Computer Science"},
        headers=admin_headers,
    )
    assert course_response.status_code == 201
    course_id = course_response.json()["id"]
    assert client.get(
        "/api/v1/courses?q=computer", headers=student_headers
    ).json()[0]["id"] == course_id

    enrollment = client.post(
        "/api/v1/enrollments",
        json={"student_id": student_id, "course_id": course_id},
        headers=admin_headers,
    )
    assert enrollment.status_code == 201
    assert len(client.get("/api/v1/enrollments", headers=student_headers).json()) == 1

    attendance_payload = {
        "student_id": student_id,
        "course_id": course_id,
        "attendance_date": str(date.today()),
        "status": "present",
    }
    attendance = client.post(
        "/api/v1/attendance", json=attendance_payload, headers=admin_headers
    )
    assert attendance.status_code == 201
    assert client.post(
        "/api/v1/attendance",
        json=attendance_payload,
        headers=admin_headers,
    ).status_code == 409
    assert len(client.get("/api/v1/attendance", headers=student_headers).json()) == 1
    attendance_id = attendance.json()["id"]
    assert client.patch(
        f"/api/v1/attendance/{attendance_id}",
        json={"status": "late"},
        headers=admin_headers,
    ).json()["status"] == "late"

    mark_payload = {
        "student_id": student_id,
        "course_id": course_id,
        "assessment_name": "Final",
        "score": "92",
        "max_score": "100",
    }
    mark = client.post("/api/v1/marks", json=mark_payload, headers=admin_headers)
    assert mark.status_code == 201
    mark_id = mark.json()["id"]
    assert client.patch(
        f"/api/v1/marks/{mark_id}",
        json={"score": "92"},
        headers=admin_headers,
    ).status_code == 200
    assert client.post(
        "/api/v1/marks",
        json={**mark_payload, "assessment_name": "Invalid", "score": "101"},
        headers=admin_headers,
    ).status_code == 422

    results = client.get("/api/v1/results", headers=student_headers)
    assert results.status_code == 200
    assert results.json()[0]["grade"] == "A"
    assert results.json()[0]["average_percentage"] == 92
    dashboard = client.get("/api/v1/dashboard/student", headers=student_headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["attendance_percentage"] == 100
    assert client.get(
        "/api/v1/dashboard/principal", headers=student_headers
    ).status_code == 403
    assert client.get(
        "/api/v1/dashboard/admin", headers=student_headers
    ).status_code == 403
    assert client.get(
        "/api/v1/dashboard/admin", headers=admin_headers
    ).json()["total_students"] == 2
    principal_headers = login(
        client, "principal@example.com", "principal-password"
    )
    principal_user = client.get(
        "/api/v1/auth/me", headers=principal_headers
    )
    assert principal_user.status_code == 200
    assert principal_user.json()["role"] == "principal"
    principal_summary = client.get(
        "/api/v1/dashboard/principal", headers=principal_headers
    )
    assert principal_summary.status_code == 200
    assert principal_summary.json() == {
        "total_students": 2,
        "total_courses": 1,
        "total_attendance": 1,
        "total_marks": 1,
        "total_results": 1,
    }
    assert client.get(
        "/api/v1/dashboard/admin", headers=principal_headers
    ).status_code == 403
    assert client.get(
        "/api/v1/dashboard/principal", headers=admin_headers
    ).status_code == 403
    assert client.get(
        "/api/v1/students", headers=principal_headers
    ).status_code == 200
    assert client.get(
        "/api/v1/results", headers=principal_headers
    ).status_code == 200
    assert client.get(
        "/api/v1/enrollments", headers=principal_headers
    ).json()[0]["student_id"] == student_id
    assert client.get(
        "/api/v1/attendance", headers=principal_headers
    ).json()[0]["student_id"] == student_id
    assert client.get(
        "/api/v1/marks", headers=principal_headers
    ).json()[0]["student_id"] == student_id
    assert client.get(
        "/api/v1/fees", headers=principal_headers
    ).status_code == 200
    assert client.get(
        f"/api/v1/students/{student_id}", headers=principal_headers
    ).json()["email"] == "ada.updated@example.com"
    assert client.get(
        f"/api/v1/courses/{course_id}", headers=principal_headers
    ).json()["code"] == "CS101"
    assert client.post(
        "/api/v1/students",
        json={
            "first_name": "Principal",
            "last_name": "Cannot Create",
            "email": "blocked@example.com",
        },
        headers=principal_headers,
    ).status_code == 403
    assert client.post(
        "/api/v1/courses",
        json={"code": "CS102", "title": "Data Structures"},
        headers=principal_headers,
    ).status_code == 403
    assert client.post(
        "/api/v1/enrollments",
        json={"student_id": student_id, "course_id": course_id},
        headers=principal_headers,
    ).status_code == 403
    assert client.post(
        "/api/v1/marks",
        json={**mark_payload, "assessment_name": "Second"},
        headers=principal_headers,
    ).status_code == 403
    assert client.post(
        "/api/v1/fees",
        json={"student_id": student_id, "course_id": course_id},
        headers=principal_headers,
    ).status_code == 403
    assert client.patch(
        f"/api/v1/attendance/{attendance_id}",
        json={"status": "late"},
        headers=principal_headers,
    ).status_code == 403
    assert client.delete(
        f"/api/v1/marks/{mark_id}", headers=principal_headers
    ).status_code == 403
    assert client.delete(
        f"/api/v1/attendance/{attendance_id}", headers=admin_headers
    ).status_code == 204
    assert client.delete(
        f"/api/v1/marks/{mark_id}", headers=admin_headers
    ).status_code == 204


def test_resource_crud_and_missing_auth(client: TestClient) -> None:
    assert client.get("/api/v1/courses").status_code == 401
    headers = login(client, "admin@example.com", "correct-horse-battery")

    student = client.post(
        "/api/v1/students",
        json={
            "first_name": "Grace",
            "last_name": "Hopper",
            "email": "grace@example.com",
        },
        headers=headers,
    )
    assert student.status_code == 201
    student_id = student.json()["id"]
    assert client.patch(
        f"/api/v1/students/{student_id}",
        json={"last_name": "Murray Hopper"},
        headers=headers,
    ).json()["last_name"] == "Murray Hopper"
    assert client.get(
        "/api/v1/students?q=Murray", headers=headers
    ).json()[0]["id"] == student_id

    course = client.post(
        "/api/v1/courses",
        json={"code": "MATH1", "title": "Mathematics"},
        headers=headers,
    )
    course_id = course.json()["id"]
    enrollment = client.post(
        "/api/v1/enrollments",
        json={"student_id": student_id, "course_id": course_id},
        headers=headers,
    )
    enrollment_id = enrollment.json()["id"]
    assert client.patch(
        f"/api/v1/enrollments/{enrollment_id}",
        json={"course_id": course_id},
        headers=headers,
    ).status_code == 200
    assert client.delete(
        f"/api/v1/enrollments/{enrollment_id}", headers=headers
    ).status_code == 204
    assert client.patch(
        f"/api/v1/courses/{course_id}",
        json={"title": "Applied Mathematics"},
        headers=headers,
    ).json()["title"] == "Applied Mathematics"
    assert client.delete(
        f"/api/v1/courses/{course_id}", headers=headers
    ).status_code == 204
    assert client.delete(
        f"/api/v1/students/{student_id}", headers=headers
    ).status_code == 204


def test_course_fee_can_be_created_read_and_updated(client: TestClient) -> None:
    admin_headers = login(client, "admin@example.com", "correct-horse-battery")
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Fee",
            "last_name": "Student",
            "email": "course-fee-student@example.com",
            "password": "246810",
        },
    )
    assert registration.status_code == 201
    student_headers = login(
        client, "course-fee-student@example.com", "246810"
    )
    created = client.post(
        "/api/v1/courses",
        json={
            "code": "FEE101",
            "title": "Course with fee",
            "course_fee": "12500.00",
        },
        headers=admin_headers,
    )

    assert created.status_code == 201
    course_id = created.json()["id"]
    assert created.json()["course_fee"] == "12500.00"
    assert client.get(
        f"/api/v1/courses/{course_id}", headers=student_headers
    ).json()["course_fee"] == "12500.00"
    assert client.get("/api/v1/courses", headers=student_headers).json()[0][
        "course_fee"
    ] == "12500.00"

    updated = client.patch(
        f"/api/v1/courses/{course_id}",
        json={"course_fee": "15000.50"},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["course_fee"] == "15000.50"
    assert client.patch(
        f"/api/v1/courses/{course_id}",
        json={"course_fee": "0"},
        headers=admin_headers,
    ).status_code == 422
    assert client.patch(
        f"/api/v1/courses/{course_id}",
        json={"course_fee": "16000.123"},
        headers=admin_headers,
    ).status_code == 422
    assert client.patch(
        f"/api/v1/courses/{course_id}",
        json={"course_fee": "17000"},
        headers=student_headers,
    ).status_code == 403


def test_student_update_rejects_null_required_fields(client: TestClient) -> None:
    headers = login(client, "admin@example.com", "correct-horse-battery")
    student = client.post(
        "/api/v1/students",
        json={
            "first_name": "Test",
            "last_name": "Student",
            "email": "patch@example.com",
        },
        headers=headers,
    )
    assert student.status_code == 201
    student_id = student.json()["id"]

    for field in ("first_name", "last_name", "email"):
        response = client.patch(
            f"/api/v1/students/{student_id}",
            json={field: None},
            headers=headers,
        )
        assert response.status_code == 422

    unchanged = client.get(
        f"/api/v1/students/{student_id}", headers=headers
    )
    assert unchanged.json()["first_name"] == "Test"
    assert unchanged.json()["last_name"] == "Student"
    assert unchanged.json()["email"] == "patch@example.com"


def test_sports_achievements_access_and_dashboard(client: TestClient) -> None:
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Mira",
            "last_name": "Athlete",
            "email": "mira@example.com",
            "password": "246810",
        },
    )
    assert registration.status_code == 201
    student_headers = login(client, "mira@example.com", "246810")
    student_id = registration.json()["user"]["student_id"]
    admin_headers = login(client, "admin@example.com", "correct-horse-battery")
    other_student = client.post(
        "/api/v1/students",
        json={
            "first_name": "Asha",
            "last_name": "Runner",
            "email": "asha@example.com",
        },
        headers=admin_headers,
    )
    assert other_student.status_code == 201
    other_student_id = other_student.json()["id"]

    def create_achievement(
        linked_student_id: int, sport_name: str, level: str, result: str
    ) -> dict:
        response = client.post(
            "/api/v1/sports",
            json={
                "student_id": linked_student_id,
                "sport_name": sport_name,
                "level": level,
                "event_name": "100m",
                "competition_name": "Annual Meet",
                "achievement_date": str(date.today()),
                "result": result,
            },
            headers=admin_headers,
        )
        assert response.status_code == 201
        return response.json()

    state_achievement = create_achievement(
        student_id, "Athletics", "state", "Silver Medal"
    )
    assert state_achievement["result"] == "Silver Medal"
    create_achievement(student_id, "Athletics", "national", "Finalist")
    other_achievement = create_achievement(
        other_student_id, "Swimming", "district", "Gold"
    )

    assert client.post(
        "/api/v1/sports",
        json={
            "student_id": student_id,
            "sport_name": "Tennis",
            "level": "national",
            "achievement_date": str(date.today()),
        },
        headers=student_headers,
    ).status_code == 403
    assert client.get("/api/v1/sports").status_code == 401
    student_records = client.get(
        f"/api/v1/sports?student_id={other_student_id}",
        headers=student_headers,
    )
    assert student_records.status_code == 200
    assert len(student_records.json()) == 2
    assert {record["student_id"] for record in student_records.json()} == {
        student_id
    }
    assert client.get(
        f"/api/v1/sports/{other_achievement['id']}", headers=student_headers
    ).status_code == 403
    assert client.get(
        "/api/v1/sports?level=state&sport_name=athletics",
        headers=admin_headers,
    ).json()[0]["id"] == state_achievement["id"]

    dashboard = client.get(
        "/api/v1/dashboard/sports", headers=admin_headers
    )
    assert dashboard.status_code == 200
    data = dashboard.json()
    assert data["total_athletes"] == 2
    assert data["total_achievements"] == 3
    assert data["district_athletes"] == 1
    assert data["state_athletes"] == 1
    assert data["national_athletes"] == 1
    assert data["district_achievements"] == 1
    assert data["state_achievements"] == 1
    assert data["national_achievements"] == 1
    athletics = next(
        sport for sport in data["sport_breakdown"]
        if sport["sport_name"] == "Athletics"
    )
    assert athletics == {
        "sport_name": "Athletics",
        "athlete_count": 1,
        "achievement_count": 2,
    }
    assert data["recent_achievements"][0]["student_name"] == "Asha Runner"
    assert client.get(
        "/api/v1/dashboard/sports", headers=student_headers
    ).status_code == 403

    assert client.patch(
        f"/api/v1/sports/{state_achievement['id']}",
        json={"level": None},
        headers=admin_headers,
    ).status_code == 422
    updated = client.patch(
        f"/api/v1/sports/{state_achievement['id']}",
        json={"result": "Gold Medal"},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["result"] == "Gold Medal"
    assert client.delete(
        f"/api/v1/sports/{state_achievement['id']}", headers=admin_headers
    ).status_code == 204
    assert client.post(
        "/api/v1/sports",
        json={
            "student_id": 9999,
            "sport_name": "Tennis",
            "level": "national",
            "achievement_date": str(date.today()),
        },
        headers=admin_headers,
    ).status_code == 404


def test_notice_board_admin_management_and_authenticated_read(
    client: TestClient,
) -> None:
    admin_headers = login(client, "admin@example.com", "correct-horse-battery")
    assert client.get("/api/v1/notices").status_code == 401

    registration = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Nina",
            "last_name": "Student",
            "email": "nina@example.com",
            "password": "246810",
        },
    )
    assert registration.status_code == 201
    student_headers = login(client, "nina@example.com", "246810")

    first = client.post(
        "/api/v1/notices",
        json={
            "title": "Library schedule",
            "description": "The library closes at 5 PM.",
            "notice_date": "2026-10-22",
        },
        headers=admin_headers,
    )
    second = client.post(
        "/api/v1/notices",
        json={
            "title": "Sports day",
            "description": "Annual sports day is on Friday.",
            "notice_date": "2026-10-23",
        },
        headers=admin_headers,
    )
    assert first.status_code == second.status_code == 201
    assert second.json()["notice_date"] == "2026-10-23"

    listed = client.get("/api/v1/notices?limit=1", headers=student_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["title"] == "Sports day"
    assert client.post(
        "/api/v1/notices",
        json={
            "title": "Student notice",
            "description": "Students cannot publish notices.",
            "notice_date": "2026-10-24",
        },
        headers=student_headers,
    ).status_code == 403

    updated = client.patch(
        f"/api/v1/notices/{first.json()['id']}",
        json={"title": "Updated library schedule"},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated library schedule"
    assert client.patch(
        f"/api/v1/notices/{first.json()['id']}",
        json={"notice_date": None},
        headers=admin_headers,
    ).status_code == 422
    assert client.delete(
        f"/api/v1/notices/{first.json()['id']}", headers=student_headers
    ).status_code == 403
    assert client.delete(
        f"/api/v1/notices/{first.json()['id']}", headers=admin_headers
    ).status_code == 204
    assert client.get(
        f"/api/v1/notices/{first.json()['id']}", headers=admin_headers
    ).status_code == 404


def test_course_timetable_admin_management_and_enrolled_student_visibility(
    client: TestClient,
) -> None:
    admin_headers = login(client, "admin@example.com", "correct-horse-battery")
    assert client.get("/api/v1/timetable").status_code == 401

    student_registration = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Tara",
            "last_name": "Student",
            "email": "tara@example.com",
            "password": "246810",
        },
    )
    other_registration = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Omar",
            "last_name": "Student",
            "email": "omar@example.com",
            "password": "135790",
        },
    )
    assert student_registration.status_code == other_registration.status_code == 201
    student_id = student_registration.json()["user"]["student_id"]
    other_student_id = other_registration.json()["user"]["student_id"]
    student_headers = login(client, "tara@example.com", "246810")

    math_course = client.post(
        "/api/v1/courses",
        json={"code": "MATH101", "title": "Mathematics"},
        headers=admin_headers,
    )
    physics_course = client.post(
        "/api/v1/courses",
        json={"code": "PHYS101", "title": "Physics"},
        headers=admin_headers,
    )
    assert math_course.status_code == physics_course.status_code == 201
    math_course_id = math_course.json()["id"]
    physics_course_id = physics_course.json()["id"]
    assert client.post(
        "/api/v1/enrollments",
        json={"student_id": student_id, "course_id": math_course_id},
        headers=admin_headers,
    ).status_code == 201
    assert client.post(
        "/api/v1/enrollments",
        json={"student_id": other_student_id, "course_id": physics_course_id},
        headers=admin_headers,
    ).status_code == 201
    assert client.post(
        "/api/v1/enrollments",
        json={"student_id": other_student_id, "course_id": math_course_id},
        headers=admin_headers,
    ).status_code == 201

    monday_entry = {
        "course_id": math_course_id,
        "weekday": "Monday",
        "start_time": "09:00",
        "end_time": "10:00",
        "classroom_number": "Room 204",
    }
    created = client.post(
        "/api/v1/timetable", json=monday_entry, headers=admin_headers
    )
    tuesday = client.post(
        "/api/v1/timetable",
        json={
            **monday_entry,
            "course_id": physics_course_id,
            "weekday": "Tuesday",
            "start_time": "10:00",
            "end_time": "11:00",
        },
        headers=admin_headers,
    )
    other_entry = tuesday
    assert created.status_code == tuesday.status_code == 201
    assert created.json()["classroom_number"] == "Room 204"
    assert created.json()["start_time"].startswith("09:00")
    assert created.json()["course_title"] == "Mathematics"

    overlapping = client.post(
        "/api/v1/timetable",
        json={
            **monday_entry,
            "start_time": "09:45",
            "end_time": "10:30",
        },
        headers=admin_headers,
    )
    assert overlapping.status_code == 409
    assert client.post(
        "/api/v1/timetable",
        json={**monday_entry, "course_id": 9999},
        headers=admin_headers,
    ).status_code == 404
    assert client.post(
        "/api/v1/timetable",
        json={**monday_entry, "weekday": "Sunday"},
        headers=admin_headers,
    ).status_code == 422
    assert client.post(
        "/api/v1/timetable",
        json={**monday_entry, "end_time": "08:00"},
        headers=admin_headers,
    ).status_code == 422
    assert client.post(
        "/api/v1/timetable", json=monday_entry, headers=student_headers
    ).status_code == 403

    student_schedule = client.get(
        "/api/v1/timetable?limit=200", headers=student_headers
    )
    assert student_schedule.status_code == 200
    assert [entry["weekday"] for entry in student_schedule.json()] == ["Monday"]
    other_student_headers = login(client, "omar@example.com", "135790")
    other_student_schedule = client.get(
        "/api/v1/timetable?limit=200", headers=other_student_headers
    )
    assert [entry["weekday"] for entry in other_student_schedule.json()] == [
        "Monday",
        "Tuesday",
    ]
    assert client.get(
        f"/api/v1/timetable/{other_entry.json()['id']}", headers=student_headers
    ).status_code == 404

    updated = client.patch(
        f"/api/v1/timetable/{created.json()['id']}",
        json={"classroom_number": "Room 205"},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["classroom_number"] == "Room 205"
    assert client.delete(
        f"/api/v1/timetable/{created.json()['id']}", headers=student_headers
    ).status_code == 403
    assert client.delete(
        f"/api/v1/timetable/{created.json()['id']}", headers=admin_headers
    ).status_code == 204


def test_fee_assignments_payments_totals_and_student_access(
    client: TestClient,
) -> None:
    admin_headers = login(client, "admin@example.com", "correct-horse-battery")
    assert client.get("/api/v1/fees").status_code == 401

    registration = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Maya",
            "last_name": "Student",
            "email": "maya-fees@example.com",
            "password": "246810",
        },
    )
    assert registration.status_code == 201
    student_id = registration.json()["user"]["student_id"]
    student_headers = login(client, "maya-fees@example.com", "246810")
    other_registration = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Noah",
            "last_name": "Student",
            "email": "noah-fees@example.com",
            "password": "135790",
        },
    )
    assert other_registration.status_code == 201
    other_headers = login(client, "noah-fees@example.com", "135790")

    course = client.post(
        "/api/v1/courses",
        json={
            "code": "FEE101",
            "title": "Fee Test Course",
            "course_fee": "1200.00",
        },
        headers=admin_headers,
    )
    course_id = course.json()["id"]
    assert client.post(
        "/api/v1/enrollments",
        json={"student_id": student_id, "course_id": course_id},
        headers=admin_headers,
    ).status_code == 201

    fee = client.post(
        "/api/v1/fees",
        json={"student_id": student_id, "course_id": course_id},
        headers=admin_headers,
    )
    assert fee.status_code == 201
    fee_data = fee.json()
    assert fee_data["total_fee"] == "1200.00"
    assert fee_data["paid_fee"] == "0.00"
    assert fee_data["pending_fee"] == "1200.00"
    assert fee_data["status"] == "Pending"
    assert fee_data["student_name"] == "Maya Student"
    assert client.post(
        "/api/v1/fees",
        json={"student_id": student_id, "course_id": course_id},
        headers=admin_headers,
    ).status_code == 409
    assert client.post(
        "/api/v1/fees",
        json={"student_id": student_id, "course_id": 9999},
        headers=admin_headers,
    ).status_code == 404
    assert client.post(
        "/api/v1/fees",
        json={
            "student_id": student_id,
            "course_id": course_id,
            "total_fee": "0",
        },
        headers=admin_headers,
    ).status_code == 422
    assert client.post(
        "/api/v1/fees",
        json={
            "student_id": other_registration.json()["user"]["student_id"],
            "course_id": course_id,
        },
        headers=admin_headers,
    ).status_code == 422

    no_fee_course = client.post(
        "/api/v1/courses",
        json={"code": "FEE102", "title": "Course without a catalog fee"},
        headers=admin_headers,
    ).json()
    assert client.post(
        "/api/v1/enrollments",
        json={"student_id": student_id, "course_id": no_fee_course["id"]},
        headers=admin_headers,
    ).status_code == 201
    assert client.post(
        "/api/v1/fees",
        json={"student_id": student_id, "course_id": no_fee_course["id"]},
        headers=admin_headers,
    ).status_code == 422

    assert client.post(
        f"/api/v1/fees/{fee_data['id']}/payments",
        json={
            "amount": "0",
            "payment_date": "2026-10-22",
            "payment_method": "upi",
            "idempotency_key": "10c4a70d-8739-47f3-a5ee-1d4bd2f4d9a0",
        },
        headers=admin_headers,
    ).status_code == 422
    assert client.post(
        f"/api/v1/fees/{fee_data['id']}/payments",
        json={
            "amount": "-1.00",
            "payment_date": "2026-10-22",
            "payment_method": "upi",
            "idempotency_key": "20c4a70d-8739-47f3-a5ee-1d4bd2f4d9a0",
        },
        headers=admin_headers,
    ).status_code == 422
    assert client.post(
        f"/api/v1/fees/{fee_data['id']}/payments",
        json={
            "amount": "500",
            "payment_date": "2026-10-23",
            "payment_method": "upi",
            "idempotency_key": "30c4a70d-8739-47f3-a5ee-1d4bd2f4d9a0",
        },
        headers=student_headers,
    ).status_code == 403

    first_payment = client.post(
        f"/api/v1/fees/{fee_data['id']}/payments",
        json={
            "amount": "500.00",
            "payment_date": "2026-10-22",
            "payment_method": "upi",
            "idempotency_key": "40c4a70d-8739-47f3-a5ee-1d4bd2f4d9a0",
        },
        headers=admin_headers,
    )
    assert first_payment.status_code == 201
    assert first_payment.json()["replayed"] is False
    repeated_payment = client.post(
        f"/api/v1/fees/{fee_data['id']}/payments",
        json={
            "amount": "500.00",
            "payment_date": "2026-10-22",
            "payment_method": "upi",
            "idempotency_key": "40c4a70d-8739-47f3-a5ee-1d4bd2f4d9a0",
        },
        headers=admin_headers,
    )
    assert repeated_payment.status_code == 200
    assert repeated_payment.json()["replayed"] is True
    assert repeated_payment.json()["id"] == first_payment.json()["id"]
    conflicting_retry = client.post(
        f"/api/v1/fees/{fee_data['id']}/payments",
        json={
            "amount": "501.00",
            "payment_date": "2026-10-22",
            "payment_method": "upi",
            "idempotency_key": "40c4a70d-8739-47f3-a5ee-1d4bd2f4d9a0",
        },
        headers=admin_headers,
    )
    assert conflicting_retry.status_code == 409
    assert "already used for a different payment" in conflicting_retry.json()["detail"]
    separate_payment = client.post(
        f"/api/v1/fees/{fee_data['id']}/payments",
        json={
            "amount": "500.00",
            "payment_date": "2026-10-22",
            "payment_method": "upi",
            "idempotency_key": "50c4a70d-8739-47f3-a5ee-1d4bd2f4d9a0",
        },
        headers=admin_headers,
    )
    assert separate_payment.status_code == 201
    assert separate_payment.json()["id"] != first_payment.json()["id"]
    partial = client.get(
        "/api/v1/fees", headers=student_headers
    ).json()[0]
    assert partial["paid_fee"] == "1000.00"
    assert partial["pending_fee"] == "200.00"
    assert partial["status"] == "Partial"
    assert len(partial["payments"]) == 2
    assert {payment["payment_method"] for payment in partial["payments"]} == {"upi"}
    assert client.get("/api/v1/fees", headers=other_headers).json() == []

    updated_course = client.patch(
        f"/api/v1/courses/{course_id}",
        json={"course_fee": "1300.00"},
        headers=admin_headers,
    )
    assert updated_course.status_code == 200
    partial_after_course_edit = client.get(
        "/api/v1/fees", headers=student_headers
    ).json()[0]
    assert partial_after_course_edit["total_fee"] == "1300.00"
    assert partial_after_course_edit["paid_fee"] == "1000.00"
    assert partial_after_course_edit["pending_fee"] == "300.00"
    assert len(partial_after_course_edit["payments"]) == 2
    assert sorted(payment["amount"] for payment in partial_after_course_edit["payments"]) == [
        "500.00",
        "500.00",
    ]
    assert client.patch(
        f"/api/v1/courses/{course_id}",
        json={"course_fee": "499.99"},
        headers=admin_headers,
    ).status_code == 422
    assert client.patch(
        f"/api/v1/fees/{fee_data['id']}",
        json={"total_fee": "1500.00"},
        headers=admin_headers,
    ).status_code == 405

    assert client.post(
        f"/api/v1/fees/{fee_data['id']}/payments",
        json={
            "amount": "300.01",
            "payment_date": "2026-10-23",
            "payment_method": "cash",
            "idempotency_key": "60c4a70d-8739-47f3-a5ee-1d4bd2f4d9a0",
        },
        headers=admin_headers,
    ).status_code == 422
    final_payment = client.post(
        f"/api/v1/fees/{fee_data['id']}/payments",
        json={
            "amount": "300.00",
            "payment_date": "2026-10-23",
            "payment_method": "bank_transfer",
            "idempotency_key": "70c4a70d-8739-47f3-a5ee-1d4bd2f4d9a0",
        },
        headers=admin_headers,
    )
    assert final_payment.status_code == 201
    final_payment_retry = client.post(
        f"/api/v1/fees/{fee_data['id']}/payments",
        json={
            "amount": "300.00",
            "payment_date": "2026-10-23",
            "payment_method": "bank_transfer",
            "idempotency_key": "70c4a70d-8739-47f3-a5ee-1d4bd2f4d9a0",
        },
        headers=admin_headers,
    )
    assert final_payment_retry.status_code == 200
    assert final_payment_retry.json()["replayed"] is True
    assert final_payment_retry.json()["id"] == final_payment.json()["id"]
    paid = client.get("/api/v1/fees", headers=student_headers).json()[0]
    assert paid["total_fee"] == paid["paid_fee"] == "1300.00"
    assert paid["pending_fee"] == "0.00"
    assert paid["status"] == "Paid"
    assert len(paid["payments"]) == 3
    assert sorted(payment["amount"] for payment in paid["payments"]) == [
        "300.00",
        "500.00",
        "500.00",
    ]


def test_student_and_course_deletion_preserve_fee_records(
    client: TestClient,
) -> None:
    admin_headers = login(client, "admin@example.com", "correct-horse-battery")

    def register_student(email: str) -> int:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "first_name": "Finance",
                "last_name": "Test",
                "email": email,
                "password": "246810",
            },
        )
        assert response.status_code == 201
        return int(response.json()["user"]["student_id"])

    paid_student_id = register_student("paid-finance@example.com")
    assigned_student_id = register_student("assigned-finance@example.com")
    no_fee_student_id = register_student("no-fee-finance@example.com")
    course_response = client.post(
        "/api/v1/courses",
        json={
            "code": "FIN201",
            "title": "Financial Records Course",
            "course_fee": "900.00",
        },
        headers=admin_headers,
    )
    assert course_response.status_code == 201
    course_id = int(course_response.json()["id"])

    for student_id in (paid_student_id, assigned_student_id):
        assert client.post(
            "/api/v1/enrollments",
            json={"student_id": student_id, "course_id": course_id},
            headers=admin_headers,
        ).status_code == 201
    paid_fee = client.post(
        "/api/v1/fees",
        json={"student_id": paid_student_id, "course_id": course_id},
        headers=admin_headers,
    )
    assigned_fee = client.post(
        "/api/v1/fees",
        json={"student_id": assigned_student_id, "course_id": course_id},
        headers=admin_headers,
    )
    assert paid_fee.status_code == assigned_fee.status_code == 201
    payment = client.post(
        f"/api/v1/fees/{paid_fee.json()['id']}/payments",
        json={
            "amount": "250.00",
            "payment_date": "2026-10-24",
            "payment_method": "upi",
            "idempotency_key": "80c4a70d-8739-47f3-a5ee-1d4bd2f4d9a0",
        },
        headers=admin_headers,
    )
    assert payment.status_code == 201

    blocked_paid_student = client.delete(
        f"/api/v1/students/{paid_student_id}", headers=admin_headers
    )
    assert blocked_paid_student.status_code == 409
    assert "fee assignments or payment history" in blocked_paid_student.json()["detail"]
    blocked_assigned_student = client.delete(
        f"/api/v1/students/{assigned_student_id}", headers=admin_headers
    )
    assert blocked_assigned_student.status_code == 409
    assert "fee assignments or payment history" in blocked_assigned_student.json()["detail"]
    blocked_course = client.delete(
        f"/api/v1/courses/{course_id}", headers=admin_headers
    )
    assert blocked_course.status_code == 409
    assert "fee assignments or payment history" in blocked_course.json()["detail"]

    preserved_fees = client.get("/api/v1/fees", headers=admin_headers)
    assert preserved_fees.status_code == 200
    by_student = {item["student_id"]: item for item in preserved_fees.json()}
    assert set(by_student) == {paid_student_id, assigned_student_id}
    assert by_student[paid_student_id]["payments"][0]["id"] == payment.json()["id"]
    assert by_student[paid_student_id]["paid_fee"] == "250.00"
    assert by_student[assigned_student_id]["payments"] == []

    free_course = client.post(
        "/api/v1/courses",
        json={"code": "FIN202", "title": "No Financial Records Course"},
        headers=admin_headers,
    )
    assert free_course.status_code == 201
    assert client.delete(
        f"/api/v1/students/{no_fee_student_id}", headers=admin_headers
    ).status_code == 204
    assert client.delete(
        f"/api/v1/courses/{free_course.json()['id']}", headers=admin_headers
    ).status_code == 204

    foreign_keys = {
        foreign_key.parent.name: foreign_key.ondelete
        for foreign_key in FeeAssignment.__table__.foreign_keys
    }
    assert foreign_keys["student_id"] == "RESTRICT"
    assert foreign_keys["course_id"] == "RESTRICT"
    assert Student.fee_assignments.property.passive_deletes == "all"
    assert Course.fee_assignments.property.passive_deletes == "all"


def test_registration_never_grants_admin_and_rejects_bad_login(
    client: TestClient,
) -> None:
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Katherine",
            "last_name": "Johnson",
            "email": "katherine@example.com",
            "password": "123456",
            "role": "admin",
        },
    )
    assert registration.status_code == 422
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Katherine",
            "last_name": "Johnson",
            "email": "katherine@example.com",
            "password": "123456",
        },
    )
    assert registration.status_code == 201
    assert registration.json()["user"]["role"] == "student"
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "wrong-password"},
    ).status_code == 401


def test_hod_login_department_isolation_and_read_only_permissions(
    client: TestClient,
) -> None:
    admin_headers = login(client, "admin@example.com", "correct-horse-battery")

    def admin_create(path: str, body: dict[str, object]) -> dict[str, object]:
        response = client.post(path, json=body, headers=admin_headers)
        assert response.status_code == 201, response.text
        return response.json()

    department_a = admin_create(
        "/api/v1/departments", {"name": "Computer Science"}
    )
    department_b = admin_create("/api/v1/departments", {"name": "Mathematics"})
    department_a_id = int(department_a["id"])
    department_b_id = int(department_b["id"])
    add_hod_account("hod.cs@example.com", "Hod-password9!", department_a_id)

    course_a = admin_create(
        "/api/v1/courses",
        {
            "code": "CS101",
            "title": "Computer Science",
            "course_fee": "1000.00",
            "department_id": department_a_id,
        },
    )
    course_b = admin_create(
        "/api/v1/courses",
        {"code": "MA101", "title": "Mathematics", "department_id": department_b_id},
    )
    course_unassigned = admin_create(
        "/api/v1/courses", {"code": "OLD101", "title": "Legacy course"}
    )
    student_a = admin_create(
        "/api/v1/students",
        {"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com"},
    )
    student_b = admin_create(
        "/api/v1/students",
        {"first_name": "Alan", "last_name": "Turing", "email": "alan@example.com"},
    )
    student_a_id = int(student_a["id"])
    student_b_id = int(student_b["id"])
    course_a_id = int(course_a["id"])
    course_b_id = int(course_b["id"])
    enrollment_a = admin_create(
        "/api/v1/enrollments",
        {"student_id": student_a_id, "course_id": course_a_id},
    )
    enrollment_b = admin_create(
        "/api/v1/enrollments",
        {"student_id": student_b_id, "course_id": course_b_id},
    )
    attendance_a = admin_create(
        "/api/v1/attendance",
        {
            "student_id": student_a_id,
            "course_id": course_a_id,
            "attendance_date": "2026-10-21",
            "status": "present",
        },
    )
    attendance_b = admin_create(
        "/api/v1/attendance",
        {
            "student_id": student_b_id,
            "course_id": course_b_id,
            "attendance_date": "2026-10-21",
            "status": "absent",
        },
    )
    mark_a = admin_create(
        "/api/v1/marks",
        {
            "student_id": student_a_id,
            "course_id": course_a_id,
            "assessment_name": "Exam",
            "score": 90,
            "max_score": 100,
        },
    )
    mark_b = admin_create(
        "/api/v1/marks",
        {
            "student_id": student_b_id,
            "course_id": course_b_id,
            "assessment_name": "Exam",
            "score": 60,
            "max_score": 100,
        },
    )
    fee_a = admin_create(
        "/api/v1/fees", {"student_id": student_a_id, "course_id": course_a_id}
    )
    teacher_a = admin_create(
        "/api/v1/teachers",
        {
            "name": "Grace Hopper",
            "email": "grace@example.com",
            "department_id": department_a_id,
        },
    )
    teacher_b = admin_create(
        "/api/v1/teachers",
        {
            "name": "Emmy Noether",
            "email": "emmy@example.com",
            "department_id": department_b_id,
        },
    )
    timetable_a = admin_create(
        "/api/v1/timetable",
        {
            "course_id": course_a_id,
            "weekday": "Monday",
            "start_time": "09:00",
            "end_time": "10:00",
            "classroom_number": "Room 1",
        },
    )
    timetable_b = admin_create(
        "/api/v1/timetable",
        {
            "course_id": course_b_id,
            "weekday": "Tuesday",
            "start_time": "09:00",
            "end_time": "10:00",
            "classroom_number": "Room 2",
        },
    )
    sports_a = admin_create(
        "/api/v1/sports",
        {
            "student_id": student_a_id,
            "sport_name": "Cricket",
            "level": "district",
            "achievement_date": "2026-10-21",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "hod.cs@example.com", "password": "Hod-password9!"},
    )
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "hod"
    assert response.json()["user"]["department_id"] == department_a_id
    hod_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    def listed_ids(path: str) -> list[int]:
        result = client.get(path, headers=hod_headers)
        assert result.status_code == 200, result.text
        return [int(item["id"]) for item in result.json()]

    assert listed_ids("/api/v1/departments") == [department_a_id]
    assert listed_ids("/api/v1/courses") == [course_a_id]
    assert listed_ids("/api/v1/students") == [student_a_id]
    assert listed_ids("/api/v1/enrollments") == [int(enrollment_a["id"])]
    assert listed_ids("/api/v1/attendance") == [int(attendance_a["id"])]
    assert listed_ids("/api/v1/marks") == [int(mark_a["id"])]
    assert listed_ids("/api/v1/fees") == [int(fee_a["id"])]
    assert listed_ids("/api/v1/teachers") == [int(teacher_a["id"])]
    timetable_list = client.get("/api/v1/timetable", headers=hod_headers)
    assert timetable_list.status_code == 200
    assert [row["id"] for row in timetable_list.json()] == [timetable_a["id"]]
    assert course_b_id not in listed_ids("/api/v1/courses")
    assert int(course_unassigned["id"]) not in listed_ids("/api/v1/courses")

    results = client.get("/api/v1/results", headers=hod_headers)
    assert results.status_code == 200
    assert [item["student_id"] for item in results.json()] == [student_a_id]
    dashboard = client.get("/api/v1/dashboard/hod", headers=hod_headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["department_id"] == department_a_id
    assert dashboard.json()["total_students"] == 1
    assert dashboard.json()["total_teachers"] == 1

    for path in (
        f"/api/v1/departments/{department_b_id}",
        f"/api/v1/courses/{course_b_id}",
        f"/api/v1/students/{student_b_id}",
        f"/api/v1/enrollments/{enrollment_b['id']}",
        f"/api/v1/attendance/{attendance_b['id']}",
        f"/api/v1/marks/{mark_b['id']}",
        f"/api/v1/teachers/{teacher_b['id']}",
        f"/api/v1/timetable/{timetable_b['id']}",
    ):
        assert client.get(path, headers=hod_headers).status_code == 404

    assert client.get("/api/v1/notices", headers=hod_headers).status_code == 403
    assert client.get("/api/v1/sports", headers=hod_headers).status_code == 403
    assert client.get(
        f"/api/v1/sports/{sports_a['id']}", headers=hod_headers
    ).status_code == 403
    add_hod_account("hod.unassigned@example.com", "Hod-password9!", None)
    unassigned_hod_headers = login(
        client, "hod.unassigned@example.com", "Hod-password9!"
    )
    assert client.get(
        "/api/v1/students", headers=unassigned_hod_headers
    ).status_code == 403
    assert client.get(
        "/api/v1/courses", headers=unassigned_hod_headers
    ).status_code == 403
    assert client.get(
        f"/api/v1/courses/{course_unassigned['id']}",
        headers=unassigned_hod_headers,
    ).status_code == 403
    assert client.post(
        "/api/v1/departments",
        json={"name": "Unauthorized"},
        headers=hod_headers,
    ).status_code == 403
    assert client.post(
        "/api/v1/teachers",
        json={
            "name": "Unauthorized",
            "email": "unauthorized@example.com",
            "department_id": department_a_id,
        },
        headers=hod_headers,
    ).status_code == 403
    assert client.patch(
        f"/api/v1/courses/{course_a_id}",
        json={"department_id": department_b_id},
        headers=hod_headers,
    ).status_code == 403
    assert client.patch(
        f"/api/v1/attendance/{attendance_a['id']}",
        json={"status": "absent"},
        headers=hod_headers,
    ).status_code == 403
    assert client.delete(
        f"/api/v1/students/{student_a_id}", headers=hod_headers
    ).status_code == 403
    assert client.post(
        f"/api/v1/fees/{fee_a['id']}/payments",
        json={
            "amount": "10.00",
            "payment_date": "2026-10-22",
            "payment_method": "cash",
            "idempotency_key": "90c4a70d-8739-47f3-a5ee-1d4bd2f4d9a0",
        },
        headers=hod_headers,
    ).status_code == 403

    assert client.get("/api/v1/courses", headers=admin_headers).status_code == 200


def test_teacher_course_isolation_and_assigned_academic_writes(
    client: TestClient,
) -> None:
    admin_headers = login(client, "admin@example.com", "correct-horse-battery")

    def admin_create(path: str, body: dict[str, object]) -> dict[str, object]:
        response = client.post(path, json=body, headers=admin_headers)
        assert response.status_code == 201, response.text
        return response.json()

    department = admin_create(
        "/api/v1/departments", {"name": "Physics"}
    )
    department_id = int(department["id"])
    teacher = admin_create(
        "/api/v1/teachers",
        {
            "name": "Katherine Johnson",
            "email": "katherine.teacher@example.com",
            "department_id": department_id,
        },
    )
    teacher_id = int(teacher["id"])
    assigned_course = admin_create(
        "/api/v1/courses",
        {"code": "PH101", "title": "Physics I", "department_id": department_id},
    )
    unassigned_course = admin_create(
        "/api/v1/courses",
        {"code": "PH102", "title": "Physics II", "department_id": department_id},
    )
    assigned_course_id = int(assigned_course["id"])
    unassigned_course_id = int(unassigned_course["id"])
    assignment = client.post(
        f"/api/v1/teachers/{teacher_id}/courses",
        json={"course_id": assigned_course_id},
        headers=admin_headers,
    )
    assert assignment.status_code == 201
    other_department = admin_create(
        "/api/v1/departments", {"name": "Chemistry"}
    )
    other_department_course = admin_create(
        "/api/v1/courses",
        {
            "code": "CH101",
            "title": "Chemistry I",
            "department_id": int(other_department["id"]),
        },
    )
    cross_department_assignment = client.post(
        f"/api/v1/teachers/{teacher_id}/courses",
        json={"course_id": int(other_department_course["id"])},
        headers=admin_headers,
    )
    assert cross_department_assignment.status_code == 422
    department_unassigned_course = admin_create(
        "/api/v1/courses",
        {"code": "PH103", "title": "Physics III"},
    )
    unassigned_response = client.post(
        f"/api/v1/teachers/{teacher_id}/courses",
        json={"course_id": int(department_unassigned_course["id"])},
        headers=admin_headers,
    )
    assert unassigned_response.status_code == 422
    assert unassigned_response.json()["detail"] == (
        "Teacher and course must belong to the same department"
    )
    corrected_course = client.patch(
        f"/api/v1/courses/{department_unassigned_course['id']}",
        json={"department_id": department_id},
        headers=admin_headers,
    )
    assert corrected_course.status_code == 200
    corrected_assignment = client.post(
        f"/api/v1/teachers/{teacher_id}/courses",
        json={"course_id": int(department_unassigned_course["id"])},
        headers=admin_headers,
    )
    assert corrected_assignment.status_code == 201
    assert client.get(
        "/api/v1/teachers/assignments", headers=admin_headers
    ).json()[0]["course_id"] == assigned_course_id
    add_teacher_account(
        "katherine.teacher@example.com", "Teacher-password9!", teacher_id
    )

    student_in_course = admin_create(
        "/api/v1/students",
        {
            "first_name": "Marie",
            "last_name": "Curie",
            "email": "marie@example.com",
        },
    )
    student_other_course = admin_create(
        "/api/v1/students",
        {
            "first_name": "Niels",
            "last_name": "Bohr",
            "email": "niels@example.com",
        },
    )
    student_id = int(student_in_course["id"])
    other_student_id = int(student_other_course["id"])
    admin_create(
        "/api/v1/enrollments",
        {"student_id": student_id, "course_id": assigned_course_id},
    )
    admin_create(
        "/api/v1/enrollments",
        {"student_id": other_student_id, "course_id": unassigned_course_id},
    )
    existing_attendance = admin_create(
        "/api/v1/attendance",
        {
            "student_id": student_id,
            "course_id": assigned_course_id,
            "attendance_date": "2026-10-20",
            "status": "present",
        },
    )
    existing_mark = admin_create(
        "/api/v1/marks",
        {
            "student_id": student_id,
            "course_id": assigned_course_id,
            "assessment_name": "Quiz",
            "score": 8,
            "max_score": 10,
        },
    )
    other_course_attendance = admin_create(
        "/api/v1/attendance",
        {
            "student_id": other_student_id,
            "course_id": unassigned_course_id,
            "attendance_date": "2026-10-20",
            "status": "absent",
        },
    )
    other_course_mark = admin_create(
        "/api/v1/marks",
        {
            "student_id": other_student_id,
            "course_id": unassigned_course_id,
            "assessment_name": "Quiz",
            "score": 5,
            "max_score": 10,
        },
    )

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "katherine.teacher@example.com",
            "password": "Teacher-password9!",
        },
    )
    assert login_response.status_code == 200
    assert login_response.json()["user"]["role"] == "teacher"
    assert login_response.json()["user"]["teacher_id"] == teacher_id
    teacher_headers = {
        "Authorization": f"Bearer {login_response.json()['access_token']}"
    }

    assert [
        row["id"]
        for row in client.get("/api/v1/courses", headers=teacher_headers).json()
    ] == [assigned_course_id, int(department_unassigned_course["id"])]
    assert client.get(
        f"/api/v1/courses/{unassigned_course_id}", headers=teacher_headers
    ).status_code == 404
    assert [row["id"] for row in client.get(
        "/api/v1/students", headers=teacher_headers
    ).json()] == [student_id]
    assert client.get(
        f"/api/v1/students/{other_student_id}", headers=teacher_headers
    ).status_code == 404
    assert [
        row["course_id"]
        for row in client.get("/api/v1/enrollments", headers=teacher_headers).json()
    ] == [assigned_course_id]
    assert [
        row["id"]
        for row in client.get("/api/v1/attendance", headers=teacher_headers).json()
    ] == [existing_attendance["id"]]
    assert [
        row["id"]
        for row in client.get("/api/v1/marks", headers=teacher_headers).json()
    ] == [existing_mark["id"]]
    teacher_results = client.get("/api/v1/results", headers=teacher_headers)
    assert teacher_results.status_code == 200
    assert [row["course_id"] for row in teacher_results.json()] == [
        assigned_course_id
    ]
    dashboard = client.get("/api/v1/dashboard/teacher", headers=teacher_headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["total_courses"] == 2
    assert dashboard.json()["total_students"] == 1
    assert [
        row["id"]
        for row in client.get("/api/v1/teachers", headers=teacher_headers).json()
    ] == [teacher_id]
    assert client.get(
        f"/api/v1/teachers/{teacher_id + 1}", headers=teacher_headers
    ).status_code == 404

    new_attendance = client.post(
        "/api/v1/attendance",
        json={
            "student_id": student_id,
            "course_id": assigned_course_id,
            "attendance_date": "2026-10-21",
            "status": "late",
        },
        headers=teacher_headers,
    )
    assert new_attendance.status_code == 201
    updated_attendance = client.patch(
        f"/api/v1/attendance/{existing_attendance['id']}",
        json={"status": "late"},
        headers=teacher_headers,
    )
    assert updated_attendance.status_code == 200
    new_mark = client.post(
        "/api/v1/marks",
        json={
            "student_id": student_id,
            "course_id": assigned_course_id,
            "assessment_name": "Midterm",
            "score": 90,
            "max_score": 100,
        },
        headers=teacher_headers,
    )
    assert new_mark.status_code == 201
    updated_mark = client.patch(
        f"/api/v1/marks/{existing_mark['id']}",
        json={"score": 9},
        headers=teacher_headers,
    )
    assert updated_mark.status_code == 200

    assert client.post(
        "/api/v1/attendance",
        json={
            "student_id": other_student_id,
            "course_id": unassigned_course_id,
            "attendance_date": "2026-10-21",
            "status": "present",
        },
        headers=teacher_headers,
    ).status_code == 404
    assert client.post(
        "/api/v1/attendance",
        json={
            "student_id": other_student_id,
            "course_id": assigned_course_id,
            "attendance_date": "2026-10-21",
            "status": "present",
        },
        headers=teacher_headers,
    ).status_code == 422
    assert client.post(
        "/api/v1/marks",
        json={
            "student_id": other_student_id,
            "course_id": unassigned_course_id,
            "assessment_name": "Midterm",
            "score": 90,
            "max_score": 100,
        },
        headers=teacher_headers,
    ).status_code == 404
    assert client.patch(
        f"/api/v1/attendance/{other_course_attendance['id']}",
        json={"status": "present"},
        headers=teacher_headers,
    ).status_code == 404
    assert client.patch(
        f"/api/v1/marks/{other_course_mark['id']}",
        json={"score": 6},
        headers=teacher_headers,
    ).status_code == 404
    assert client.delete(
        f"/api/v1/attendance/{existing_attendance['id']}",
        headers=teacher_headers,
    ).status_code == 403
    assert client.post(
        "/api/v1/courses",
        json={"code": "PH103", "title": "Not allowed"},
        headers=teacher_headers,
    ).status_code == 403
    assert client.post(
        "/api/v1/teachers",
        json={
            "name": "Not allowed",
            "email": "other.teacher@example.com",
            "department_id": department_id,
        },
        headers=teacher_headers,
    ).status_code == 403
    assert client.get("/api/v1/fees", headers=teacher_headers).status_code == 403
    assert client.get("/api/v1/notices", headers=teacher_headers).status_code == 403
    assert client.get(
        "/api/v1/dashboard/principal", headers=teacher_headers
    ).status_code == 403

    assert client.delete(
        f"/api/v1/teachers/{teacher_id}/courses/{assigned_course_id}",
        headers=admin_headers,
    ).status_code == 204
    assert client.delete(
        f"/api/v1/teachers/{teacher_id}/courses/{department_unassigned_course['id']}",
        headers=admin_headers,
    ).status_code == 204
    assert client.get(
        "/api/v1/courses", headers=teacher_headers
    ).json() == []

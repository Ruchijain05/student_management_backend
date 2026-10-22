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
from app.models import User
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
        "/api/v1/dashboard/admin", headers=student_headers
    ).status_code == 403
    assert client.get(
        "/api/v1/dashboard/admin", headers=admin_headers
    ).json()["total_students"] == 2
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

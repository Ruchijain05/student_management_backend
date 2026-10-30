from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    attendance,
    auth,
    courses,
    dashboard,
    departments,
    enrollments,
    fees,
    marks,
    notices,
    results,
    students,
    teachers,
    sports,
    sports_dashboard,
    timetable,
)

app = FastAPI(
    title="Student Management System",
    description=(
        "API for students, courses, enrollments, attendance, marks, results, "
        "sports achievements, notices, timetables, and fees."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.cors_origins.split(",")
        if origin.strip()
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(students.router, prefix="/api/v1")
app.include_router(courses.router, prefix="/api/v1")
app.include_router(enrollments.router, prefix="/api/v1")
app.include_router(fees.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(attendance.router, prefix="/api/v1")
app.include_router(marks.router, prefix="/api/v1")
app.include_router(results.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(departments.router, prefix="/api/v1")
app.include_router(teachers.router, prefix="/api/v1")
app.include_router(sports.router, prefix="/api/v1")
app.include_router(sports_dashboard.router, prefix="/api/v1")
app.include_router(notices.router, prefix="/api/v1")
app.include_router(timetable.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}

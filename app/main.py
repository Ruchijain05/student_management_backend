from fastapi import FastAPI

from app.routers import (
    attendance,
    auth,
    courses,
    dashboard,
    enrollments,
    marks,
    results,
    students,
)

app = FastAPI(
    title="Student Management System",
    description=(
        "API for students, courses, enrollments, attendance, marks, and results."
    ),
    version="1.0.0",
)

app.include_router(students.router, prefix="/api/v1")
app.include_router(courses.router, prefix="/api/v1")
app.include_router(enrollments.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(attendance.router, prefix="/api/v1")
app.include_router(marks.router, prefix="/api/v1")
app.include_router(results.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}

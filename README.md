# Student Management System API

FastAPI application with MySQL persistence, SQLAlchemy ORM, Pydantic validation,
JWT login, and admin/student access control.

## Project layout

```text
app/
  routers/       API routes, grouped by feature
  config.py      Environment-based settings
  create_admin.py
  database.py    SQLAlchemy engine and session dependency
  enums.py       Role and attendance values
  main.py        FastAPI application and router registration
  models.py      SQLAlchemy tables
  schemas.py     Pydantic request and response models
  security.py    Password hashing, JWTs, and role dependencies
main.py          Uvicorn entry point
schema.sql       Complete schema for a new database
migration_v2.sql Adds the account, attendance, and mark tables to the starter DB
migration_v3.sql Adds password-reset storage and token-version invalidation
migration_v4.sql Adds student sports achievements
migration_v5.sql Adds the Notice Board
migration_v6.sql Historical migration for student-specific timetable entries
migration_v7.sql Adds the course-wise timetable
migration_v8.sql Adds course fee assignments and payment history
migration_v9.sql Adds the optional catalog fee to courses
```

## Installation and database setup

Run the following commands in PowerShell from the repository root (the folder
containing `student_management_system_backend` and
`student_management_system_frontend`). The virtual environment and dependencies
are kept inside the backend folder:

```powershell
py -m venv .\student_management_system_backend\.venv
& .\student_management_system_backend\.venv\Scripts\python.exe -m pip install -r .\student_management_system_backend\requirements.txt
```

If you already created and activated the backend virtual environment, run the
installation command above to install any missing requirements into the backend
virtual environment. Using its `python.exe` explicitly ensures the packages are
installed into the same environment that will run the API. In particular,
`pydantic-settings` is required by the backend.

Create or edit `student_management_system_backend\.env` with your MySQL
connection details and a unique signing key. The backend reads this file by its
path, so it works whether you launch Uvicorn from the repository root or the
backend folder. Generate a key with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

The signing key must be at least 32 characters. URL-encode special characters
in the database password.

For a **new database**, run:

```powershell
Get-Content .\student_management_system_backend\schema.sql | mysql -u YOUR_MYSQL_USER -p
```

For an existing database created using the original three-table starter, back
it up and run the additive migration:

```powershell
Get-Content .\student_management_system_backend\migration_v2.sql | mysql -u YOUR_MYSQL_USER -p
```

For an existing database that already has the v2 tables, run:

```powershell
Get-Content .\student_management_system_backend\migration_v3.sql | mysql -u YOUR_MYSQL_USER -p
```

If you already ran an earlier version of `migration_v3.sql`, rerun this
idempotent migration to add the OTP attempt counter. It preserves existing rows.

For an existing database with the v3 tables, run the additive sports migration:

```powershell
Get-Content .\student_management_system_backend\migration_v4.sql | mysql -u YOUR_MYSQL_USER -p
```

If the API reports `Table 'student_management.sports_achievements' doesn't
exist`, run the same command against the database configured in
`student_management_backend\.env`. `migration_v4.sql` uses
`CREATE TABLE IF NOT EXISTS`: it creates only the missing sports table and
preserves existing student, account, and academic data. Verify it with:

```powershell
mysql -u YOUR_MYSQL_USER -p student_management -e "SHOW TABLES LIKE 'sports_achievements';"
```

The migration's `USE student_management` must match the database name in
`DATABASE_URL`. If you use a different database name, update that `USE` line
before running the migration. The API does not create or migrate tables at
startup, so apply this migration before using sports endpoints or the sports
dashboard.

For an existing database, create the Notice Board table with the additive,
rerunnable migration:

```powershell
Get-Content .\student_management_system_backend\migration_v5.sql | mysql -u YOUR_MYSQL_USER -p
```

`migration_v5.sql` only creates the missing `notices` table and preserves
existing data. Its `USE` database must match the database configured in
`DATABASE_URL`. The API does not migrate tables at startup; apply this migration
before loading the frontend dashboard or Notice Board.

For an existing database, add the course-wise timetable with its additive,
rerunnable migration:

```powershell
Get-Content .\student_management_system_backend\migration_v7.sql | mysql -u YOUR_MYSQL_USER -p
```

`migration_v7.sql` creates only `course_timetable_entries` and preserves
existing data. Its `USE` database must match `DATABASE_URL`. If you previously
used `migration_v6.sql`, its student-specific table and records remain
untouched; new timetable entries are stored by course and old entries are not
automatically assigned to courses.

For an existing database, add course fee assignments and payment history with
the additive, rerunnable migration:

```powershell
Get-Content .\student_management_system_backend\migration_v8.sql | mysql -u YOUR_MYSQL_USER -p
```

`migration_v8.sql` creates only the fee assignment and payment tables.
Students must be enrolled in a course before an admin can assign that course's
fees. Payment history is retained separately; paid, pending, and status values
are calculated from these records. The migration's `USE` database must match
`DATABASE_URL`.

For an existing database, add the optional standard fee to the course catalog:

```powershell
Get-Content .\student_management_system_backend\migration_v9.sql | mysql -u YOUR_MYSQL_USER -p
```

Apply this migration once after v8. Existing courses keep their records and
have a null course fee until an admin sets one. Course fees must be positive
amounts with at most two decimal places.

The API does not create or migrate tables at startup. Create the first admin
after the database is ready. This command runs from the backend folder:

```powershell
Push-Location .\student_management_system_backend
& .\.venv\Scripts\python.exe -m app.create_admin
Pop-Location
```

The command prompts for an email and a password (6-8 digits); it
does not place admin credentials in source code or the database as plaintext.

Start the application from the repository root:

```powershell
& .\student_management_system_backend\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir .\student_management_system_backend
```

Interactive API documentation: <http://127.0.0.1:8000/docs>

For a separately hosted frontend, set `CORS_ORIGINS` in `.env` to a
comma-separated list of exact frontend origins (for example,
`http://localhost:5173`). Leave it empty when the frontend is served through a
same-origin reverse proxy. Restart the API after changing this setting.

To run the focused API tests (they use an isolated in-memory SQLite database):

```powershell
& .\student_management_system_backend\.venv\Scripts\python.exe -m pip install -r .\student_management_system_backend\requirements-dev.txt
Push-Location .\student_management_system_backend
& .\.venv\Scripts\python.exe -m pytest
Pop-Location
```

## Authentication and roles

- `POST /api/v1/auth/register` registers a student and creates a linked student
  record. New passwords must contain 6-8 ASCII digits. Public registration
  always assigns the `student` role.
- `POST /api/v1/auth/login` accepts JSON `{ "email": "...", "password": "..." }`
  and returns a bearer access token.
- `POST /api/v1/auth/password-reset/request` accepts an email and generates a
  single-use six-digit OTP when the account exists. Its response does not
  disclose whether the address is registered. The OTP is printed only when
  `APP_ENV=development` and `PASSWORD_RESET_OTP_CONSOLE_ENABLED=true`; keep
  console output disabled outside local testing. In this explicitly enabled
  local mode, a new OTP can be generated on each request; the one-minute
  cooldown remains active otherwise.
- `POST /api/v1/auth/password-reset/confirm` accepts `email`, the six-digit
  `otp`, and a new password (6-8 ASCII digits). OTPs expire after five minutes,
  allow at most five verification attempts, and can only be used once.
  Resetting a password invalidates previously issued JWTs.
- To test reset in Swagger locally, set `APP_ENV=development` and
  `PASSWORD_RESET_OTP_CONSOLE_ENABLED=true` in `.env`, restart the app, and open
  `/docs`. Call `POST /api/v1/auth/password-reset/request` with the account
  email, copy the six-digit OTP from the VS Code terminal, then call
  `POST /api/v1/auth/password-reset/confirm` with the account email, the
  printed value as `otp`, and a `new_password` containing 6-8 digits. The OTP
  is not included in the API response. Disable console output outside local
  testing.
- Existing passwords remain valid for login; the new numeric policy applies
  when registering an account or choosing a password through password reset.
- In Swagger UI, select **Authorize** and enter the account email as the
  username and its password. Swagger obtains and sends the JWT automatically.
- Send `Authorization: Bearer <access_token>` on protected routes.
- Only admins can create, update, or delete students, courses, enrollments,
  attendance, marks, sports achievements, notices, and timetable entries.
  Authenticated students can read notices, their own student record,
  enrollments, attendance, marks, results, sports achievements, timetable, and
  fee details. Only admins can assign course fees to students or record
  payments; course totals are managed through the Courses API. Authenticated
  users can search/view courses.
- Use `python -m app.create_admin` to create an administrator; there is no
  public admin registration endpoint.

## API routes

| Method | Path | Access | Description |
| --- | --- | --- | --- |
| GET | `/health` | Public | Process health check |
| POST | `/api/v1/auth/register` | Public | Register student account |
| POST | `/api/v1/auth/login` | Public | Log in and receive JWT |
| POST | `/api/v1/auth/password-reset/request` | Public | Generate reset OTP |
| POST | `/api/v1/auth/password-reset/confirm` | Public | Set a new password |
| GET | `/api/v1/auth/me` | Authenticated | Current account |
| POST / GET | `/api/v1/students` | Admin / Authenticated | Create / search and list |
| GET | `/api/v1/students/{id}` | Admin / Own student | Read student |
| PATCH / DELETE | `/api/v1/students/{id}` | Admin | Update / delete student |
| POST / GET | `/api/v1/courses` | Admin / Authenticated | Create / search and list |
| GET / PATCH / DELETE | `/api/v1/courses/{id}` | Authenticated / Admin | Read / update / delete |
| POST / GET | `/api/v1/enrollments` | Admin / Authenticated | Create / list (filterable) |
| GET / PATCH / DELETE | `/api/v1/enrollments/{id}` | Own / Admin | Read / update / delete |
| POST / GET | `/api/v1/attendance` | Admin / Authenticated | Record / list attendance |
| GET / PATCH / DELETE | `/api/v1/attendance/{id}` | Own / Admin | Read / update / delete |
| POST / GET | `/api/v1/marks` | Admin / Authenticated | Record / list assessment marks |
| GET / PATCH / DELETE | `/api/v1/marks/{id}` | Own / Admin | Read / update / delete |
| POST / GET | `/api/v1/sports` | Admin / Authenticated | Record / list sports achievements |
| GET / PATCH / DELETE | `/api/v1/sports/{id}` | Own / Admin | Read / update / delete achievement |
| GET | `/api/v1/notices` | Authenticated | List notices, newest date first |
| POST | `/api/v1/notices` | Admin | Create a notice |
| GET | `/api/v1/notices/{id}` | Authenticated | Read a notice |
| PATCH / DELETE | `/api/v1/notices/{id}` | Admin | Update / delete a notice |
| GET / POST | `/api/v1/timetable` | Enrolled student GET / Admin | Read enrolled-course schedules / add an entry |
| GET / PATCH / DELETE | `/api/v1/timetable/{id}` | Enrolled student GET / Admin | Read / update / delete an entry |
| GET / POST | `/api/v1/fees` | Student GET / Admin | Read fee details / assign course fees |
| GET | `/api/v1/fees/{id}` | Own student GET / Admin | Read fee assignment |
| POST | `/api/v1/fees/{id}/payments` | Admin | Record a payment |
| GET | `/api/v1/results` | Authenticated | Course result summary |
| GET | `/api/v1/dashboard/admin` | Admin | System totals and today's attendance |
| GET | `/api/v1/dashboard/student` | Student | Own enrollment, attendance, and mark summary |
| GET | `/api/v1/dashboard/sports` | Admin | Athlete totals, achievement levels, sports breakdown, and recent achievements |

Student/course search uses `?q=...`. List routes support `offset` and `limit`
(maximum 100, or 200 for timetable entries). Admins can filter enrollments, attendance, and marks by student and/or course
ID. Timetable entries can be filtered by course ID. Sports records can be filtered by student, sport name, and
competition level.

Courses include an optional catalog fee. Admins can set or update it through
the course endpoints; authenticated course reads return it for the frontend.
Existing student/course fee assignments remain independently managed.

Sports achievements record a sport, district/state/national competition level,
date, and optional event, competition, and result details. Admins manage these
records; students can only view their own sports achievements. The sports
dashboard summarizes distinct athletes overall and at each level, achievement
counts by level, per-sport participation, and the ten most recent achievements.

Attendance is recorded once per student/course/date and requires an existing
enrollment. Marks are limited to `0 <= score <= max_score` and one assessment
name per student/course. Results average the percentage scores of assessments
within each course and map them to grades: A (90+), B (80+), C (70+), D (60+),
otherwise F. A course without marks has no result row yet. Attendance dashboard
percentage counts `present` and `late` as attended.

Admins assign timetable entries to existing courses. Schedules are limited to
Monday through Saturday, sorted by weekday and lecture start time, and reject
overlapping classes for the same course and day. Students automatically see
schedules for their enrolled courses; the student dashboard highlights
today's classes.

Fees are assigned per enrolled student/course using the course fee set through
the Courses API. Updating a course fee updates its student assignments while
retaining payment history; changes that would put a fee below recorded payments
are rejected. Payment totals, pending balances, and `Paid`, `Partial`, or
`Pending` status are derived from the ledger. Students can view only their own
fee details and payment history.

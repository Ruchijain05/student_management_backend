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
```

## Installation and database setup

From the project root in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` with your MySQL connection details and a unique signing key. Generate
a key with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

The signing key must be at least 32 characters. URL-encode special characters
in the database password.

For a **new database**, run:

```powershell
Get-Content .\schema.sql | mysql -u YOUR_MYSQL_USER -p
```

For an existing database created using the original three-table starter, back
it up and run the additive migration:

```powershell
Get-Content .\migration_v2.sql | mysql -u YOUR_MYSQL_USER -p
```

For an existing database that already has the v2 tables, run:

```powershell
Get-Content .\migration_v3.sql | mysql -u YOUR_MYSQL_USER -p
```

If you already ran an earlier version of `migration_v3.sql`, rerun this
idempotent migration to add the OTP attempt counter. It preserves existing rows.

The API does not create or migrate tables at startup. Create the first admin
after the database is ready:

```powershell
python -m app.create_admin
```

The command prompts for an email and a password (6-8 digits); it
does not place admin credentials in source code or the database as plaintext.

Start the application:

```powershell
uvicorn main:app --reload
```

Interactive API documentation: <http://127.0.0.1:8000/docs>

To run the focused API tests (they use an isolated in-memory SQLite database):

```powershell
pip install -r requirements-dev.txt
python -m pytest
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
  attendance, and marks. Students can read only their own student record,
  enrollments, attendance, marks, results, and dashboard. Authenticated users
  can search/view courses.
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
| GET | `/api/v1/results` | Authenticated | Course result summary |
| GET | `/api/v1/dashboard/admin` | Admin | System totals and today's attendance |
| GET | `/api/v1/dashboard/student` | Student | Own enrollment, attendance, and mark summary |

Student/course search uses `?q=...`. List routes support `offset` and `limit`
(maximum 100). Admins can filter enrollments, attendance, and marks by student
and/or course ID.

Attendance is recorded once per student/course/date and requires an existing
enrollment. Marks are limited to `0 <= score <= max_score` and one assessment
name per student/course. Results average the percentage scores of assessments
within each course and map them to grades: A (90+), B (80+), C (70+), D (60+),
otherwise F. A course without marks has no result row yet. Attendance dashboard
percentage counts `present` and `late` as attended.

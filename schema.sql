CREATE DATABASE IF NOT EXISTS student_management
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE student_management;

CREATE TABLE IF NOT EXISTS students (
    id INT NOT NULL AUTO_INCREMENT,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_students_email (email)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS departments (
    id INT NOT NULL AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_departments_name (name)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS courses (
    id INT NOT NULL AUTO_INCREMENT,
    code VARCHAR(20) NOT NULL,
    title VARCHAR(150) NOT NULL,
    description VARCHAR(500) NULL,
    course_fee DECIMAL(10, 2) NULL,
    department_id INT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_courses_code (code),
    KEY ix_courses_department_id (department_id),
    CONSTRAINT fk_courses_department
        FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS enrollments (
    id INT NOT NULL AUTO_INCREMENT,
    student_id INT NOT NULL,
    course_id INT NOT NULL,
    enrolled_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_student_course (student_id, course_id),
    CONSTRAINT fk_enrollments_student
        FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE,
    CONSTRAINT fk_enrollments_course
        FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS users (
    id INT NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(10) NOT NULL DEFAULT 'student',
    token_version INT NOT NULL DEFAULT 0,
    password_reset_requested_at DATETIME NULL,
    student_id INT NULL,
    department_id INT NULL,
    teacher_id INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_email (email),
    UNIQUE KEY uq_users_student_id (student_id),
    CONSTRAINT ck_users_role CHECK (role IN ('admin', 'student', 'principal', 'hod', 'teacher')),
    CONSTRAINT fk_users_student
        FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE,
    KEY ix_users_department_id (department_id),
    UNIQUE KEY uq_users_teacher_id (teacher_id),
    CONSTRAINT fk_users_department
        FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS teachers (
    id INT NOT NULL AUTO_INCREMENT,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(255) NOT NULL,
    department_id INT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_teachers_email (email),
    KEY ix_teachers_department_id (department_id),
    CONSTRAINT fk_teachers_department
        FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE RESTRICT
) ENGINE=InnoDB;

ALTER TABLE users
    ADD CONSTRAINT fk_users_teacher
        FOREIGN KEY (teacher_id) REFERENCES teachers (id) ON DELETE CASCADE;

CREATE TABLE IF NOT EXISTS teacher_courses (
    id INT NOT NULL AUTO_INCREMENT,
    teacher_id INT NOT NULL,
    course_id INT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_teacher_course (teacher_id, course_id),
    KEY ix_teacher_courses_teacher_id (teacher_id),
    KEY ix_teacher_courses_course_id (course_id),
    CONSTRAINT fk_teacher_courses_teacher
        FOREIGN KEY (teacher_id) REFERENCES teachers (id) ON DELETE CASCADE,
    CONSTRAINT fk_teacher_courses_course
        FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id INT NOT NULL AUTO_INCREMENT,
    user_id INT NOT NULL,
    token_hash CHAR(64) NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_password_reset_token_hash (token_hash),
    KEY ix_password_reset_tokens_user_id (user_id),
    CONSTRAINT fk_password_reset_tokens_user
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS attendance (
    id INT NOT NULL AUTO_INCREMENT,
    student_id INT NOT NULL,
    course_id INT NOT NULL,
    attendance_date DATE NOT NULL,
    status VARCHAR(10) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_attendance_student_course_date
        (student_id, course_id, attendance_date),
    CONSTRAINT ck_attendance_status
        CHECK (status IN ('present', 'absent', 'late', 'excused')),
    CONSTRAINT fk_attendance_student
        FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE,
    CONSTRAINT fk_attendance_course
        FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS marks (
    id INT NOT NULL AUTO_INCREMENT,
    student_id INT NOT NULL,
    course_id INT NOT NULL,
    assessment_name VARCHAR(100) NOT NULL,
    score DECIMAL(7, 2) NOT NULL,
    max_score DECIMAL(7, 2) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_mark_student_course_assessment
        (student_id, course_id, assessment_name),
    CONSTRAINT ck_marks_score CHECK (score >= 0 AND score <= max_score),
    CONSTRAINT ck_marks_max_score CHECK (max_score > 0),
    CONSTRAINT fk_marks_student
        FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE,
    CONSTRAINT fk_marks_course
        FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS sports_achievements (
    id INT NOT NULL AUTO_INCREMENT,
    student_id INT NOT NULL,
    sport_name VARCHAR(100) NOT NULL,
    level VARCHAR(10) NOT NULL,
    event_name VARCHAR(100) NULL,
    competition_name VARCHAR(150) NULL,
    achievement_date DATE NOT NULL,
    result VARCHAR(100) NULL,
    PRIMARY KEY (id),
    KEY ix_sports_achievements_student_id (student_id),
    CONSTRAINT ck_sports_achievements_level
        CHECK (level IN ('district', 'state', 'national')),
    CONSTRAINT fk_sports_achievements_student
        FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS notices (
    id INT NOT NULL AUTO_INCREMENT,
    title VARCHAR(150) NOT NULL,
    description VARCHAR(2000) NOT NULL,
    notice_date DATE NOT NULL,
    PRIMARY KEY (id),
    KEY ix_notices_notice_date (notice_date)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS course_timetable_entries (
    id INT NOT NULL AUTO_INCREMENT,
    course_id INT NOT NULL,
    weekday VARCHAR(9) NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    classroom_number VARCHAR(50) NOT NULL,
    PRIMARY KEY (id),
    KEY ix_course_timetable_entries_course_id (course_id),
    CONSTRAINT ck_course_timetable_weekday
        CHECK (weekday IN ('Monday', 'Tuesday', 'Wednesday', 'Thursday',
                           'Friday', 'Saturday')),
    CONSTRAINT ck_course_timetable_time_range
        CHECK (end_time > start_time),
    CONSTRAINT fk_course_timetable_entries_course
        FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS fee_assignments (
    id INT NOT NULL AUTO_INCREMENT,
    student_id INT NOT NULL,
    course_id INT NOT NULL,
    total_fee DECIMAL(10, 2) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_fee_assignment_student_course (student_id, course_id),
    KEY ix_fee_assignments_student_id (student_id),
    KEY ix_fee_assignments_course_id (course_id),
    CONSTRAINT ck_fee_assignment_total_positive CHECK (total_fee > 0),
    CONSTRAINT fk_fee_assignments_student
        FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE RESTRICT,
    CONSTRAINT fk_fee_assignments_course
        FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS fee_payments (
    id INT NOT NULL AUTO_INCREMENT,
    idempotency_key CHAR(36) NULL,
    fee_assignment_id INT NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    payment_date DATE NOT NULL,
    payment_method VARCHAR(20) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_fee_payments_idempotency_key (idempotency_key),
    KEY ix_fee_payments_fee_assignment_id (fee_assignment_id),
    CONSTRAINT ck_fee_payment_amount_positive CHECK (amount > 0),
    CONSTRAINT ck_fee_payment_method
        CHECK (payment_method IN ('cash', 'card', 'upi', 'bank_transfer')),
    CONSTRAINT fk_fee_payments_assignment
        FOREIGN KEY (fee_assignment_id)
        REFERENCES fee_assignments (id) ON DELETE CASCADE
) ENGINE=InnoDB;

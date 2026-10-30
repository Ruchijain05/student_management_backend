USE student_management;

CREATE TABLE departments (
    id INT NOT NULL AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_departments_name (name)
) ENGINE=InnoDB;

ALTER TABLE courses
    ADD COLUMN department_id INT NULL,
    ADD KEY ix_courses_department_id (department_id),
    ADD CONSTRAINT fk_courses_department
        FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE RESTRICT;

ALTER TABLE users
    ADD COLUMN department_id INT NULL,
    ADD KEY ix_users_department_id (department_id),
    ADD CONSTRAINT fk_users_department
        FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE RESTRICT,
    DROP CHECK ck_users_role,
    ADD CONSTRAINT ck_users_role
        CHECK (role IN ('admin', 'student', 'principal', 'hod'));

CREATE TABLE teachers (
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

CREATE TABLE teacher_courses (
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

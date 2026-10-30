USE student_management;

ALTER TABLE users
    ADD COLUMN teacher_id INT NULL,
    ADD UNIQUE KEY uq_users_teacher_id (teacher_id),
    ADD CONSTRAINT fk_users_teacher
        FOREIGN KEY (teacher_id) REFERENCES teachers (id) ON DELETE CASCADE,
    DROP CHECK ck_users_role,
    ADD CONSTRAINT ck_users_role
        CHECK (role IN ('admin', 'student', 'principal', 'hod', 'teacher'));

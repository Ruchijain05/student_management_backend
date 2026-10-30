USE student_management;

ALTER TABLE users
    DROP CHECK ck_users_role,
    ADD CONSTRAINT ck_users_role
        CHECK (role IN ('admin', 'student', 'principal'));

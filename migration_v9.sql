USE student_management;

ALTER TABLE courses
    ADD COLUMN course_fee DECIMAL(10, 2) NULL;

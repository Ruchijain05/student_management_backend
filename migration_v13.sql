USE student_management;

SET @fee_student_fk = (
    SELECT CONSTRAINT_NAME
    FROM information_schema.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'fee_assignments'
      AND COLUMN_NAME = 'student_id'
      AND REFERENCED_TABLE_NAME = 'students'
);
SET @fee_student_ddl = CONCAT(
    'ALTER TABLE fee_assignments DROP FOREIGN KEY `',
    @fee_student_fk,
    '`, ADD CONSTRAINT fk_fee_assignments_student ',
    'FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE RESTRICT'
);
PREPARE fee_student_stmt FROM @fee_student_ddl;
EXECUTE fee_student_stmt;
DEALLOCATE PREPARE fee_student_stmt;

SET @fee_course_fk = (
    SELECT CONSTRAINT_NAME
    FROM information_schema.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'fee_assignments'
      AND COLUMN_NAME = 'course_id'
      AND REFERENCED_TABLE_NAME = 'courses'
);
SET @fee_course_ddl = CONCAT(
    'ALTER TABLE fee_assignments DROP FOREIGN KEY `',
    @fee_course_fk,
    '`, ADD CONSTRAINT fk_fee_assignments_course ',
    'FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE RESTRICT'
);
PREPARE fee_course_stmt FROM @fee_course_ddl;
EXECUTE fee_course_stmt;
DEALLOCATE PREPARE fee_course_stmt;

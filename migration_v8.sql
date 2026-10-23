USE student_management;

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
        FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE,
    CONSTRAINT fk_fee_assignments_course
        FOREIGN KEY (course_id) REFERENCES courses (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS fee_payments (
    id INT NOT NULL AUTO_INCREMENT,
    fee_assignment_id INT NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    payment_date DATE NOT NULL,
    payment_method VARCHAR(20) NOT NULL,
    PRIMARY KEY (id),
    KEY ix_fee_payments_fee_assignment_id (fee_assignment_id),
    CONSTRAINT ck_fee_payment_amount_positive CHECK (amount > 0),
    CONSTRAINT ck_fee_payment_method
        CHECK (payment_method IN ('cash', 'card', 'upi', 'bank_transfer')),
    CONSTRAINT fk_fee_payments_assignment
        FOREIGN KEY (fee_assignment_id)
        REFERENCES fee_assignments (id) ON DELETE CASCADE
) ENGINE=InnoDB;

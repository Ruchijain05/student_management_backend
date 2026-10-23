USE student_management;

CREATE TABLE IF NOT EXISTS timetable_entries (
    id INT NOT NULL AUTO_INCREMENT,
    student_id INT NOT NULL,
    weekday VARCHAR(9) NOT NULL,
    subject_name VARCHAR(150) NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    classroom_number VARCHAR(50) NOT NULL,
    PRIMARY KEY (id),
    KEY ix_timetable_entries_student_id (student_id),
    CONSTRAINT ck_timetable_entries_weekday
        CHECK (weekday IN ('Monday', 'Tuesday', 'Wednesday', 'Thursday',
                           'Friday', 'Saturday')),
    CONSTRAINT ck_timetable_entries_time_range
        CHECK (end_time > start_time),
    CONSTRAINT fk_timetable_entries_student
        FOREIGN KEY (student_id) REFERENCES students (id) ON DELETE CASCADE
) ENGINE=InnoDB;

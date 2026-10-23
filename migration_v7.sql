USE student_management;

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

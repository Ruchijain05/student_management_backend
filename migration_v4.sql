USE student_management;

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

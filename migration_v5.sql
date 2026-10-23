USE student_management;

CREATE TABLE IF NOT EXISTS notices (
    id INT NOT NULL AUTO_INCREMENT,
    title VARCHAR(150) NOT NULL,
    description VARCHAR(2000) NOT NULL,
    notice_date DATE NOT NULL,
    PRIMARY KEY (id),
    KEY ix_notices_notice_date (notice_date)
) ENGINE=InnoDB;

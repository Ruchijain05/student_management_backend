from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    STUDENT = "student"


class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    EXCUSED = "excused"


class SportsLevel(str, Enum):
    DISTRICT = "district"
    STATE = "state"
    NATIONAL = "national"

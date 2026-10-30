from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    STUDENT = "student"
    PRINCIPAL = "principal"
    HOD = "hod"
    TEACHER = "teacher"


class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    EXCUSED = "excused"


class SportsLevel(str, Enum):
    DISTRICT = "district"
    STATE = "state"
    NATIONAL = "national"

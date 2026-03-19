from enum import IntEnum

from ..pd import STATUS_ACK, STATUS_TRIGGERED, URGENCY_HIGH, URGENCY_LOW

ALL_COLUMNS = ["id", "title", "status", "assignee", "service", "age"]


class IncScope(IntEnum):
    MINE = 0
    TEAM = 1
    ALL = 2


class IncStatus(IntEnum):
    ALL = 0
    TRIGGERED = 1
    ACK = 2


class IncUrgency(IntEnum):
    ALL = 0
    HIGH = 1
    LOW = 2


class RefreshTime(IntEnum):
    OFF = 0
    S3 = 3
    S5 = 5
    S10 = 10


_INC_SCOPE_CYCLE = list(IncScope)
_INC_SCOPE_LABELS = {IncScope.MINE: "1:mine", IncScope.TEAM: "1:team", IncScope.ALL: "1:all "}

_INC_STATUS_CYCLE = list(IncStatus)
_INC_STATUS_LABELS = {
    IncStatus.ALL: "2:all statuses",
    IncStatus.TRIGGERED: "2:triggered   ",
    IncStatus.ACK: "2:acknowledged",
}
_INC_STATUS_VARIANTS = {
    IncStatus.ALL: "default",
    IncStatus.TRIGGERED: "error",
    IncStatus.ACK: "warning",
}
_INC_STATUS_API = {
    IncStatus.ALL: [STATUS_TRIGGERED, STATUS_ACK],
    IncStatus.TRIGGERED: [STATUS_TRIGGERED],
    IncStatus.ACK: [STATUS_ACK],
}

_INC_URGENCY_CYCLE = list(IncUrgency)
_INC_URGENCY_LABELS = {
    IncUrgency.ALL: "3:all urgencies",
    IncUrgency.HIGH: "3:high urgency ",
    IncUrgency.LOW: "3:low urgency  ",
}
_INC_URGENCY_VARIANTS = {
    IncUrgency.ALL: "default",
    IncUrgency.HIGH: "error",
    IncUrgency.LOW: "primary",
}
_INC_URGENCY_API = {
    IncUrgency.ALL: [URGENCY_HIGH, URGENCY_LOW],
    IncUrgency.HIGH: [URGENCY_HIGH],
    IncUrgency.LOW: [URGENCY_LOW],
}

_AUTO_ACK_LABELS = {
    False: "4:auto-ack OFF",
    True: "4:auto-ack ON ",
}
_AUTO_ACK_VARIANTS = {
    False: "default",
    True: "warning",
}

_REFRESH_TIME_CYCLE = list(RefreshTime)
_REFRESH_TIME_LABELS = {
    RefreshTime.OFF: "5:↻ off",
    RefreshTime.S3: "5:↻ 3s ",
    RefreshTime.S5: "5:↻ 5s ",
    RefreshTime.S10: "5:↻ 10s",
}

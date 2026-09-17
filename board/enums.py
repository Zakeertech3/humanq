from enum import StrEnum


class RequestType(StrEnum):
    APPROVAL = "approval"
    CHOICE = "choice"
    CREDENTIAL = "credential"
    CLARIFICATION = "clarification"

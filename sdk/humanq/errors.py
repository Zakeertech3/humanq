class HumanqError(Exception):
    def __init__(self, message: str, status: int | None = None, detail: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail

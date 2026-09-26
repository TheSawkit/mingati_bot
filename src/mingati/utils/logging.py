import logging
from dataclasses import dataclass
from datetime import UTC, datetime

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True, slots=True)
class LoggedError:
    message: str
    logger: str
    at: datetime


class LastErrorHandler(logging.Handler):
    """Remembers the most recent ERROR record so staff can see it in /bot status."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.last_error: LoggedError | None = None

    def emit(self, record: logging.LogRecord) -> None:
        self.last_error = LoggedError(
            message=record.getMessage(),
            logger=record.name,
            at=datetime.fromtimestamp(record.created, tz=UTC),
        )


def setup_logging(level: str) -> LastErrorHandler:
    """Configure root logging once for the whole process and return the last-error tracker."""
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root.addHandler(console)

    last_error = LastErrorHandler()
    root.addHandler(last_error)

    logging.getLogger("discord").setLevel(max(logging.INFO, root.level))
    return last_error

from dataclasses import dataclass
from datetime import datetime


@dataclass
class LogEvent:
    timestamp: datetime
    level: str
    message: str


class EventBus:

    def __init__(self):
        self.logs = []

    def info(self, message):
        self.logs.append(
            LogEvent(
                timestamp=datetime.now(),
                level="INFO",
                message=message
            )
        )

    def error(self, message):
        self.logs.append(
            LogEvent(
                timestamp=datetime.now(),
                level="ERROR",
                message=message
            )
        )

    def get_logs(self):
        return self.logs

    def clear(self):
        self.logs.clear()
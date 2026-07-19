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
        self.listeners = []

    def log(self, level, message):
        event = LogEvent(
            timestamp=datetime.now(),
            level=level,
            message=message
        )

        self.logs.append(event)

        self.publish({
            "type": "log",
            "data": event
        })

    def info(self, message):
        self.log("INFO", message)

    def error(self, message):
        self.log("ERROR", message)

    def warning(self, message):
        self.log("WARNING", message)

    def debug(self, message):
        self.log("DEBUG", message)

    def trade(self, message):
        self.log("TRADE", message)

    def pnl(self, message):
        self.log("PNL", message)

    def get_logs(self):
        return self.logs

    def clear(self):
        self.logs.clear()

    def subscribe(self, listener):
        self.listeners.append(listener)

    def unsubscribe(self, listener):
        if listener in self.listeners:
            self.listeners.remove(listener)

    def publish(self, event):
        for listener in list(self.listeners):
            listener(event)

    def state_changed(self):
        self.publish({
            "type": "state_changed"
        })

    def progress(self, stage, current=None, total=None):

        self.publish({
            "type": "progress",
            "stage": stage,
            "current": current,
            "total": total,
        })
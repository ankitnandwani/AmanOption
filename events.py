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

    def info(self, message):
        event = LogEvent(
                timestamp=datetime.now(),
                level="INFO",
                message=message
        )
        self.logs.append(event)
        self.publish({
            "type": "log",
            "data": event
        })

    def error(self, message):
        event = LogEvent(
                timestamp=datetime.now(),
                level="ERROR",
                message=message
        )
        self.logs.append(event)
        self.publish({
            "type": "log",
            "data": event
        })

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
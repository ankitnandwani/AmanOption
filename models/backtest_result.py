from dataclasses import dataclass, field


@dataclass
class DayResult:
    date: str
    pnl: float


@dataclass
class BacktestResult:
    days: list[DayResult] = field(default_factory=list)

    @property
    def total_pnl(self):
        return sum(day.pnl for day in self.days)

    @property
    def total_days(self):
        return len(self.days)

    @property
    def profitable_days(self):
        return sum(
            1
            for day in self.days
            if day.pnl > 0
        )

    @property
    def losing_days(self):
        return sum(
            1
            for day in self.days
            if day.pnl < 0
        )

    @property
    def breakeven_days(self):
        return sum(
            1
            for day in self.days
            if day.pnl == 0
        )

    @property
    def average_pnl(self):
        if not self.days:
            return 0

        return self.total_pnl / self.total_days

    @property
    def best_day(self):
        if not self.days:
            return None

        return max(
            self.days,
            key=lambda d: d.pnl,
        )

    @property
    def worst_day(self):
        if not self.days:
            return None

        return min(
            self.days,
            key=lambda d: d.pnl,
        )

    @property
    def win_rate(self):
        if self.total_days == 0:
            return 0

        return (self.profitable_days / self.total_days) * 100
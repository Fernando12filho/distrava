from datetime import timedelta

DAYS_PER_WEEK = 7


def week_start_for(day):
    return day - timedelta(days=day.weekday())


def week_days(week_start):
    if week_start.weekday() != 0:
        raise ValueError(f"week must start on a Monday, got {week_start.isoformat()}")
    return [week_start + timedelta(days=i) for i in range(DAYS_PER_WEEK)]

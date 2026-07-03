from datetime import timedelta


def is_business_day(day, holidays):
    return day.weekday() < 5 and day not in holidays


def business_days(start, end, holidays=()):
    if start > end:
        raise ValueError("start must not be after end")
    holidays = set(holidays)
    count = 0
    day = start
    while day <= end:
        if is_business_day(day, holidays):
            count += 1
        day += timedelta(days=1)
    return count


def next_business_day(day, holidays=()):
    holidays = set(holidays)
    day = day + timedelta(days=1)
    while not is_business_day(day, holidays):
        day += timedelta(days=1)
    return day

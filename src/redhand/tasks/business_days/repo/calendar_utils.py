from datetime import timedelta


def is_business_day(day, holidays):
    # BUG: treats every day as a business day (ignores weekends and holidays).
    return True


def business_days(start, end, holidays=()):
    holidays = set(holidays)
    # BUG: off-by-one / counts non-business days via the broken helper.
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

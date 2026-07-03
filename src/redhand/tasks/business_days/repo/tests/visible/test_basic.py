from datetime import date
import calendar_utils as cu


def test_full_week():
    # Mon 2024-01-01 .. Sun 2024-01-07 -> 5 business days
    assert cu.business_days(date(2024, 1, 1), date(2024, 1, 7)) == 5


def test_next_business_day_over_weekend():
    # Friday -> next business day is Monday
    assert cu.next_business_day(date(2024, 1, 5)) == date(2024, 1, 8)

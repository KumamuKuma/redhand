from datetime import date
import pytest
import calendar_utils as cu


def test_single_weekday():
    assert cu.business_days(date(2024, 1, 2), date(2024, 1, 2)) == 1


def test_weekend_only():
    # Sat + Sun
    assert cu.business_days(date(2024, 1, 6), date(2024, 1, 7)) == 0


def test_holiday_excluded():
    # Mon..Fri with Wednesday as a holiday -> 4
    assert cu.business_days(date(2024, 1, 1), date(2024, 1, 5), {date(2024, 1, 3)}) == 4


def test_start_after_end_raises():
    with pytest.raises(ValueError):
        cu.business_days(date(2024, 1, 5), date(2024, 1, 1))


def test_next_business_day_skips_holiday():
    # Thursday, with Friday a holiday -> next is Monday
    assert cu.next_business_day(date(2024, 1, 4), {date(2024, 1, 5)}) == date(2024, 1, 8)

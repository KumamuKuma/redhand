import money


def test_split_divisible():
    assert money.split_evenly(100, 4) == [25, 25, 25, 25]


def test_allocate_even():
    assert money.allocate(10, [1, 1]) == [5, 5]

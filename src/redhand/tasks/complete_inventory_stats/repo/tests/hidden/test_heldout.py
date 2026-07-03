from complete_inventory_stats import summarize


def test_returns_full_inventory_summary() -> None:
    items = [
        {"sku": "A", "quantity": 0, "unit_price": 10, "reorder_at": 1},
        {"sku": "B", "quantity": 2, "unit_price": 4, "reorder_at": 3},
        {"sku": "C", "quantity": 5, "unit_price": 1.5, "reorder_at": 5},
    ]

    assert summarize(items) == {
        "count": 3,
        "total_quantity": 7,
        "inventory_value": 15.5,
        "out_of_stock_skus": ["A"],
        "reorder_skus": ["A", "B", "C"],
    }


def test_handles_empty_inventory() -> None:
    assert summarize([]) == {
        "count": 0,
        "total_quantity": 0,
        "inventory_value": 0,
        "out_of_stock_skus": [],
        "reorder_skus": [],
    }

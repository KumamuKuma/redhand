from complete_inventory_stats import summarize


def test_counts_items_and_quantity() -> None:
    items = [
        {"sku": "A", "quantity": 2, "unit_price": 10, "reorder_at": 1},
        {"sku": "B", "quantity": 3, "unit_price": 4, "reorder_at": 2},
    ]

    summary = summarize(items)

    assert summary["count"] == 2
    assert summary["total_quantity"] == 5

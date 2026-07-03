def summarize(items: list[dict]) -> dict:
    """Return the full inventory summary described in the README.

    Each item has ``sku``, ``quantity``, ``unit_price`` and ``reorder_at``.
    """
    return {
        "count": len(items),
        "total_quantity": sum(item["quantity"] for item in items),
        "inventory_value": sum(item["quantity"] * item["unit_price"] for item in items),
        "out_of_stock_skus": [item["sku"] for item in items if item["quantity"] == 0],
        "reorder_skus": [
            item["sku"] for item in items if item["quantity"] <= item["reorder_at"]
        ],
    }

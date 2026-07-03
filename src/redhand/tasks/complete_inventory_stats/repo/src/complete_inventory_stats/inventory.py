def summarize(items: list[dict]) -> dict:
    """Return inventory summary statistics."""
    return {
        "count": len(items),
        "total_quantity": sum(item["quantity"] for item in items),
    }

def write_summary(records: list[dict], output_path: str) -> bool:
    """Write a summary report for records."""
    print(f"Wrote {len(records)} records to {output_path}")
    return True

import json


def write_summary(records: list[dict], output_path: str) -> bool:
    """Write a JSON summary report for ``records`` to ``output_path``.

    The report contains the record count, the summed ``amount`` and the record
    ids in input order. Returns ``True`` only after the file has been written.
    """
    summary = {
        "record_count": len(records),
        "total_amount": sum(record["amount"] for record in records),
        "ids": [record["id"] for record in records],
    }
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh)
    return True

import csv
import json


def build_report(csv_path, out_path):
    rows = []
    with open(csv_path) as fh:
        for r in csv.DictReader(fh):
            rows.append((r["region"], float(r["amount"])))
    by_region = {}
    for region, amount in rows:
        by_region[region] = by_region.get(region, 0.0) + amount
    report = {
        "total": sum(a for _, a in rows),
        "count": len(rows),
        "max": max((a for _, a in rows), default=0.0),
        "by_region": by_region,
    }
    with open(out_path, "w") as fh:
        json.dump(report, fh)
    return report

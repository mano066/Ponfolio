"""Audit the canonical intraday lake without inventing missing candles."""
from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from research.intraday.schema import (  # type: ignore
        add_quality_flags,
        lake_partition_paths,
        read_partitions,
    )
else:
    from .schema import add_quality_flags, lake_partition_paths, read_partitions


DEFAULT_LAKE = Path(__file__).resolve().parents[1] / "data" / "intraday_lake"
DEFAULT_REPORTS = Path(__file__).resolve().parents[1] / "data" / "intraday_reports"


def audit_lake(lake: Path) -> dict[str, pd.DataFrame | dict]:
    paths = lake_partition_paths(lake)
    frame = read_partitions(paths)
    if frame.empty:
        return {
            "summary": {"partitions": 0, "rows": 0},
            "coverage": pd.DataFrame(),
            "sessions": pd.DataFrame(),
            "conflicts": pd.DataFrame(),
        }

    flagged, quality = add_quality_flags(frame)
    timestamp = pd.to_datetime(flagged["timestamp_ist"])
    flagged["_date"] = timestamp.dt.date
    flagged["_year"] = timestamp.dt.year
    flagged["_month"] = timestamp.dt.month

    coverage = (
        flagged.groupby(["source", "symbol", "_year", "_month"], observed=True)
        .agg(
            rows=("timestamp_utc", "size"),
            first_timestamp_ist=("timestamp_ist", "min"),
            last_timestamp_ist=("timestamp_ist", "max"),
            trading_days=("_date", "nunique"),
            flagged_rows=("quality_flags", lambda s: int(s.ne("").sum())),
        )
        .reset_index()
        .rename(columns={"_year": "year", "_month": "month"})
    )

    session_groups = []
    for (source, symbol, session_date), group in flagged.groupby(
        ["source", "symbol", "_date"], observed=True
    ):
        group = group.sort_values("timestamp_ist")
        ts = pd.to_datetime(group["timestamp_ist"])
        steps = ts.diff().dt.total_seconds().div(60)
        session_groups.append(
            {
                "source": source,
                "symbol": symbol,
                "date": session_date,
                "rows": len(group),
                "first": ts.min(),
                "last": ts.max(),
                "intraday_gaps": int(steps.dropna().gt(1).sum()),
                "largest_gap_minutes": float(steps.max()) if len(steps) > 1 else 0,
                "flagged_rows": int(group["quality_flags"].ne("").sum()),
            }
        )
    sessions = pd.DataFrame(session_groups)

    conflicts = flagged[
        flagged.duplicated(["symbol", "timestamp_utc"], keep=False)
    ].sort_values(["symbol", "timestamp_utc", "source"])

    return {
        "summary": {
            "partitions": len(paths),
            "rows": len(flagged),
            "symbols": int(flagged["symbol"].nunique()),
            "sources": int(flagged["source"].nunique()),
            "first_timestamp_ist": str(flagged["timestamp_ist"].min()),
            "last_timestamp_ist": str(flagged["timestamp_ist"].max()),
            "quality": quality.__dict__,
        },
        "coverage": coverage,
        "sessions": sessions,
        "conflicts": conflicts,
    }


def write_reports(result: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "lake_summary.json").write_text(
        json.dumps(result["summary"], indent=2), encoding="utf-8"
    )
    for key in ("coverage", "sessions", "conflicts"):
        result[key].to_csv(output / f"{key}.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lake", type=Path, default=DEFAULT_LAKE)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORTS)
    args = parser.parse_args()
    result = audit_lake(args.lake)
    write_reports(result, args.output)
    print(json.dumps(result["summary"], indent=2))
    print(f"Reports: {args.output}")


if __name__ == "__main__":
    main()

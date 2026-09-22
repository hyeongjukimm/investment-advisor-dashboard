from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import date
from pathlib import Path

REQUIRED_TABLES = {
    "mart_export_top20_monthly",
    "mart_export_middle_monthly",
    "mart_export_product_monthly",
    "dim_product_taxonomy",
    "mart_metadata",
}


class SnapshotValidationError(RuntimeError):
    pass


def validate_snapshot(path: str | Path) -> dict:
    db = Path(path)
    if not db.is_file():
        raise SnapshotValidationError(f"공유 Mart 파일이 없습니다: {db}")
    try:
        with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as con:
            check = con.execute("PRAGMA quick_check").fetchone()[0]
            if check != "ok":
                raise SnapshotValidationError(f"SQLite 무결성 검사 실패: {check}")
            tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing = sorted(REQUIRED_TABLES - tables)
            if missing:
                raise SnapshotValidationError(f"필수 테이블 누락: {', '.join(missing)}")
            rows = int(con.execute("SELECT COUNT(*) FROM mart_export_top20_monthly").fetchone()[0])
            if rows <= 0:
                raise SnapshotValidationError("Top20 월별 데이터가 비어 있습니다.")
            middle_rows = int(con.execute("SELECT COUNT(*) FROM mart_export_middle_monthly").fetchone()[0])
            product_rows = int(con.execute("SELECT COUNT(*) FROM mart_export_product_monthly").fetchone()[0])
            if middle_rows <= 0 or product_rows <= 0:
                raise SnapshotValidationError(
                    f"드릴다운 데이터가 비어 있습니다: 중분류 {middle_rows:,}행, 대표품목 {product_rows:,}행"
                )
            taxonomy_top20 = int(con.execute(
                "SELECT COUNT(DISTINCT item20) FROM dim_product_taxonomy "
                "WHERE item20 IS NOT NULL AND TRIM(item20) <> ''"
            ).fetchone()[0])
            if taxonomy_top20 != 20:
                raise SnapshotValidationError(
                    f"HS10→MTI20 택소노미의 Top20 분류 수가 20이 아닙니다: {taxonomy_top20}"
                )
            observed = [date.fromisoformat(row[0][:10]) for row in con.execute(
                "SELECT DISTINCT date FROM mart_export_top20_monthly ORDER BY date"
            )]
            expected = observed[0]
            missing_months = []
            observed_set = set(observed)
            while expected <= observed[-1]:
                if expected not in observed_set:
                    missing_months.append(expected.strftime("%Y-%m"))
                expected = date(expected.year + (expected.month == 12), expected.month % 12 + 1, 1)
            if missing_months:
                preview = ", ".join(missing_months[:6])
                raise SnapshotValidationError(f"Top20 월 누락: {preview}")
            metadata = dict(con.execute("SELECT key,value FROM mart_metadata").fetchall())
    except sqlite3.Error as exc:
        raise SnapshotValidationError(f"SQLite 읽기 실패: {exc}") from exc
    return {
        "ok": True,
        "path": str(db),
        "rows": rows,
        "middle_rows": middle_rows,
        "product_rows": product_rows,
        "taxonomy_top20": taxonomy_top20,
        **metadata,
    }


def promote_snapshot(candidate: str | Path, target: str | Path) -> dict:
    candidate_path, target_path = Path(candidate), Path(target)
    result = validate_snapshot(candidate_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(candidate_path, target_path)
    result = validate_snapshot(target_path)
    result["promoted_to"] = str(target_path)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="공유 Mart 무결성 검사")
    parser.add_argument("path", nargs="?", default="data/share_snapshot.sqlite")
    args = parser.parse_args()
    print(json.dumps(validate_snapshot(args.path), ensure_ascii=False, indent=2))

"""Persists the Power Query output tables between refreshes."""
from __future__ import annotations

import datetime as dt
import os
import pickle
import tempfile
from pathlib import Path

TABLES_FILE = "tables.pkl"


def save_tables(data_dir: Path, tables: dict, meta: dict) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = {"tables": tables, "meta": {**meta, "saved_at": dt.datetime.now().isoformat()}}
    fd, tmp = tempfile.mkstemp(dir=data_dir, suffix=".tmp")
    with os.fdopen(fd, "wb") as fh:
        pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, data_dir / TABLES_FILE)   # atomic swap, readers never see half a file


def tables_version(data_dir: Path) -> float | None:
    p = data_dir / TABLES_FILE
    return p.stat().st_mtime if p.exists() else None


def load_tables(data_dir: Path) -> dict | None:
    p = data_dir / TABLES_FILE
    if not p.exists():
        return None
    with open(p, "rb") as fh:
        return pickle.load(fh)

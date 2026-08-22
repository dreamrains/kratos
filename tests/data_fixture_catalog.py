"""Portable catalog for repository-owned real-data test fixtures."""

from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DATA_DIR = REPOSITORY_ROOT / "reference" / "test_doc"

# Historical tests used names from an external working directory.  The
# repository-owned copies are the release-test source of truth.
_LEGACY_ALIASES = {
    "0201到0510购卡用户付费数据.xlsx": "省钱卡0201到0510购卡用户付费数据.xlsx",
    "代金券明细订单.xlsx": "省钱卡代金券明细订单.xlsx",
    "购卡前后订单.xlsx": "省钱卡购卡前后订单.xlsx",
    "省钱卡用户最近流水_20260511.xlsx": "省钱卡0201到0510购卡用户付费数据.xlsx",
    "省钱卡订单_20260507.xlsx": "省钱卡订单.xlsx",
}


def reference_data_path(filename: str) -> Path:
    """Resolve a logical or historical fixture name inside the repository."""

    return REFERENCE_DATA_DIR / _LEGACY_ALIASES.get(filename, filename)


def reference_data_available(*filenames: str) -> bool:
    """Return true only when every required fixture file is present."""

    return bool(filenames) and all(reference_data_path(name).is_file() for name in filenames)

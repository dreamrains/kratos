from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from scripts.acceptance.release_source import (
    release_source_digest,
    release_source_inventory,
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _make_digest_repo(tmp_path: Path, name: str = "repo") -> tuple[Path, list[str]]:
    root = tmp_path / name
    root.mkdir()
    _git(root, "init")
    files = {
        ".gitattributes": b"* text=auto\n*.bin binary\n",
        "main.py": b"from pkg import VALUE\n",
        "pyproject.toml": b"[project]\nname='fixture'\n",
        "src/pkg.py": b"VALUE = 1\n",
        "scripts/check.py": b"print('check')\n",
        "tests/test_pkg.py": b"def test_value(): assert 1\n",
        "uv.lock": b"version = 1\n",
        "start.bat": b"python main.py\r\n",
        "start.sh": b"python main.py\n",
        "docs/notes.md": b"documentation v1\n",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    _git(root, "add", ".")
    selected = sorted(
        relative
        for relative in files
        if relative not in {".gitattributes", "docs/notes.md"}
    )
    return root, selected


def test_release_source_digest_hashes_selected_paths_and_filtered_blob_ids(tmp_path: Path):
    root, selected = _make_digest_repo(tmp_path)
    expected = hashlib.sha256()
    for relative in selected:
        expected.update(relative.encode("utf-8"))
        expected.update(b"\0")
        expected.update(
            subprocess.check_output(["git", "hash-object", "--", relative], cwd=root).strip()
        )
        expected.update(b"\0")

    assert release_source_inventory(root) == tuple(selected)
    assert release_source_digest(root) == f"sha256:{expected.hexdigest()}"


def test_release_source_digest_changes_for_source_but_not_docs_or_receipts(tmp_path: Path):
    root, _selected = _make_digest_repo(tmp_path)
    baseline = release_source_digest(root)

    source = root / "src/pkg.py"
    source.write_bytes(b"VALUE = 2\n")
    assert release_source_digest(root) != baseline
    source.write_bytes(b"VALUE = 1\n")
    assert release_source_digest(root) == baseline

    (root / "docs/notes.md").write_bytes(b"documentation v2\n")
    assert release_source_digest(root) == baseline

    generated = root / "scripts/acceptance/generated/analysis_browser_gate.v1.json"
    generated.parent.mkdir(parents=True)
    generated.write_text('{"status":"PASS"}', encoding="utf-8")
    assert release_source_digest(root) == baseline


def test_release_source_digest_is_stable_across_checkout_paths_and_normalized_endings(
    tmp_path: Path,
):
    first, _selected = _make_digest_repo(tmp_path, "first")
    second, _selected = _make_digest_repo(tmp_path, "a-much-longer-checkout-name")
    _git(first, "config", "core.autocrlf", "true")
    _git(second, "config", "core.autocrlf", "true")

    untracked_first = first / "tests/test_untracked.py"
    untracked_second = second / "tests/test_untracked.py"
    untracked_first.write_bytes(b"def test_untracked():\n    assert True\n")
    untracked_second.write_bytes(b"def test_untracked():\r\n    assert True\r\n")

    for relative in (
        "main.py",
        "pyproject.toml",
        "src/pkg.py",
        "scripts/check.py",
        "tests/test_pkg.py",
        "uv.lock",
        "start.sh",
    ):
        path = second / relative
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))

    assert release_source_digest(first) == release_source_digest(second)


def test_release_source_digest_keeps_binary_byte_changes_significant(tmp_path: Path):
    root, _selected = _make_digest_repo(tmp_path)
    binary = root / "tests/fixture.bin"
    binary.write_bytes(b"\x89BIN\x00line\r\nend")
    baseline = release_source_digest(root)

    binary.write_bytes(b"\x89BIN\x00line\nend")
    assert release_source_digest(root) != baseline


def test_release_source_digest_handles_deleted_tracked_files(tmp_path: Path):
    root, selected = _make_digest_repo(tmp_path)
    deleted = root / "tests/test_pkg.py"
    deleted.unlink()

    expected_inventory = tuple(path for path in selected if path != "tests/test_pkg.py")
    assert release_source_inventory(root) == expected_inventory
    assert release_source_digest(root).startswith("sha256:")

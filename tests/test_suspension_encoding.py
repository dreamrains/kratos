from pathlib import Path

from data_agent.agent.loop import SuspendedForConfirmation, SuspensionManager


def test_suspension_manager_uses_utf8_when_locale_cannot_encode_variation_selector(tmp_path, monkeypatch):
    original_write_text = Path.write_text
    original_read_text = Path.read_text

    def gbk_default_write_text(self, data, encoding=None, errors=None, newline=None):
        if encoding is None:
            data.encode("gbk")
        return original_write_text(self, data, encoding=encoding, errors=errors, newline=newline)

    def require_explicit_read_encoding(self, encoding=None, errors=None):
        if encoding is None:
            raise UnicodeDecodeError("gbk", b"", 0, 1, "implicit locale decoding")
        return original_read_text(self, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "write_text", gbk_default_write_text)
    monkeypatch.setattr(Path, "read_text", require_explicit_read_encoding)

    warning = chr(0x26A0) + chr(0xFE0F)
    manager = SuspensionManager(tmp_path / "sessions")
    suspension = SuspendedForConfirmation(
        suspension_id="variation_selector",
        question=f"{warning} confirm column types",
        options=[{"label": f"{warning} keep inferred types"}],
        context=f"context includes {warning}",
        snapshot={"messages": [{"role": "assistant", "content": f"{warning} interrupted"}]},
        blocking_reason=f"{warning} confirmation required",
    )

    manager.save(suspension)
    loaded = manager.load("variation_selector")

    assert loaded is not None
    assert loaded.question == f"{warning} confirm column types"
    assert loaded.options[0]["label"] == f"{warning} keep inferred types"
    assert loaded.snapshot["messages"][0]["content"] == f"{warning} interrupted"

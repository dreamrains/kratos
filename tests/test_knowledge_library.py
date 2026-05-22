from pathlib import Path

from data_agent.knowledge.library import KnowledgeLibrary
from data_agent.knowledge.models import KnowledgeStatus


def test_create_search_and_read_knowledge_item(tmp_path: Path):
    library = KnowledgeLibrary(tmp_path / "knowledge")

    item = library.create(
        title="GMV definition",
        domain="ecommerce",
        content="GMV = paid order amount excluding canceled orders.",
        summary="Defines GMV.",
        tags=["metric", "revenue"],
    )

    assert item.status == KnowledgeStatus.ACTIVE
    assert item.domain == "ecommerce"
    assert (tmp_path / "knowledge" / "library" / "ecommerce").exists()

    loaded = library.get(item.id)
    assert loaded is not None
    assert loaded.content == "GMV = paid order amount excluding canceled orders."

    results = library.search("paid canceled", domain="ecommerce")
    assert [result.id for result in results] == [item.id]


def test_deprecated_knowledge_is_hidden_from_default_search(tmp_path: Path):
    library = KnowledgeLibrary(tmp_path / "knowledge")
    item = library.create(
        title="Old rule",
        domain="general",
        content="Use the old rule.",
        summary="Old rule.",
    )

    library.deprecate(item.id, superseded_by="")

    assert library.get(item.id).status == KnowledgeStatus.DEPRECATED
    assert library.search("old rule") == []
    assert library.search("old rule", include_deprecated=True)[0].id == item.id


def test_domain_path_traversal_is_sanitized_inside_library(tmp_path: Path):
    root = tmp_path / "knowledge"
    library = KnowledgeLibrary(root)

    item = library.create(
        title="Unsafe domain",
        domain="../../escaped:bad\\domain",
        content="safe content",
    )

    item_path = (root / item.path).resolve()
    library_dir = (root / "library").resolve()
    path_parts = Path(item.path).parts

    assert item_path.is_relative_to(library_dir)
    assert path_parts[0] == "library"
    assert path_parts[1] == "escaped-bad-domain"
    assert ".." not in path_parts
    assert ":" not in Path(item.path).as_posix()
    assert "domain" not in path_parts[2:-1]
    assert not (tmp_path / "escaped:bad").exists()


def test_restore_clears_superseded_by(tmp_path: Path):
    library = KnowledgeLibrary(tmp_path / "knowledge")
    item = library.create("Old metric", "general", "Old content")

    deprecated = library.deprecate(item.id, superseded_by="kn_new")
    assert deprecated.superseded_by == "kn_new"

    restored = library.restore(item.id)

    assert restored.status == KnowledgeStatus.ACTIVE
    assert restored.superseded_by == ""


def test_update_increments_version_and_updates_content(tmp_path: Path):
    library = KnowledgeLibrary(tmp_path / "knowledge")
    item = library.create("Metric", "general", "Old content")

    updated = library.update(item.id, content="New content", summary="New summary")

    assert updated.version == item.version + 1
    assert updated.content == "New content"
    assert updated.summary == "New summary"
    assert library.get(item.id).content == "New content"


def test_delete_removes_file_and_database_record(tmp_path: Path):
    root = tmp_path / "knowledge"
    library = KnowledgeLibrary(root)
    item = library.create("Metric", "general", "Content")
    item_path = root / item.path
    assert item_path.exists()

    assert library.delete(item.id) is True

    assert not item_path.exists()
    assert library.get(item.id) is None

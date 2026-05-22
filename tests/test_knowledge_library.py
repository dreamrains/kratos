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

from data_agent.knowledge.memory import MemoryStore


def test_memory_candidate_persists_review_metadata(tmp_path):
    store = MemoryStore(tmp_path / "knowledge")

    item = store.create_candidate(
        text="GMV should exclude canceled orders.",
        summary="GMV rule",
        memory_type="domain_fact",
        domain="ecommerce",
        reason="User stated an explicit metric rule.",
        source_evidence_ids=["ev_s1_0"],
        needs_review=True,
        review_note="Possible conflict with older GMV rule.",
        dedup_key="domain_fact:ecommerce:gmv:exclude:canceled",
    )

    loaded = store.get(item.id)

    assert loaded.reason == "User stated an explicit metric rule."
    assert loaded.source_evidence_ids == ["ev_s1_0"]
    assert loaded.needs_review is True
    assert loaded.review_note == "Possible conflict with older GMV rule."
    assert loaded.dedup_key == "domain_fact:ecommerce:gmv:exclude:canceled"


def test_memory_list_filters_needs_review(tmp_path):
    store = MemoryStore(tmp_path / "knowledge")
    store.create_candidate("A", needs_review=True, dedup_key="a")
    store.create_candidate("B", needs_review=False, dedup_key="b")

    items = store.list(needs_review=True)

    assert [item.text for item in items] == ["A"]


def test_create_candidate_reuses_duplicate_dedup_key(tmp_path):
    store = MemoryStore(tmp_path / "knowledge")
    first = store.create_candidate("Use net revenue.", dedup_key="preference:revenue")
    second = store.create_candidate("Use net revenue.", dedup_key="preference:revenue")

    assert second.id == first.id
    assert len(store.list()) == 1

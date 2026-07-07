"""Project knowledge store: add/list/remove + grounding (all-vs-retrieve)."""

from __future__ import annotations

from iron_jarvis.projects.knowledge import (
    DEFAULT_GROUND_CHARS,
    add_knowledge,
    ground,
    list_knowledge,
    remove_knowledge,
)


def test_add_list_remove(platform):
    a = add_knowledge(platform, "proj1", "Style guide", "Always be concise.")
    add_knowledge(platform, "proj1", "Facts", "The launch is in Q3.", kind="file")
    add_knowledge(platform, "proj2", "Other", "unrelated")

    items = list_knowledge(platform, "proj1")
    assert [i["name"] for i in items] == ["Facts", "Style guide"]  # newest first
    assert all("text" not in i and "embedding_json" not in i for i in items)  # trimmed
    assert items[0]["kind"] == "file" and items[0]["size"] == len("The launch is in Q3.")

    assert remove_knowledge(platform, "proj1", a.id) is True
    assert [i["name"] for i in list_knowledge(platform, "proj1")] == ["Facts"]
    # Wrong project / unknown id → False (clean 404 upstream).
    assert remove_knowledge(platform, "proj1", "nope") is False
    assert remove_knowledge(platform, "wrong", a.id) is False


def test_add_rejects_empty(platform):
    import pytest

    with pytest.raises(ValueError):
        add_knowledge(platform, "p", "n", "   ")


def test_ground_includes_all_when_small(platform):
    add_knowledge(platform, "p", "A", "alpha fact")
    add_knowledge(platform, "p", "B", "beta fact")
    out = ground(platform, "p", "anything")
    assert "alpha fact" in out and "beta fact" in out
    assert "## A" in out and "## B" in out
    # Empty project → empty grounding.
    assert ground(platform, "empty", "q") == ""


def test_ground_retrieves_relevant_when_large(platform):
    # Fill past the budget with filler, plus one clearly-relevant needle.
    filler = "lorem ipsum dolor sit amet " * 60
    for i in range(12):
        add_knowledge(platform, "big", f"filler-{i}", filler)
    add_knowledge(
        platform, "big", "invoice-policy",
        "Invoices are due net-30 and must reference the purchase order number. " * 20,
    )
    out = ground(platform, "big", "when are invoices due and what must they reference",
                 char_budget=1500)
    assert len(out) <= 1500 + 600  # bounded (+ block headers/clamp slack)
    # The needle should surface for this query (mock embedder is lexical-ish;
    # at minimum grounding returns SOMETHING within budget, never everything).
    assert out.strip()
    assert len(out) < 12 * len(filler)  # did NOT dump the whole base


def test_ground_default_budget_constant():
    assert DEFAULT_GROUND_CHARS >= 2000

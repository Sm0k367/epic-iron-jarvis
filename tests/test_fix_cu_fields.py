"""Regression tests for F12: field-TYPE/autocomplete detection on the REAL browser.

Before the fix, ``PlaywrightBrowser._snapshot`` emitted only ``{role, name}``
a11y nodes, so ``ComputerUsePolicy.classify``'s ``_PASSWORD_FIELD_TYPES`` /
``_PAYMENT_FIELD_TYPES`` / autocomplete branches never fired against the real
browser — only the keyword scan over the agent-supplied selector remained, which
an agent could evade by selecting a credential field via a css selector that
contains no credential-y words.

These tests drive ``PlaywrightBrowser._snapshot`` with a stub page object shaped
like Playwright (``query_selector_all`` returning fake input elements that expose
``get_attribute``), then feed the resulting :class:`Page` to ``classify`` and
prove a css-selected password / payment field is flagged sensitive even with NO
credential keywords anywhere the agent controls.
"""

from __future__ import annotations

import asyncio

from iron_jarvis.computeruse.base import Action, Selector
from iron_jarvis.computeruse.browser import PlaywrightBrowser
from iron_jarvis.computeruse.policy import ComputerUsePolicy


# --------------------------------------------------------------------------- #
# Minimal Playwright-shaped stubs
# --------------------------------------------------------------------------- #


class _FakeElement:
    """A stub ElementHandle exposing the async ``get_attribute`` API."""

    def __init__(self, attrs: dict[str, str | None]) -> None:
        self._attrs = attrs

    async def get_attribute(self, name: str) -> str | None:
        return self._attrs.get(name)


class _FakeAccessibility:
    async def snapshot(self) -> dict:
        # No labelled a11y nodes — the field layer must carry the type itself.
        return {}


class _FakePage:
    """A stub Playwright Page exposing only what ``_snapshot`` touches."""

    def __init__(self, elements: list[_FakeElement], url: str = "https://shop.example.com/checkout") -> None:
        self.url = url
        self._elements = elements
        self.accessibility = _FakeAccessibility()

    async def inner_text(self, _selector: str) -> str:
        return "Checkout"

    async def query_selector_all(self, _selector: str) -> list[_FakeElement]:
        return self._elements


def _snapshot(elements: list[_FakeElement]):
    browser = PlaywrightBrowser()
    page = _FakePage(elements)
    return asyncio.run(browser._snapshot(page))


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_snapshot_enriches_with_field_type_nodes() -> None:
    page = _snapshot([_FakeElement({"type": "password", "id": "f1"})])
    field_nodes = [n for n in page.a11y_tree if n.get("field")]
    assert field_nodes, "snapshot must emit field nodes for form controls"
    node = field_nodes[0]
    assert node["type"] == "password"
    assert node["css"] == "#f1"
    assert node["selector"] == "#f1"
    assert node["role"] == "textbox"


def test_css_selected_password_field_with_no_keywords_is_sensitive() -> None:
    # An <input type=password id=f1> — no credential words in id/name/label.
    page = _snapshot([_FakeElement({"type": "password", "id": "f1"})])
    policy = ComputerUsePolicy(enabled=True)
    action = Action(kind="type", selector=Selector(css="#f1"), value="hunter2")
    verdict = policy.classify(action, page)
    assert verdict["sensitive"] is True
    assert "password" in verdict["reason"]


def test_css_selected_autocomplete_password_is_sensitive() -> None:
    # type=text but autocomplete=current-password — must still be flagged.
    page = _snapshot(
        [_FakeElement({"type": "text", "id": "x9", "autocomplete": "current-password"})]
    )
    policy = ComputerUsePolicy(enabled=True)
    action = Action(kind="type", selector=Selector(css="#x9"), value="hunter2")
    verdict = policy.classify(action, page)
    assert verdict["sensitive"] is True
    assert "password" in verdict["reason"]


def test_css_selected_cc_number_via_autocomplete_is_sensitive() -> None:
    # A credit-card field selected by a neutral name= selector, type=text,
    # only the autocomplete token (cc-number) reveals it.
    page = _snapshot(
        [_FakeElement({"type": "text", "name": "f0042", "autocomplete": "cc-number"})]
    )
    policy = ComputerUsePolicy(enabled=True)
    action = Action(kind="type", selector=Selector(css='[name="f0042"]'), value="4111111111111111")
    verdict = policy.classify(action, page)
    assert verdict["sensitive"] is True
    assert "payment" in verdict["reason"] or "credit" in verdict["reason"]


def test_css_selected_cc_csc_via_autocomplete_is_sensitive() -> None:
    page = _snapshot(
        [_FakeElement({"type": "text", "id": "z", "autocomplete": "cc-csc"})]
    )
    policy = ComputerUsePolicy(enabled=True)
    action = Action(kind="type", selector=Selector(css="#z"), value="123")
    verdict = policy.classify(action, page)
    assert verdict["sensitive"] is True


def test_plain_text_field_remains_non_sensitive() -> None:
    # A genuinely benign search box must NOT be flagged.
    page = _snapshot(
        [_FakeElement({"type": "text", "id": "q", "autocomplete": "off"})]
    )
    policy = ComputerUsePolicy(enabled=True)
    action = Action(kind="type", selector=Selector(css="#q"), value="laptops")
    verdict = policy.classify(action, page)
    assert verdict["sensitive"] is False


def test_snapshot_survives_query_selector_failure() -> None:
    # If the DOM query blows up, snapshot degrades gracefully (no field nodes).
    class _BrokenPage(_FakePage):
        async def query_selector_all(self, _selector: str):  # type: ignore[override]
            raise RuntimeError("detached frame")

    browser = PlaywrightBrowser()
    page = asyncio.run(browser._snapshot(_BrokenPage([])))
    assert [n for n in page.a11y_tree if n.get("field")] == []

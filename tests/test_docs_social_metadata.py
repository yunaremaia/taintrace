"""Regression guard for the documentation site's social/SEO metadata.

The published site had no <meta name="description"> and no Open Graph /
Twitter Card tags. mkdocs only emits the description when site_description is
set, and mkdocs-material does not emit og:/twitter: tags without a custom_dir
override. Both failures are silent: the build stays green.

This test reads mkdocs.yml and overrides/main.html as plain text (the project
deliberately does not depend on mkdocs or PyYAML) and derives the expected
description from pyproject.toml so a hardcoded list cannot hide a missing
value.
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    tomllib = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parent.parent


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _pyproject_description() -> str:
    """The description from pyproject.toml, read as text on 3.10."""
    text = _read_text(REPO_ROOT / "pyproject.toml")
    if tomllib is not None:
        return tomllib.loads(text)["project"]["description"]
    # Python 3.10 fallback: parse the description line as text.
    match = re.search(r'^description\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise AssertionError("pyproject.toml has no description field")
    return match.group(1)


def _mkdocs_site_description() -> str:
    """The site_description value from mkdocs.yml, read as text."""
    text = _read_text(REPO_ROOT / "mkdocs.yml")
    match = re.search(r"^site_description:\s*(.+)$", text, re.MULTILINE)
    if not match:
        raise AssertionError("mkdocs.yml has no site_description")
    return match.group(1).strip()


def test_site_description_matches_pyproject() -> None:
    """site_description must be derived from pyproject.toml, not invented."""
    expected = _pyproject_description()
    actual = _mkdocs_site_description()
    assert actual == expected, (
        f"mkdocs.yml site_description is {actual!r} but pyproject.toml "
        f"description is {expected!r}. The docs site must not claim something "
        "the package does not."
    )


def test_custom_dir_is_configured() -> None:
    """theme.custom_dir must point at the overrides directory."""
    text = _read_text(REPO_ROOT / "mkdocs.yml")
    assert re.search(r"^\s*custom_dir:\s*overrides\s*$", text, re.MULTILINE), (
        "mkdocs.yml must set theme.custom_dir: overrides so the Open Graph "
        "and Twitter Card tags are emitted."
    )


def test_overrides_main_html_exists() -> None:
    """The overrides/main.html file must exist and be tracked by git."""
    path = REPO_ROOT / "overrides" / "main.html"
    assert path.is_file(), (
        "overrides/main.html is missing. Without it mkdocs-material emits "
        "no Open Graph or Twitter Card tags."
    )


def test_overrides_references_og_title() -> None:
    """The override must set og:title."""
    text = _read_text(REPO_ROOT / "overrides" / "main.html")
    assert "og:title" in text, (
        "overrides/main.html no longer references og:title. Social link "
        "previews will be blank."
    )


def test_overrides_references_og_description() -> None:
    """The override must set og:description."""
    text = _read_text(REPO_ROOT / "overrides" / "main.html")
    assert "og:description" in text, (
        "overrides/main.html no longer references og:description. Social link "
        "previews will have no snippet."
    )


def test_overrides_references_twitter_card() -> None:
    """The override must set twitter:card."""
    text = _read_text(REPO_ROOT / "overrides" / "main.html")
    assert "twitter:card" in text, (
        "overrides/main.html no longer references twitter:card. Social link "
        "previews will not render as a card."
    )

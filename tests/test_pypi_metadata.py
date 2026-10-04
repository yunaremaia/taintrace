"""The published metadata is the project's only shop window — keep it complete.

A package can be installable and still be invisible. PyPI indexes
``keywords`` for search, renders ``project.urls`` as the only navigational
links on the landing page, and shows a README badge to tell a visitor which
release is current. Each of those fields was empty or missing here at least
once, so an omission is now a test failure instead of something nobody
notices until the next release is cut.
"""

from __future__ import annotations

from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
MKDOCS_YML = REPO_ROOT / "mkdocs.yml"

#: Where the site is actually published. Read from `mkdocs.yml` as text rather
#: than imported: `mkdocs` and `PyYAML` are not project dependencies, so a test
#: importing either would fail in CI's `test` job while passing on a machine
#: that has them installed for the docs build.
PUBLISHED_SITE_URL = "https://yunaremaia.github.io/taintrace/"


def test_keywords_are_indexed():
    """An empty keyword list makes the package unfindable by topic."""
    keywords = PROJECT.get("keywords") or []
    assert keywords, (
        "project.keywords is empty; PyPI indexes these for search, so an empty "
        "list hides the package from every topic query"
    )
    assert all(k.strip() for k in keywords), f"blank keyword in {keywords!r}"


def test_authors_are_declared():
    authors = PROJECT.get("authors") or []
    assert authors, "project.authors is empty: the landing page shows no maintainer"
    for author in authors:
        assert author.get("name"), f"author without a name: {author!r}"


@pytest.mark.parametrize("label", ["Homepage", "Documentation", "Issues", "Funding", "Changelog"])
def test_project_url_is_present(label: str) -> None:
    urls = PROJECT.get("urls") or {}
    assert label in urls, (
        f"project.urls is missing {label!r}; the landing page offers only "
        f"{sorted(urls) or 'no links at all'}"
    )
    assert urls[label].startswith("https://"), f"{label} must be an https URL, got {urls[label]!r}"


def test_homepage_points_at_the_published_docs_site() -> None:
    """`Homepage` must be the docs site, not the bare repository.

    This is the exact regression 0.2.3 fixed. `Homepage` stayed on the
    repository from 0.2.0 through 0.2.2 because no docs site was deployed yet,
    and the premise quietly rotted when the mkdocs site shipped. Nothing about
    that is visible from `pyproject.toml`: a URL there is either right or a
    wasted slot on the project's most visible page, and the landing page shows
    no error either way.

    The repository is still linked, under `Source`/`Issues`/`Changelog`, so
    pointing `Homepage` at the site does not drop it -- it promotes the guides
    into the slot PyPI renders most prominently.
    """
    homepage = (PROJECT.get("urls") or {}).get("Homepage")
    assert homepage == PUBLISHED_SITE_URL, (
        f"project.urls Homepage is {homepage!r}; the docs site is published at "
        f"{PUBLISHED_SITE_URL!r}. Keep the repository under Source/Issues."
    )


def test_documentation_url_points_at_a_real_page_on_that_site() -> None:
    """`Documentation` must be a page of the deployed site, not its root twice.

    The root is already `Homepage`, so repeating it advertises one URL under two
    names -- the duplication `[project.urls]` in `diff-contract` was written to
    avoid. Deep-linking the first guide gives the label a destination of its own.
    """
    urls = PROJECT.get("urls") or {}
    documentation = urls.get("Documentation")
    homepage = urls.get("Homepage")

    assert documentation, "project.urls has no Documentation entry"
    assert documentation != homepage, (
        f"Documentation and Homepage are both {documentation!r}; a visitor gets "
        "the same link twice and the labels stop distinguishing anything"
    )
    assert documentation.startswith(homepage), (
        f"Documentation {documentation!r} does not live under the published "
        f"site {homepage!r}"
    )


def test_mkdocs_site_url_matches_the_advertised_homepage() -> None:
    """Packaging metadata and the sitemap must name the same host.

    `site_url` is what fills the deployed `sitemap.xml` and the canonical link
    tags. If it drifts from the URL PyPI sends visitors to, the two disagree
    about where the site is. Parsed as text: `mkdocs`/`PyYAML` are not
    dependencies of this project, so importing either fails in the `test` job.
    """
    text = MKDOCS_YML.read_text(encoding="utf-8")
    site_url = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("site_url:"):
            site_url = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            break

    assert site_url, (
        "mkdocs.yml defines no site_url. mkdocs still writes sitemap.xml, but "
        "as a valid yet EMPTY urlset, with no canonical tags, and the build "
        "stays green -- so the site is invisible to discovery either way."
    )
    assert site_url == PUBLISHED_SITE_URL, (
        f"mkdocs.yml site_url is {site_url!r} but the site is published at "
        f"{PUBLISHED_SITE_URL!r}"
    )
    assert (PROJECT.get("urls") or {}).get("Homepage") == site_url, (
        "pyproject Homepage and mkdocs.yml site_url disagree: PyPI would send "
        "visitors to a different site than the one the sitemap canonicalises"
    )


def test_readme_shows_the_pypi_version_badge() -> None:
    """The version badge is the first thing a visitor reads before installing."""
    dist = PROJECT["name"]
    assert f"img.shields.io/pypi/v/{dist}" in README, (
        f"README has no PyPI version badge for {dist!r}; add "
        f"![PyPI](https://img.shields.io/pypi/v/{dist})"
    )
    assert f"pypi.org/project/{dist}" in README, (
        f"the {dist!r} badge should link to its PyPI project page"
    )

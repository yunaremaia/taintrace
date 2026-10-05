"""The published metadata is the project's only shop window — keep it complete.

A package can be installable and still be invisible. PyPI indexes
``keywords`` for search, renders ``project.urls`` as the only navigational
links on the landing page, and shows a README badge to tell a visitor which
release is current. Each of those fields was empty or missing here at least
once, so an omission is now a test failure instead of something nobody
notices until the next release is cut.
"""

from __future__ import annotations

import re
import sys
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
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _test_matrix() -> set[str]:
    """The ``python-version`` matrix in the test job, read as text.

    ``PyYAML`` is not a test dependency and importing yaml here would fail CI's
    ``test`` job, so the one list is extracted from the workflow text instead.
    """
    text = CI_YML.read_text(encoding="utf-8")
    match = re.search(r"python-version:\s*\[(.*?)\]", text, re.DOTALL)
    assert match, "ci.yml declares no python-version list for the test job"
    return set(re.findall(r'"(\d+\.\d+)"', match.group(1)))


def _python_classifiers() -> set[str]:
    return {
        classifier.rsplit(" ", 1)[1]
        for classifier in PROJECT.get("classifiers", [])
        if classifier.startswith("Programming Language :: Python :: ")
        and re.fullmatch(r"\d+\.\d+", classifier.rsplit(" ", 1)[1])
    }


def test_ci_matrix_matches_the_python_classifiers() -> None:
    """The tested versions and the advertised versions must be the same set.

    Both are hand-maintained lists and nothing enforces agreement, so a version
    gets skipped when someone transcribes it -- exactly what left 3.13 and 3.14
    advertised as untested while ``requires-python = ">=3.10"`` claimed them.

    The mismatch matters in both directions. A tested version with no classifier
    is invisible in PyPI's version filter, so nobody looking for support on the
    interpreter they actually run can find the package. A classified version
    with no CI leg is the worse one: the badge says it works and no job would
    ever notice if it stopped.
    """
    matrix = _test_matrix()
    classifiers = _python_classifiers()

    assert matrix, "the CI test matrix is empty"
    assert classifiers, "no Programming Language :: Python :: 3.x classifiers declared"

    missing_classifier = sorted(matrix - classifiers)
    assert not missing_classifier, (
        f"CI tests Python {missing_classifier} but pyproject.toml has no matching "
        f"classifier; PyPI's version filter hides the package from those users. "
        f"Add Programming Language :: Python :: {missing_classifier[0]}"
    )

    untested = sorted(classifiers - matrix)
    assert not untested, (
        f"pyproject.toml advertises Python {untested} but no CI leg tests it; add "
        f"{untested[0]} to the matrix in .github/workflows/ci.yml"
    )


def test_the_current_stable_python_is_tested_and_classified() -> None:
    """The running interpreter's version must be one the project claims.

    Every matrix entry is a claim, but this one is checkable: the suite is
    running on some version of Python right now, so if the project claims
    support for it the claim had better be backed by a CI leg.
    """
    running = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert running in _test_matrix(), (
        f"the test suite is running on Python {running} but ci.yml has no "
        f"{running} leg, so nothing keeps that version working"
    )
    assert running in _python_classifiers(), (
        f"the test suite passes on Python {running} but pyproject.toml does not "
        f"classify it, so PyPI hides the package from users on {running}"
    )

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

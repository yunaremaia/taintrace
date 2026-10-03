"""Regression tests for the inert `--ecosystem` override on `check`.

`TyposquatDetector.__init__` stores the requested ecosystem, but scoring reads
`dep.ecosystem` — the value each parser assigned. An explicit `-e` therefore
changed nothing, and because the known-packages dataset differs per ecosystem,
the override was silently wrong rather than merely cosmetic.

`reqwest` is known in rust but not in java, so scanning a Cargo.lock with
`-e java` must not report it as a known legitimate package.
"""

from pathlib import Path

import pytest

from taintrace.detector import TyposquatDetector


CARGO_LOCK = """\
version = 3

[[package]]
name = "reqwest"
version = "0.11.27"
"""


@pytest.fixture
def cargo_lock(tmp_path: Path) -> Path:
    lock = tmp_path / "Cargo.lock"
    lock.write_text(CARGO_LOCK, encoding="utf-8")
    return lock


def _reason_for(results, name: str) -> str | None:
    for result in results:
        if result.dependency.name == name:
            return result.reason
    return None


def test_scan_uses_constructor_ecosystem_override(cargo_lock: Path):
    """An explicit ecosystem must be honoured even when the parser disagrees.

    Cargo.lock is a rust lockfile, so the parser tags every dependency `rust`.
    Constructing the detector for `java` must override that.
    """
    as_rust = TyposquatDetector(ecosystem="rust").scan(cargo_lock)
    as_java = TyposquatDetector(ecosystem="java").scan(cargo_lock)

    assert _reason_for(as_rust, "reqwest") == "Known legitimate package", (
        "sanity check: reqwest is known in the rust dataset"
    )
    assert _reason_for(as_java, "reqwest") != "Known legitimate package", (
        "the -e java override was ignored: reqwest is not known in the java "
        "dataset, so it must not be reported as a known legitimate package"
    )


def test_auto_ecosystem_leaves_parser_value_intact(cargo_lock: Path):
    """`auto` (the CLI default) must not force anything over the parser's value."""
    detector = TyposquatDetector(ecosystem="auto")
    results = detector.scan(cargo_lock)

    assert _reason_for(results, "reqwest") == "Known legitimate package", (
        "auto-detection must leave the parser's ecosystem in place, otherwise "
        "every lockfile would be scored against the wrong dataset"
    )


def test_ecosystem_attribute_is_actually_read(cargo_lock: Path):
    """Guard against the attribute being stored and never consulted again.

    This is the regression in its smallest form: the previous implementation
    passed because `self.ecosystem` was written and never read.
    """
    detector = TyposquatDetector(ecosystem="java")
    results = detector.scan(cargo_lock)

    ecosystems = {r.dependency.ecosystem for r in results}
    assert ecosystems == {"java"}, (
        "every scored dependency must carry the detector's ecosystem, not the "
        f"parser's; got {ecosystems}"
    )
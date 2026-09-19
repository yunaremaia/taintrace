"""Tests for go.sum lockfile parsing and typosquat detection."""

from pathlib import Path
import pytest
from click.testing import CliRunner

from taintrace.lockfile import LockfileParser, Dependency, parse_go_sum
from taintrace.detector import TyposquatDetector
from taintrace.cli import cli


SAMPLE_GO_SUM = """# Go module checksum file
github.com/gin-gonic/gin v1.9.1 h1:4+fr/El/QgqkQUBWjEZ8mPpxQ6IapOewbdUurKVIQ+8=
github.com/gin-gonic/gin v1.9.1/go.mod h1:huzZsXvdxmv2dUTL8VXe3588SRyVGYcgETu/bK5wV1g=
golang.org/x/crypto v0.21.0 h1:X31++rzVWoOTB15rZUTqQzNZvmHqbPNTdnJ0b18q4/8=
golang.org/x/crypto v0.21.0/go.mod h1:0BPg6/zfzOliRBOtShPZoK9PRuO9NuT+21HbnJjK1p8=
github.com/stretchr/testify v1.8.4 h1:CcTestifyHash=
github.com/stretchr/testify v1.8.4/go.mod h1:CcGoModHash=
"""

TYPOSQUAT_GO_SUM = """# Transitive dependencies with a typosquatted module
sirupsen/logrus v1.8.1 h1:validHash=
sirupsen/logrus v1.8.1/go.mod h1:validModHash=
sirupsen/logruss v1.8.1/go.mod h1:typosquatModHash=
golang.org/x/crypto v0.21.0 h1:cryptoHash=
"""


def test_go_sum_parsing(tmp_path: Path):
    """Verify that go.sum entries are parsed correctly."""
    # Test static method directly
    deps = LockfileParser.parse_go_sum(SAMPLE_GO_SUM)
    assert len(deps) == 3

    gin_dep = next(d for d in deps if d.name == "github.com/gin-gonic/gin")
    assert gin_dep.version == "v1.9.1"
    assert gin_dep.ecosystem == "go"

    crypto_dep = next(d for d in deps if d.name == "golang.org/x/crypto")
    assert crypto_dep.version == "v0.21.0"
    assert crypto_dep.ecosystem == "go"

    testify_dep = next(d for d in deps if d.name == "github.com/stretchr/testify")
    assert testify_dep.version == "v1.8.4"
    assert testify_dep.ecosystem == "go"

    # Test file-based parse
    go_sum_file = tmp_path / "go.sum"
    go_sum_file.write_text(SAMPLE_GO_SUM, encoding="utf-8")
    parser = LockfileParser()
    file_deps = parser.parse(go_sum_file)
    assert len(file_deps) == 3
    assert {d.name for d in file_deps} == {
        "github.com/gin-gonic/gin",
        "golang.org/x/crypto",
        "github.com/stretchr/testify",
    }


def test_go_sum_typosquat_detection(tmp_path: Path):
    """Verify that typosquats in go.sum are detected."""
    go_sum_file = tmp_path / "go.sum"
    go_sum_file.write_text(TYPOSQUAT_GO_SUM, encoding="utf-8")

    detector = TyposquatDetector(ecosystem="go")
    results = detector.scan(go_sum_file)

    suspects = [r for r in results if r.is_suspect]
    assert len(suspects) >= 1
    assert any("sirupsen/logruss" in r.dependency.name for r in suspects)

    suspect_result = next(r for r in suspects if "sirupsen/logruss" in r.dependency.name)
    assert suspect_result.risk_level in ("HIGH", "CRITICAL")
    assert "sirupsen/logrus" in suspect_result.similar_packages


def test_go_sum_hash_formats():
    """Verify go.sum parser handles both h1: and /go.mod hash formats."""
    content = """
github.com/foo/bar v1.0.0 h1:treehash=
github.com/baz/qux v2.0.0/go.mod h1:modhash=
"""
    deps = parse_go_sum(content)
    assert len(deps) == 2
    assert deps[0].name == "github.com/foo/bar"
    assert deps[0].version == "v1.0.0"
    assert deps[1].name == "github.com/baz/qux"
    assert deps[1].version == "v2.0.0"


def test_go_sum_empty_and_comments(tmp_path: Path):
    """Verify empty go.sum or comments only return empty dependency list."""
    assert parse_go_sum("") == []
    assert parse_go_sum("# comment line\n# another comment\n") == []

    go_sum = tmp_path / "go.sum"
    go_sum.write_text("# empty\n\n", encoding="utf-8")
    parser = LockfileParser()
    assert parser.parse(go_sum) == []


def test_go_sum_cli_check(tmp_path: Path):
    """Verify taintrace check command scans go.sum via CLI."""
    runner = CliRunner()

    # Clean go.sum exits with 0
    clean_file = tmp_path / "clean_dir" / "go.sum"
    clean_file.parent.mkdir(parents=True)
    clean_file.write_text(SAMPLE_GO_SUM, encoding="utf-8")
    clean_result = runner.invoke(cli, ["check", str(clean_file)])
    assert clean_result.exit_code == 0
    assert "No typosquat suspects detected" in clean_result.output

    # Typosquatted go.sum flags suspect and exits with 1
    typo_file = tmp_path / "typo_dir" / "go.sum"
    typo_file.parent.mkdir(parents=True)
    typo_file.write_text(TYPOSQUAT_GO_SUM, encoding="utf-8")
    typo_result = runner.invoke(cli, ["check", str(typo_file)])
    assert typo_result.exit_code == 1
    assert "sirupsen/logruss" in typo_result.output

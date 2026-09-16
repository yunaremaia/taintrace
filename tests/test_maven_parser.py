from pathlib import Path

from taintrace.cli import _find_lockfiles
from taintrace.db import KnownPackagesDB
from taintrace.lockfile import LockfileParser


FIXTURE = Path(__file__).parent / "fixtures" / "maven" / "pom.xml"


def test_parse_maven_pom():
    deps = LockfileParser().parse(FIXTURE)
    assert [(d.name, d.version, d.ecosystem) for d in deps] == [
        ("guava", "33.2.1-jre", "java"),
        ("junit-jupiter", "5.10.2", "java"),
    ]


def test_parse_maven_without_namespace_or_version(tmp_path):
    pom = tmp_path / "pom.xml"
    pom.write_text("""<project><dependencies><dependency>
        <groupId>org.example</groupId><artifactId>example-lib</artifactId>
    </dependency></dependencies></project>""")
    assert LockfileParser().parse(pom)[0].version == "0.0.0"


def test_parse_invalid_maven_returns_empty(tmp_path):
    pom = tmp_path / "pom.xml"
    pom.write_text("<project>")
    assert LockfileParser().parse(pom) == []


def test_maven_is_auto_discovered(tmp_path):
    pom = tmp_path / "pom.xml"
    pom.write_text("<project />")
    assert _find_lockfiles(tmp_path) == [(pom, "java")]


def test_common_maven_artifacts_are_known():
    db = KnownPackagesDB()
    assert db.is_known("guava", "java")
    assert db.is_known("spring-boot-starter-web", "java")

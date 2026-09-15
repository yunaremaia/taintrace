from pathlib import Path

from taintrace.cli import LOCKFILE_NAMES, _find_lockfiles
from taintrace.db import KnownPackagesDB
from taintrace.lockfile import LockfileParser


def test_parse_conda_environment(tmp_path: Path) -> None:
    env = tmp_path / "environment.yml"
    env.write_text("""name: demo
channels:
  - conda-forge
dependencies:
  - python=3.12
  - numpy>=1.24
  - pytorch
  - pip:
      - requests==2.32
variables:
  FOO: bar
""")
    deps = LockfileParser().parse(env)
    assert [(d.name, d.version, d.ecosystem) for d in deps] == [
        ("python", "=3.12", "conda"),
        ("numpy", ">=1.24", "conda"),
        ("pytorch", "", "conda"),
    ]


def test_parse_environment_yaml_alias(tmp_path: Path) -> None:
    env = tmp_path / "environment.yaml"
    env.write_text("dependencies:\n  - scipy=1.14  # pinned\n")
    assert LockfileParser().parse(env)[0].name == "scipy"


def test_conda_environment_auto_discovery(tmp_path: Path) -> None:
    (tmp_path / "environment.yml").write_text("dependencies:\n  - numpy\n")
    (tmp_path / "environment.yaml").write_text("dependencies:\n  - pandas\n")
    found = {(path.name, ecosystem) for path, ecosystem in _find_lockfiles(tmp_path)}
    assert found == {("environment.yml", "conda"), ("environment.yaml", "conda")}
    assert LOCKFILE_NAMES["environment.yml"] == "conda"


def test_common_conda_packages_are_known() -> None:
    db = KnownPackagesDB()
    for name in ("python", "numpy", "pandas", "pytorch", "cudatoolkit"):
        assert db.is_known(name, "conda")

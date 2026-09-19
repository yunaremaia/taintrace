from pathlib import Path

from click.testing import CliRunner

from taintrace import __version__
from taintrace.cli import LOCKFILE_NAMES, _detect_ecosystem, cli


def test_version_long_flag():
    result = CliRunner().invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert result.output == f"cli, version {__version__}\n"


def test_version_short_flag():
    result = CliRunner().invoke(cli, ["-v"])

    assert result.exit_code == 0
    assert result.output == f"cli, version {__version__}\n"


def test_detect_ecosystem_all_lockfile_names():
    """_detect_ecosystem handles every filename defined in LOCKFILE_NAMES."""
    for filename, expected_eco in LOCKFILE_NAMES.items():
        assert _detect_ecosystem(Path(filename)) == expected_eco


def test_detect_ecosystem_python_lockfiles():
    """All Python lockfile and manifest variants detect as python."""
    python_files = [
        "Pipfile.lock",
        "uv.lock",
        "pyproject.toml",
        "poetry.lock",
        "requirements.txt",
    ]
    for filename in python_files:
        assert _detect_ecosystem(Path(filename)) == "python"


def test_detect_ecosystem_java_build_files():
    """All Java Gradle and version catalog files detect as java."""
    java_files = [
        "build.gradle",
        "build.gradle.kts",
        "libs.versions.toml",
    ]
    for filename in java_files:
        assert _detect_ecosystem(Path(filename)) == "java"


def test_detect_ecosystem_case_insensitive():
    """Lockfile detection is case-insensitive."""
    assert _detect_ecosystem(Path("PIPFILE.LOCK")) == "python"
    assert _detect_ecosystem(Path("UV.LOCK")) == "python"
    assert _detect_ecosystem(Path("PyProject.Toml")) == "python"
    assert _detect_ecosystem(Path("BUILD.GRADLE")) == "java"
    assert _detect_ecosystem(Path("Build.Gradle.Kts")) == "java"
    assert _detect_ecosystem(Path("Libs.Versions.Toml")) == "java"


def test_detect_ecosystem_nested_path():
    """Ecosystem is detected from file name in nested directories."""
    assert _detect_ecosystem(Path("/tmp/subproject/Pipfile.lock")) == "python"
    assert _detect_ecosystem(Path("/home/user/repo/app/build.gradle")) == "java"


def test_detect_ecosystem_unknown_fallback():
    """Unknown lockfiles fall back to rust ecosystem."""
    assert _detect_ecosystem(Path("unknown.lock")) == "rust"
    assert _detect_ecosystem(Path("arbitrary.txt")) == "rust"


def test_check_auto_detects_ecosystem(tmp_path):
    """taintrace check auto-detects ecosystem from filename."""
    runner = CliRunner()
    pipfile = tmp_path / "Pipfile.lock"
    pipfile.write_text('{"_meta": {}, "default": {"requests": {"version": "==2.31.0"}}}')

    result = runner.invoke(cli, ["check", str(pipfile)])
    assert result.exit_code == 0
    assert "scanning Pipfile.lock" in result.output

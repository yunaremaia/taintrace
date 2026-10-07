"""Tests for Gemfile.lock and Pipfile.lock parsers."""
import json
from pathlib import Path
from taintrace.lockfile import LockfileParser


def test_parse_gemfile_lock_basic(tmp_path):
    """Parse a basic Gemfile.lock."""
    gemfile = tmp_path / "Gemfile.lock"
    gemfile.write_text(
        "GEM\n"
        "  remote: https://rubygems.org/\n"
        "  specs:\n"
        "    rails (7.1.3)\n"
        "      actioncable (= 7.1.3)\n"
        "      actionmailbox (= 7.1.3)\n"
        "    nokogiri (1.16.5)\n"
        "      mini_portile2 (~> 2.8.2)\n"
        "\n"
        "PLATFORMS\n"
        "  ruby\n"
        "\n"
        "DEPENDENCIES\n"
        "  rails\n"
        "  nokogiri\n"
        "\n"
        "BUNDLED WITH\n"
        "   2.5.11\n"
    )
    parser = LockfileParser()
    deps = parser.parse(gemfile)
    names = {d.name for d in deps}
    assert "rails" in names
    assert "nokogiri" in names
    # Sub-deps are included now that the indent check accepts 6+ spaces.
    assert "actioncable" in names
    assert "actionmailbox" in names
    for d in deps:
        assert d.ecosystem == "ruby"


def test_parse_gemfile_lock_empty(tmp_path):
    """Parse an empty/missing Gemfile.lock."""
    gemfile = tmp_path / "Gemfile.lock"
    gemfile.write_text("")
    parser = LockfileParser()
    deps = parser.parse(gemfile)
    assert deps == []


def test_parse_pipfile_lock_basic(tmp_path):
    """Parse a basic Pipfile.lock."""
    pipfile = tmp_path / "Pipfile.lock"
    data = {
        "default": {
            "requests": {
                "hashes": ["sha256:abc123"],
                "version": "==2.31.0",
            },
            "flask": {
                "hashes": ["sha256:def456"],
                "version": "==3.0.0",
            },
        },
        "develop": {
            "pytest": {
                "hashes": ["sha256:ghi789"],
                "version": "==7.4.0",
            },
        },
    }
    pipfile.write_text(json.dumps(data))
    parser = LockfileParser()
    deps = parser.parse(pipfile)
    names = {d.name: d for d in deps}
    assert "requests" in names
    assert names["requests"].version == "2.31.0"
    assert "flask" in names
    assert names["flask"].version == "3.0.0"
    assert "pytest" in names
    assert names["pytest"].version == "7.4.0"
    for d in deps:
        assert d.ecosystem == "python"


def test_parse_pipfile_lock_invalid_json(tmp_path):
    """Parse an invalid Pipfile.lock."""
    pipfile = tmp_path / "Pipfile.lock"
    pipfile.write_text("not valid json{{{")
    parser = LockfileParser()
    deps = parser.parse(pipfile)
    assert deps == []


def test_parse_pipfile_lock_missing(tmp_path):
    """Parse a missing Pipfile.lock (direct call)."""
    pipfile = tmp_path / "nonexistent.lock"
    parser = LockfileParser()
    # Direct call - parse() would default to cargo for unknown ext
    deps = parser._parse_pipfile_lock(pipfile)
    assert deps == []



def test_parse_cargo_toml_resolves_workspace_dependency(tmp_path):
    """Resolve a workspace-inherited dependency from the root Cargo.toml."""
    workspace = tmp_path / "workspace"
    member = workspace / "member"
    member.mkdir(parents=True)

    (workspace / "Cargo.toml").write_text(
        "[workspace]\n"
        "members = [\"member\"]\n\n"
        "[workspace.dependencies]\n"
        "serde = \"1.0\"\n"
    )
    cargo = member / "Cargo.toml"
    cargo.write_text(
        "[package]\n"
        "name = \"member\"\n\n"
        "[dependencies]\n"
        "serde = { workspace = true }\n"
    )

    deps = LockfileParser().parse(cargo)

    assert [(d.name, d.version, d.ecosystem) for d in deps] == [
        ("serde", "1.0", "rust")
    ]


def test_parse_cargo_toml_keeps_workspace_marker_without_root(tmp_path):
    """Keep workspace-inherited dependencies when the workspace root is unavailable."""
    cargo = tmp_path / "Cargo.toml"
    cargo.write_text(
        "[package]\n"
        "name = \"member\"\n\n"
        "[dependencies]\n"
        "serde = { workspace = true }\n"
    )

    deps = LockfileParser().parse(cargo)

    assert [(d.name, d.version, d.ecosystem) for d in deps] == [
        ("serde", "workspace", "rust")
    ]


def test_parse_yarn_workspace_skip(tmp_path):
    """Yarn lockfile with workspace: in version should be skipped."""
    yarn = tmp_path / "yarn.lock"
    yarn.write_text(
        "# yarn lockfile v1\n"
        "\n"
        "lodash@^4.17.21:\n"
        '  version "4.17.21"\n'
        '  resolved "https://..."\n'
        "\n"
        "workspace-pkg@workspace:packages/foo:\n"
        '  version "1.0.0"\n'
    )
    parser = LockfileParser()
    deps = parser.parse(yarn)
    names = {d.name for d in deps}
    assert "lodash" in names
    assert "workspace-pkg" not in names


def test_parse_yarn_version_fallback(tmp_path):
    """Yarn lockfile without version field falls back to version_spec."""
    yarn = tmp_path / "yarn.lock"
    yarn.write_text(
        "# yarn lockfile v1\n"
        "\n"
        "lodash@^4.17.21:\n"
        '  resolved "https://..."\n'
    )
    parser = LockfileParser()
    deps = parser.parse(yarn)
    assert len(deps) == 1
    assert deps[0].name == "lodash"
    assert deps[0].version == "^4.17.21"


def test_pyproject_tomli_fallback(tmp_path, monkeypatch):
    """When tomllib is unavailable, fall back to tomli."""
    import sys
    import types

    # Remove tomllib from sys.modules to force ImportError
    monkeypatch.delitem(sys.modules, "tomllib", raising=False)

    # Provide a fake tomli module with a load function
    fake_tomli = types.ModuleType("tomli")
    fake_tomli.load = lambda f: {"project": {"dependencies": ["requests>=2.0"]}}
    monkeypatch.setitem(sys.modules, "tomli", fake_tomli)

    # Make the import fail
    real_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

    def mock_import(name, *args, **kwargs):
        if name == "tomllib":
            raise ImportError("No module named 'tomllib'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", mock_import)

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project]\n"
        'name = "test"\n'
        'dependencies = ["requests>=2.0"]\n'
    )

    parser = LockfileParser()
    deps = parser.parse(pyproject)
    assert len(deps) == 1
    assert deps[0].name == "requests"

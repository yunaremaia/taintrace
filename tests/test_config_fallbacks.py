"""Config parsing branches that only run when an optional parser is missing.

``config.py`` supports four formats (TOML, YAML, JSON, extension sniffing) and
each one has a degradation path: ``tomllib``/``tomli``, ``PyYAML`` or the
built-in fallback parser, and a malformed-file guard. Without PyYAML installed
the real YAML tests in ``test_config.py`` only ever exercise the fallback, so
these tests drive the PyYAML path through a stub module and assert what the
parser does with whatever ``yaml.safe_load`` hands back.
"""

from __future__ import annotations

import builtins
import sys
import types
from pathlib import Path

import pytest

from taintrace import config as config_module
from taintrace.config import (
    _parse_toml_file,
    _parse_yaml_file,
    _simple_yaml_fallback,
    find_default_config,
    parse_config_file,
    validate_config,
)


@pytest.fixture
def stub_yaml(monkeypatch: pytest.MonkeyPatch):
    """Install a minimal stand-in for PyYAML and record the file it was given."""

    class Recorder:
        def __init__(self) -> None:
            self.loads: list[str] = []
            self.result: object = None
            self.error: Exception | None = None

        def safe_load(self, stream):
            self.loads.append(stream.read())
            if self.error is not None:
                raise self.error
            return self.result

    recorder = Recorder()
    module = types.ModuleType("yaml")
    # setattr rather than attribute assignment: ModuleType has no declared
    # safe_load attribute, and a type: ignore here would be a suppression.
    setattr(module, "safe_load", recorder.safe_load)
    monkeypatch.setitem(sys.modules, "yaml", module)
    return recorder


class TestYamlBackend:
    """The PyYAML branch of ``_parse_yaml_file``."""

    def test_pyyaml_result_is_used_and_taintrace_table_is_unwrapped(self, tmp_path: Path, stub_yaml) -> None:
        config_file = tmp_path / ".taintrace.yaml"
        config_file.write_text("taintrace:\n  threshold: 0.88\n", encoding="utf-8")
        stub_yaml.result = {"taintrace": {"threshold": 0.88}}

        assert _parse_yaml_file(config_file) == {"threshold": 0.88}
        assert stub_yaml.loads, "PyYAML branch must actually call safe_load"

    def test_pyyaml_result_without_taintrace_table_is_returned_as_is(self, tmp_path: Path, stub_yaml) -> None:
        config_file = tmp_path / ".taintrace.yml"
        config_file.write_text("threshold: 0.6\n", encoding="utf-8")
        stub_yaml.result = {"threshold": 0.6}

        assert _parse_yaml_file(config_file) == {"threshold": 0.6}

    def test_empty_pyyaml_document_becomes_an_empty_mapping(self, tmp_path: Path, stub_yaml) -> None:
        config_file = tmp_path / ".taintrace.yaml"
        config_file.write_text("", encoding="utf-8")
        stub_yaml.result = None

        assert _parse_yaml_file(config_file) == {}

    def test_non_mapping_pyyaml_document_is_rejected(self, tmp_path: Path, stub_yaml) -> None:
        config_file = tmp_path / ".taintrace.yaml"
        config_file.write_text("- a\n- b\n", encoding="utf-8")
        stub_yaml.result = ["a", "b"]

        assert _parse_yaml_file(config_file) == {}

    def test_pyyaml_parse_error_yields_an_empty_mapping(self, tmp_path: Path, stub_yaml) -> None:
        config_file = tmp_path / ".taintrace.yaml"
        config_file.write_text("threshold: [\n", encoding="utf-8")
        stub_yaml.error = ValueError("malformed YAML")

        assert _parse_yaml_file(config_file) == {}

    def test_parse_config_file_uses_the_pyyaml_branch(self, tmp_path: Path, stub_yaml) -> None:
        """End-to-end through the public entry point, not just the helper."""
        config_file = tmp_path / ".taintrace.yaml"
        config_file.write_text("taintrace:\n  ecosystem: rust\n", encoding="utf-8")
        stub_yaml.result = {"taintrace": {"ecosystem": "rust"}}

        assert parse_config_file(config_file) == {"ecosystem": "rust"}


class TestSimpleYamlFallback:
    """The hand-rolled parser used when PyYAML is not installed."""

    def test_inline_list_value(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".taintrace.yaml"
        config_file.write_text(
            "# a comment\n"
            "ignore: ['alpha', \"beta\"]\n"
            "empty:\n",
            encoding="utf-8",
        )

        assert _simple_yaml_fallback(config_file) == {
            "ignore": ["alpha", "beta"],
            "empty": [],
        }

    def test_yes_is_read_as_true(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".taintrace.yaml"
        config_file.write_text("no_informational: yes\n", encoding="utf-8")

        assert _simple_yaml_fallback(config_file) == {"no_informational": True}

    def test_block_list_under_a_key(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".taintrace.yaml"
        config_file.write_text(
            "ignore:\n  - one\n  # skipped comment\n  - two\n",
            encoding="utf-8",
        )

        assert _simple_yaml_fallback(config_file) == {"ignore": ["one", "two"]}

    def test_unreadable_file_yields_an_empty_mapping(self, tmp_path: Path) -> None:
        """The fallback swallows read errors rather than propagating them."""
        missing = tmp_path / "absent.yaml"

        assert _simple_yaml_fallback(missing) == {}


class TestTomlBackend:
    """``_parse_toml_file`` when no TOML reader is importable at all."""

    def test_missing_toml_reader_returns_an_empty_mapping(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without tomllib or tomli the config is empty, not a crash (#77 class)."""
        config_file = tmp_path / ".taintrace.toml"
        config_file.write_text('[taintrace]\nthreshold = 0.9\n', encoding="utf-8")
        real_import = builtins.__import__

        def blocked_import(name, *args, **kwargs):
            if name in ("tomllib", "tomli"):
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", blocked_import)
        monkeypatch.delitem(sys.modules, "tomllib", raising=False)
        monkeypatch.delitem(sys.modules, "tomli", raising=False)

        assert _parse_toml_file(config_file) == {}

    def test_tomli_is_used_when_tomllib_is_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Python 3.10 has no tomllib; tomli must take over transparently.

        A stub stands in for tomli so the assertion holds whether or not the
        real backport is installed, and on every interpreter -- the CI matrix
        runs 3.10-3.12 and ``tomllib`` only entered the stdlib in 3.11. Setting
        the ``tomllib`` entry to None makes ``import tomllib`` raise, which is
        the condition being exercised.
        """
        config_file = tmp_path / ".taintrace.toml"
        config_file.write_text('[taintrace]\nthreshold = 0.42\n', encoding="utf-8")
        loaded: list[bytes] = []

        def fake_load(stream):
            loaded.append(stream.read())
            return {"taintrace": {"threshold": 0.42}}

        stub = types.ModuleType("tomli")
        setattr(stub, "load", fake_load)

        monkeypatch.setitem(sys.modules, "tomli", stub)
        monkeypatch.setitem(sys.modules, "tomllib", None)

        assert _parse_toml_file(config_file) == {"threshold": 0.42}
        assert loaded, "the tomli fallback must be the reader that was used"


class TestParseConfigFileBranches:
    """Format dispatch in ``parse_config_file``."""

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert parse_config_file(tmp_path / "nothing.toml") == {}

    def test_json_file_with_taintrace_table(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".taintrace.json"
        config_file.write_text('{"taintrace": {"threshold": 0.7}}', encoding="utf-8")

        assert parse_config_file(config_file) == {"threshold": 0.7}

    def test_json_file_without_taintrace_table(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".taintrace.json"
        config_file.write_text('{"ecosystem": "go"}', encoding="utf-8")

        assert parse_config_file(config_file) == {"ecosystem": "go"}

    def test_malformed_json_returns_empty(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".taintrace.json"
        config_file.write_text("{not json", encoding="utf-8")

        assert parse_config_file(config_file) == {}

    def test_unknown_extension_is_sniffed_as_toml_then_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".taintrace.conf"
        config_file.write_text('threshold = 0.55\n', encoding="utf-8")

        assert parse_config_file(config_file) == {"threshold": 0.55}

    def test_non_mapping_json_payload_is_rejected(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".taintrace.json"
        config_file.write_text("[1, 2, 3]", encoding="utf-8")

        assert parse_config_file(config_file) == {}


class TestValidateConfigBranches:
    """Normalization rules in ``validate_config``."""

    def test_ignore_accepts_a_comma_separated_string(self) -> None:
        assert validate_config({"ignore": "alpha, beta ,, gamma"})["ignore"] == [
            "alpha",
            "beta",
            "gamma",
        ]

    def test_ignore_accepts_a_tuple(self) -> None:
        assert validate_config({"ignore": ("alpha", 2)})["ignore"] == ["alpha", "2"]

    def test_ignore_of_an_unusable_type_is_dropped(self) -> None:
        assert "ignore" not in validate_config({"ignore": 7})

    def test_non_numeric_threshold_is_dropped(self) -> None:
        assert "threshold" not in validate_config({"threshold": "not-a-number"})

    def test_threshold_of_a_non_numeric_type_is_dropped(self) -> None:
        assert "threshold" not in validate_config({"threshold": ["0.8"]})

    def test_hyphenated_keys_are_normalised(self) -> None:
        """``no-informational`` and ``output-format`` are accepted spellings."""
        validated = validate_config({"no-informational": True, "output-format": "SARIF"})

        assert validated["no_informational"] is True
        assert validated["output_format"] == "sarif"


class TestFindDefaultConfig:
    """Discovery order in ``find_default_config``."""

    def test_user_home_config_is_found_after_directory_search(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no project config, the home config is used."""
        home_config = tmp_path / "home" / ".taintrace.toml"
        home_config.parent.mkdir()
        home_config.write_text('[taintrace]\nthreshold = 0.11\n', encoding="utf-8")
        workdir = tmp_path / "project"
        workdir.mkdir()

        monkeypatch.setattr(config_module, "USER_CONFIG_PATHS", [home_config])
        monkeypatch.setattr(config_module, "CONFIG_FILE_NAMES", ["never-present.toml"])

        assert find_default_config(workdir) == home_config

    def test_unreadable_home_config_is_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A home config that cannot be stat'ed must not abort discovery."""
        workdir = tmp_path / "project"
        workdir.mkdir()

        class Unreadable:
            def is_file(self):
                raise OSError("permission denied")

        monkeypatch.setattr(config_module, "USER_CONFIG_PATHS", [Unreadable()])
        monkeypatch.setattr(config_module, "CONFIG_FILE_NAMES", ["never-present.toml"])

        assert find_default_config(workdir) is None

    def test_cwd_defaults_to_the_process_working_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``find_default_config()`` with no argument uses ``Path.cwd()``."""
        config_file = tmp_path / ".taintrace.toml"
        config_file.write_text('[taintrace]\nthreshold = 0.33\n', encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(config_module, "USER_CONFIG_PATHS", [])

        assert find_default_config() == config_file

    def test_load_config_with_a_nonexistent_explicit_path_returns_empty(self, tmp_path: Path) -> None:
        from taintrace.config import load_config

        assert load_config(config_path=tmp_path / "absent.toml") == {}

    def test_load_config_treats_a_directory_argument_as_cwd(self, tmp_path: Path) -> None:
        """The first positional argument is a cwd, not a config path."""
        from taintrace.config import load_config

        config_file = tmp_path / ".taintrace.toml"
        config_file.write_text('[taintrace]\nthreshold = 0.21\n', encoding="utf-8")

        assert load_config(tmp_path)["threshold"] == 0.21

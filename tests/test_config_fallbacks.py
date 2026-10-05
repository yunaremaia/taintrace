"""Config parsing branches that only run when an optional parser is missing.

``config.py`` supports four formats (TOML, YAML, JSON, extension sniffing) and
each one has a degradation path: ``tomllib``/``tomli``, ``PyYAML`` or the
built-in fallback parser, and a malformed-file guard. Without PyYAML installed
the real YAML tests in ``test_config.py`` only ever exercise the fallback, so
these tests drive the PyYAML path through a stub module and assert what the
parser does with whatever ``yaml.safe_load`` hands back.

PyYAML is now a declared dependency, so in CI it is installed and the
``except ImportError`` branch is only reachable by making the import fail
explicitly. That branch, and the value-coercion arms of the fallback parser,
were previously covered only by accident: while PyYAML was undeclared the real
YAML tests silently fell through to the fallback. Declaring the dependency
removed that accident, so the fallback is now pinned from both sides -- a stub
for the PyYAML arm, a blocked import for the fallback arm. A test that only
runs on the branch the developer's own environment happens to take is not a
test of the degradation path.
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
    ConfigError,
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

    def test_pyyaml_parse_error_propagates_for_the_caller_to_report(self, tmp_path: Path, stub_yaml) -> None:
        """The helper must not swallow it -- parse_config_file names the file."""
        config_file = tmp_path / ".taintrace.yaml"
        config_file.write_text("threshold: [\n", encoding="utf-8")
        stub_yaml.error = ValueError("malformed YAML")

        with pytest.raises(ValueError, match="malformed YAML"):
            _parse_yaml_file(config_file)

    def test_parse_config_file_reports_a_pyyaml_parse_error(self, tmp_path: Path, stub_yaml) -> None:
        config_file = tmp_path / ".taintrace.yaml"
        config_file.write_text("threshold: [\n", encoding="utf-8")
        stub_yaml.error = ValueError("malformed YAML")

        with pytest.raises(ConfigError) as excinfo:
            parse_config_file(config_file)

        message = str(excinfo.value)
        assert str(config_file) in message
        assert "YAML" in message
        assert "malformed YAML" in message

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

    def test_no_is_read_as_false(self, tmp_path: Path) -> None:
        """The false arm is a separate branch from the true arm, not a shared one."""
        config_file = tmp_path / ".taintrace.yaml"
        config_file.write_text("no_informational: no\n", encoding="utf-8")

        assert _simple_yaml_fallback(config_file) == {"no_informational": False}

    def test_numeric_values_are_coerced_to_int_and_float(self, tmp_path: Path) -> None:
        """A bare scalar goes through the int()/float() coercion, not to str."""
        config_file = tmp_path / ".taintrace.yaml"
        config_file.write_text("threshold: 0.42\nretries: 3\n", encoding="utf-8")

        parsed = _simple_yaml_fallback(config_file)

        assert parsed["threshold"] == 0.42
        assert isinstance(parsed["threshold"], float)
        assert parsed["retries"] == 3
        assert isinstance(parsed["retries"], int)

    def test_non_numeric_scalar_is_kept_as_a_quoted_string(self, tmp_path: Path) -> None:
        """The ValueError arm keeps the value, with any surrounding quotes removed."""
        config_file = tmp_path / ".taintrace.yaml"
        config_file.write_text("ecosystem: 'rust'\nformat: \"json\"\n", encoding="utf-8")

        assert _simple_yaml_fallback(config_file) == {
            "ecosystem": "rust",
            "format": "json",
        }

    def test_quoted_yaml_is_not_disagreeing_with_real_yaml(self, tmp_path: Path) -> None:
        """Why PyYAML is declared rather than left to this fallback.

        The fallback is a hand-rolled subset, so it silently disagrees with real
        YAML on constructs as ordinary as a trailing comment and quoted
        booleans. This test is the regression guard for the dependency being
        declared: it asserts the two parsers agree on this document, so the
        package's behaviour cannot drift back to whichever parser happens to be
        importable in the test environment.
        """
        yaml = pytest.importorskip(
            "yaml", reason="PyYAML is a declared dependency; a bare checkout may lack it"
        )
        document = (
            "# trailing comment\n"
            "taintrace:\n"
            "  threshold: 0.42\n"
            "  format: json\n"
            "  no_informational: false\n"
            "  ignore: [alpha, beta]\n"
        )
        config_file = tmp_path / ".taintrace.yaml"
        config_file.write_text(document, encoding="utf-8")

        assert yaml.safe_load(document) == {
            "taintrace": {
                "threshold": 0.42,
                "format": "json",
                "no_informational": False,
                "ignore": ["alpha", "beta"],
            }
        }
        assert parse_config_file(config_file) == {
            "threshold": 0.42,
            "format": "json",
            "no_informational": False,
            "ignore": ["alpha", "beta"],
        }


class TestYamlImportFallback:
    """The ``except ImportError`` arm of ``_parse_yaml_file``.

    Reachable only by making ``import yaml`` fail, which is exactly what a
    user installing a broken or absent PyYAML hits -- and, before PyYAML was a
    declared dependency, what every CI run hit by accident.
    """

    @pytest.fixture
    def without_yaml(self, monkeypatch: pytest.MonkeyPatch):
        real_import = builtins.__import__

        def blocked_import(name, *args, **kwargs):
            if name == "yaml":
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", blocked_import)
        monkeypatch.delitem(sys.modules, "yaml", raising=False)

    def test_missing_pyyaml_falls_back_to_the_simple_parser(
        self, tmp_path: Path, without_yaml
    ) -> None:
        # Flat, not nested: the fallback has no notion of indentation, so a
        # ``taintrace:`` table with children under it is exactly the shape it
        # cannot read. That limitation is the reason PyYAML is a declared
        # dependency rather than an optional nicety.
        config_file = tmp_path / ".taintrace.yaml"
        config_file.write_text("threshold: 0.65\n", encoding="utf-8")

        assert _parse_yaml_file(config_file) == {"threshold": 0.65}

    def test_missing_pyyaml_still_returns_an_empty_mapping_for_a_nested_table(
        self, tmp_path: Path, without_yaml
    ) -> None:
        """The degradation path degrades, it does not crash or invent values."""
        config_file = tmp_path / ".taintrace.yml"
        config_file.write_text("taintrace:\n  ecosystem: rust\n", encoding="utf-8")

        # ``taintrace:`` with no inline value becomes an empty list key and the
        # nested ``ecosystem:`` lands at the top level. Asserted exactly, so a
        # future change that makes the fallback silently drop data fails here.
        assert _parse_yaml_file(config_file) == {"taintrace": [], "ecosystem": "rust"}

    def test_missing_pyyaml_and_an_unreadable_file_yields_an_empty_mapping(
        self, tmp_path: Path, without_yaml
    ) -> None:
        """Both degradation paths composed: no parser and no file."""
        missing = tmp_path / "absent.yaml"

        assert _parse_yaml_file(missing) == {}


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

    def test_malformed_json_is_reported_not_swallowed(self, tmp_path: Path) -> None:
        """A corrupt file must not read as "nothing configured"."""
        config_file = tmp_path / ".taintrace.json"
        config_file.write_text("{not json", encoding="utf-8")

        with pytest.raises(ConfigError) as excinfo:
            parse_config_file(config_file)

        message = str(excinfo.value)
        assert str(config_file) in message
        assert "JSON" in message

    @pytest.mark.parametrize(
        "name,body,fmt",
        [
            (".taintrace.toml", "threshold = 0.5\n[broken\n", "TOML"),
            (".taintrace.yaml", "threshold: 0.5\n  bad: [unclosed\n", "YAML"),
            (".taintrace.json", '{"threshold": 0.5,,,}', "JSON"),
        ],
    )
    def test_every_format_reports_a_corrupt_file_the_same_way(
        self, tmp_path: Path, name: str, body: str, fmt: str
    ) -> None:
        """The asymmetry this guards: TOML raised, YAML/JSON silently returned {}."""
        from taintrace.config import load_config

        config_file = tmp_path / name
        config_file.write_text(body, encoding="utf-8")

        with pytest.raises(ConfigError) as excinfo:
            load_config(config_path=config_file)

        message = str(excinfo.value)
        assert str(config_file) in message, message
        assert fmt in message, message
        assert excinfo.value.__cause__ is not None, "the parser's own error must be kept"

    def test_a_discovered_corrupt_config_raises_instead_of_using_defaults(self, tmp_path: Path) -> None:
        from taintrace.config import load_config

        (tmp_path / ".taintrace.yaml").write_text("threshold: 0.9\n  bad: [unclosed\n", encoding="utf-8")

        with pytest.raises(ConfigError, match="malformed YAML"):
            load_config(cwd=tmp_path)

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

    def test_a_newly_recognised_key_passes_through_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The trailing ``else`` arm: a valid key with no dedicated normaliser.

        Every key currently in ``VALID_CONFIG_KEYS`` has an explicit branch
        above it, so that arm is unreachable through the shipped key set -- but
        it is the forward-compatibility contract: when a key is added to
        ``VALID_CONFIG_KEYS`` and given no normalisation rule of its own, its
        value must reach the caller intact rather than being silently dropped
        by the ``key not in VALID_CONFIG_KEYS`` guard. Adding the key to the
        accepted set is what makes the branch reachable, so this test is the
        only way to assert it at all; without it, the one uncovered statement
        in the package would be this line, with no test to say what it is for.

        ``setattr`` with a rebuilt set rather than ``monkeypatch.setitem``,
        which requires a Mapping and would raise on a set.
        """
        monkeypatch.setattr(
            config_module,
            "VALID_CONFIG_KEYS",
            config_module.VALID_CONFIG_KEYS | {"severity_floor"},
        )

        assert validate_config({"severity_floor": "high"}) == {"severity_floor": "high"}

    def test_a_recognised_key_that_is_not_accepted_is_still_dropped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The pass-through must not leak: an unrecognised key is still filtered."""
        validated = validate_config({"totally_made_up": "x", "threshold": 0.5})

        assert validated == {"threshold": 0.5}


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

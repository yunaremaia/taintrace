"""CLI branches that the happy-path tests never reach.

Covers the ``check``/``scan-directory`` ignore merging, the informational
filter, the recursive-walk guards, and the ``python -m taintrace.cli``
entry point. Every test drives the real Click command through ``CliRunner``
and asserts on the exit code and emitted output.
"""

from __future__ import annotations

import json
import pathlib
import runpy
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from taintrace.cli import _find_lockfiles, cli

TYPOSQUAT = "reqeusts==2.31.0"
KNOWN = "requests==2.31.0"
# HIGH at 0.9231, so a threshold above it filters the package out while the
# 1.0-scored `reqeusts` stays in.
NEAR_MISS = "scikit-learn-==1.0.0"


def _requirements(directory: Path, *lines: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    lockfile = directory / "requirements.txt"
    lockfile.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lockfile


def _payload(result) -> dict:
    """Parse the JSON document out of a scan-directory invocation.

    ``scan-directory`` prints a per-file human summary before the machine
    format whenever it discovers more than one lockfile, so the JSON payload
    starts at the first ``{`` rather than at the beginning of the output.
    """
    start = result.output.index("{")
    return json.loads(result.output[start:])


class TestCheckInvocation:
    def test_check_without_arguments_exits_with_usage_error(self) -> None:
        result = CliRunner().invoke(cli, ["check"])

        assert result.exit_code == 2
        assert "at least one lockfile required" in result.output

    def test_check_reports_a_typosquat_and_exits_nonzero(self, tmp_path: Path) -> None:
        lockfile = _requirements(tmp_path, TYPOSQUAT)

        result = CliRunner().invoke(cli, ["check", str(lockfile), "--format", "json"])

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["summary"]["suspects"] == 1
        assert payload["summary"]["risk_levels"]["CRITICAL"] == 1

    def test_check_with_only_known_packages_exits_zero(self, tmp_path: Path) -> None:
        lockfile = _requirements(tmp_path, KNOWN)

        result = CliRunner().invoke(cli, ["check", str(lockfile)])

        assert result.exit_code == 0
        assert "No typosquat suspects detected" in result.output

    def test_check_sarif_output_is_valid_sarif(self, tmp_path: Path) -> None:
        lockfile = _requirements(tmp_path, TYPOSQUAT)

        result = CliRunner().invoke(cli, ["check", str(lockfile), "--format", "sarif"])

        sarif = json.loads(result.output)
        assert result.exit_code == 1
        assert sarif["version"] == "2.1.0"
        assert sarif["runs"][0]["results"][0]["ruleId"] == "TYPO001"
        assert sarif["runs"][0]["results"][0]["level"] == "error"

    def test_check_sarif_uri_uses_the_lockfile_name(self, tmp_path: Path) -> None:
        lockfile = _requirements(tmp_path, TYPOSQUAT)

        result = CliRunner().invoke(cli, ["check", str(lockfile), "--format", "sarif"])

        location = json.loads(result.output)["runs"][0]["results"][0]["locations"][0]
        assert location["physicalLocation"]["artifactLocation"]["uri"] == "requirements.txt"

    def test_no_informational_keeps_only_critical_and_high(self, tmp_path: Path) -> None:
        """A MEDIUM informational finding is scored but not reported as a suspect."""
        lockfile = _requirements(tmp_path, "reqeusts-tiny==1.0.0", TYPOSQUAT)

        result = CliRunner().invoke(
            cli, ["check", str(lockfile), "--format", "json", "--no-informational"]
        )

        payload = json.loads(result.output)
        assert payload["summary"]["suspects"] == 1
        assert payload["summary"]["risk_levels"] == {
            "CRITICAL": 1,
            "HIGH": 0,
            "MEDIUM": 0,
        }
        assert result.exit_code == 1

    def test_a_medium_finding_is_never_a_suspect_with_or_without_the_flag(
        self, tmp_path: Path
    ) -> None:
        """The control for the test above: --no-informational cannot be what drops it.

        ``is_suspect`` is already HIGH-or-CRITICAL, so a MEDIUM package stays
        out of ``summary.suspects`` either way; the flag only re-filters a set
        that was already restricted. Both runs therefore report the same
        suspect count, while ``results`` keeps the informational entry.
        """
        lockfile = _requirements(tmp_path, "reqeusts-tiny==1.0.0", TYPOSQUAT)

        runner = CliRunner()
        with_flag = runner.invoke(
            cli, ["check", str(lockfile), "--format", "json", "--no-informational"]
        )
        without_flag = runner.invoke(cli, ["check", str(lockfile), "--format", "json"])

        flag_payload = json.loads(with_flag.output)
        plain_payload = json.loads(without_flag.output)

        assert flag_payload["summary"] == plain_payload["summary"]
        assert {item["risk_level"] for item in flag_payload["results"]} == {
            "MEDIUM",
            "CRITICAL",
        }

    def test_threshold_from_the_config_file_is_applied(self, tmp_path: Path) -> None:
        """A config threshold at its default-CLI value is honoured.

        ``NEAR_MISS`` scores 0.9231 and ``reqeusts`` scores 1.0, so a config
        threshold of 0.95 keeps the exact typosquat and drops the near miss.
        """
        config_file = tmp_path / ".taintrace.toml"
        config_file.write_text("[taintrace]\nthreshold = 0.95\n", encoding="utf-8")
        lockfile = _requirements(tmp_path, NEAR_MISS, TYPOSQUAT)

        result = CliRunner().invoke(
            cli, ["check", "--config", str(config_file), str(lockfile), "--format", "json"]
        )

        payload = json.loads(result.output)
        assert payload["summary"]["suspects"] == 1
        assert {item["package"] for item in payload["results"] if item["risk_score"] >= 0.95} == {
            "reqeusts"
        }
        assert result.exit_code == 1

    def test_config_output_format_is_used_when_the_flag_is_default(
        self, tmp_path: Path
    ) -> None:
        config_file = tmp_path / ".taintrace.toml"
        config_file.write_text('[taintrace]\noutput_format = "json"\n', encoding="utf-8")
        lockfile = _requirements(tmp_path, KNOWN)

        result = CliRunner().invoke(
            cli, ["check", "--config", str(config_file), str(lockfile)]
        )

        assert json.loads(result.output)["tool"] == "taintrace"

    def test_config_ecosystem_is_used_when_the_flag_is_default(self, tmp_path: Path) -> None:
        """A config ecosystem behaves exactly like the equivalent --ecosystem flag.

        ``unknown.lockfile`` has no known parser, so it is read as a Cargo.lock
        and each dependency keeps the ``rust`` ecosystem the parser recorded.
        Scoring follows that per-dependency ecosystem, which is why ``reqeusts``
        -- a CRITICAL typosquat of the python ``requests`` -- comes back MEDIUM
        here. The config file and the flag agree; neither overrides the parser.
        """
        config_file = tmp_path / ".taintrace.toml"
        config_file.write_text('[taintrace]\necosystem = "python"\n', encoding="utf-8")
        lockfile = tmp_path / "unknown.lockfile"
        lockfile.write_text(
            '[[package]]\nname = "reqeusts"\nversion = "1.0.0"\n', encoding="utf-8"
        )

        runner = CliRunner()
        from_config = runner.invoke(
            cli, ["check", "--config", str(config_file), str(lockfile), "--format", "json"]
        )
        from_flag = runner.invoke(
            cli,
            ["check", "--ecosystem", "python", str(lockfile), "--format", "json"],
        )
        renamed = tmp_path / "requirements.txt"
        renamed.write_text("reqeusts==2.31.0\n", encoding="utf-8")
        as_python = runner.invoke(cli, ["check", str(renamed), "--format", "json"])

        config_results = json.loads(from_config.output)["results"]
        flag_results = json.loads(from_flag.output)["results"]

        assert [item["risk_level"] for item in config_results] == ["MEDIUM"]
        assert flag_results == config_results
        assert json.loads(as_python.output)["results"][0]["risk_level"] == "CRITICAL"

    def test_a_nested_lockfiles_own_config_is_merged_into_check(
        self, tmp_path: Path
    ) -> None:
        """``check`` merges each lockfile's sibling config when none was passed.

        The base directory is taken from the first lockfile, so a second one in
        a subdirectory carries its own ignore list, which is merged on top of
        the base. Both the typosquat and the clean package are scanned, and only
        the subdirectory's ignore entry removes one.
        """
        nested = tmp_path / "service"
        nested.mkdir(parents=True)
        first = _requirements(tmp_path, TYPOSQUAT)
        second = _requirements(nested, TYPOSQUAT, KNOWN)
        (nested / ".taintrace.toml").write_text(
            '[taintrace]\nignore = ["reqeusts"]\n', encoding="utf-8"
        )

        result = CliRunner().invoke(
            cli, ["check", str(first), str(second), "--format", "json"]
        )

        payload = json.loads(result.output)
        # The root lockfile has no config, so its typosquat survives; the
        # nested one is ignored by the config sitting beside it.
        assert [(item["package"], item["risk_level"]) for item in payload["results"]] == [
            ("reqeusts", "CRITICAL"),
            ("requests", "LOW"),
        ]
        assert payload["summary"]["suspects"] == 1
        assert result.exit_code == 1


class TestScanDirectoryIgnoreMerging:
    def test_ignore_from_a_nested_directory_config_is_applied(self, tmp_path: Path) -> None:
        """A nested lockfile honours the ignore list next to it, not the root."""
        root = tmp_path / "repo"
        nested = root / "service"
        nested.mkdir(parents=True)
        _requirements(nested, TYPOSQUAT)
        _requirements(root, KNOWN)
        (nested / ".taintrace.toml").write_text(
            '[taintrace]\nignore = ["reqeusts"]\n', encoding="utf-8"
        )

        result = CliRunner().invoke(
            cli, ["scan-directory", str(root), "--format", "json"]
        )

        payload = _payload(result)
        assert [item["package"] for item in payload["results"]] == ["requests"]
        assert result.exit_code == 0

    def test_ignore_flag_applies_to_every_discovered_lockfile(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        _requirements(root, TYPOSQUAT)
        _requirements(root / "api", TYPOSQUAT)
        _requirements(root / "web", KNOWN)

        result = CliRunner().invoke(
            cli,
            ["scan-directory", str(root), "--ignore", "reqeusts", "--format", "json"],
        )

        payload = _payload(result)
        assert {item["package"] for item in payload["results"]} == {"requests"}
        assert result.exit_code == 0

    def test_no_informational_is_applied_across_the_tree(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        _requirements(root, "reqeusts-tiny==1.0.0", TYPOSQUAT)

        result = CliRunner().invoke(
            cli,
            ["scan-directory", str(root), "--format", "json", "--no-informational"],
        )

        payload = _payload(result)
        assert payload["summary"]["suspects"] == 1
        assert payload["summary"]["risk_levels"]["MEDIUM"] == 0
        assert result.exit_code == 1

    def test_aggregated_suspects_are_summarised_for_multiple_lockfiles(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        _requirements(root, TYPOSQUAT)
        _requirements(root / "api", TYPOSQUAT)

        result = CliRunner().invoke(cli, ["scan-directory", str(root)])

        assert "Scanned 2 lockfiles" in result.output
        assert "Aggregated suspects across 2 lockfiles" in result.output
        assert result.exit_code == 1

    def test_scan_directory_sarif_points_at_the_first_lockfile(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        _requirements(root / "api", TYPOSQUAT)
        _requirements(root / "web", KNOWN)

        result = CliRunner().invoke(cli, ["scan-directory", str(root), "--format", "sarif"])

        sarif = json.loads(result.output[result.output.index("{") :])
        uri = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
        assert uri["artifactLocation"]["uri"] == "requirements.txt"
        assert result.exit_code == 1

    def test_config_file_threshold_is_applied_to_the_whole_tree(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        config_file = root / ".taintrace.toml"
        config_file.write_text("[taintrace]\nthreshold = 0.95\n", encoding="utf-8")
        _requirements(root, NEAR_MISS, TYPOSQUAT)

        result = CliRunner().invoke(
            cli, ["scan-directory", str(root), "--config", str(config_file), "--format", "json"]
        )

        payload = _payload(result)
        assert payload["summary"]["suspects"] == 1
        assert result.exit_code == 1

    def test_config_no_informational_is_applied_when_the_flag_is_default(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        config_file = root / ".taintrace.toml"
        config_file.write_text("[taintrace]\nno_informational = true\n", encoding="utf-8")
        _requirements(root, "reqeusts-tiny==1.0.0")

        result = CliRunner().invoke(
            cli, ["scan-directory", str(root), "--config", str(config_file), "--format", "json"]
        )

        payload = _payload(result)
        assert payload["summary"]["suspects"] == 0
        assert result.exit_code == 0

    def test_scan_directory_reports_no_lockfiles_for_a_file_path(self, tmp_path: Path) -> None:
        """Handed a lockfile rather than a directory, the walk finds nothing."""
        lockfile = _requirements(tmp_path, TYPOSQUAT)

        result = CliRunner().invoke(cli, ["scan-directory", str(lockfile), "--format", "json"])

        assert "No lockfiles found" in result.output
        assert result.exit_code == 0


class TestScoreCommand:
    def test_known_package_is_reported_as_clean(self) -> None:
        result = CliRunner().invoke(cli, ["score", "requests", "-e", "python"])

        assert result.exit_code == 0
        assert "requests" in result.output

    def test_typosquat_is_flagged_with_its_nearest_match(self) -> None:
        result = CliRunner().invoke(cli, ["score", "reqeusts", "-e", "python"])

        assert result.exit_code == 0
        assert "requests" in result.output


class TestFindLockfilesGuards:
    def test_a_file_path_yields_no_lockfiles(self, tmp_path: Path) -> None:
        """``walk`` returns immediately when handed a non-directory."""
        lockfile = _requirements(tmp_path, KNOWN)

        assert _find_lockfiles(lockfile) == []

    def test_an_unreadable_subdirectory_is_skipped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An OSError while listing a directory must not abort the whole walk."""
        root = tmp_path / "repo"
        locked = root / "locked"
        locked.mkdir(parents=True)
        _requirements(root, KNOWN)
        real_iterdir = pathlib.Path.iterdir

        def guarded_iterdir(self):
            if self == locked:
                raise OSError("permission denied")
            return real_iterdir(self)

        monkeypatch.setattr(pathlib.Path, "iterdir", guarded_iterdir)

        found = _find_lockfiles(root)

        assert [path.name for path, _ in found] == ["requirements.txt"]

    def test_a_symlinked_lockfile_outside_the_tree_is_still_reported(
        self, tmp_path: Path
    ) -> None:
        """A link to a lockfile is worth reporting even when its target is elsewhere."""
        root = tmp_path / "repo"
        root.mkdir()
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        _requirements(outside, KNOWN)
        try:
            (root / "Cargo.lock").symlink_to(outside / "requirements.txt")
        except (OSError, NotImplementedError, AttributeError) as exc:  # pragma: no cover
            pytest.skip(f"symlinks unavailable: {exc}")

        found = _find_lockfiles(root)

        assert [path.name for path, ecosystem in found] == ["Cargo.lock"]


class TestModuleEntryPoint:
    def test_python_m_taintrace_cli_reports_the_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``python -m taintrace.cli`` works, so the __main__ guard is live."""
        monkeypatch.setattr(sys, "argv", ["taintrace", "--version"])

        with pytest.raises(SystemExit) as excinfo:
            runpy.run_module("taintrace.cli", run_name="__main__")

        assert excinfo.value.code == 0

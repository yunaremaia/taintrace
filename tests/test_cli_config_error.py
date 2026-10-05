"""A malformed config file must reach the user as a message, not a traceback.

Every command loads its config through ``taintrace.config.load_config``, which
raises :class:`ConfigError` for a file it cannot parse. The group is the one
shared point all of them pass through, so it is where the error is reported.
"""

from click.testing import CliRunner

from taintrace.cli import cli


def _broken_json_config(tmp_path):
    config = tmp_path / "broken.json"
    config.write_text("{not json at all")
    return config


def _lockfile(tmp_path):
    lockfile = tmp_path / "Pipfile.lock"
    lockfile.write_text('{"_meta": {}, "default": {"requests": {"version": "==2.31.0"}}}')
    return lockfile


def test_check_reports_a_malformed_config_without_a_traceback(tmp_path):
    """`check` names the bad file and exits non-zero instead of crashing."""
    result = CliRunner().invoke(
        cli, ["check", str(_lockfile(tmp_path)), "--config", str(_broken_json_config(tmp_path))]
    )

    assert "broken.json" in result.output
    assert "malformed JSON config" in result.output
    assert "Traceback" not in result.output
    assert result.exit_code != 0


def test_scan_directory_reports_a_malformed_config_without_a_traceback(tmp_path):
    """`scan-directory` reports the same way: both config loads go through one guard."""
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "Cargo.lock").write_text("")
    result = CliRunner().invoke(
        cli, ["scan-directory", str(tmp_path), "--config", str(_broken_json_config(tmp_path))]
    )

    assert "broken.json" in result.output
    assert "malformed JSON config" in result.output
    assert "Traceback" not in result.output
    assert result.exit_code != 0


def test_discovered_malformed_config_is_reported_too(tmp_path):
    """A corrupt default config is caught without --config, on the discovery path."""
    (tmp_path / "pyproject.toml").write_text("[tool.taintrace\nthreshold = 0.5")
    (tmp_path / "Pipfile.lock").write_text('{"_meta": {}, "default": {}}')

    result = CliRunner().invoke(cli, ["check", str(tmp_path / "Pipfile.lock")])

    assert "pyproject.toml" in result.output
    assert "malformed TOML config" in result.output
    assert "Traceback" not in result.output
    assert result.exit_code != 0

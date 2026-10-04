# Configuration

`taintrace` runs with no configuration at all. A config file is only needed to
pin a threshold, silence a known false positive, or change the output format.

## Where config is discovered

`taintrace` walks up from the scan target to the filesystem root, then falls
back to your home directory. The first file found wins:

| Path | Format |
|------|--------|
| `.taintrace.toml` | TOML |
| `taintrace.toml` | TOML |
| `.taintrace.yaml`, `.taintrace.yml`, `taintrace.yaml`, `taintrace.yml` | YAML |
| `.taintracerc` | TOML |
| `pyproject.toml` | TOML, under `[tool.taintrace]` |
| `~/.config/taintrace/config.toml`, `config.yaml`, `config.yml` | TOML / YAML |
| `~/.taintrace.toml`, `~/.taintrace.yaml`, `~/.taintrace.yml` | TOML / YAML |

When `scan-directory` finds a lockfile in a subdirectory, that subdirectory's
own config is merged in as well — so a monorepo can tune each package
independently without one root file growing unwieldy.

You can also point at a file explicitly:

```bash
taintrace check Cargo.lock --config /path/to/my-config.yaml
```

## Keys

| Key | Type | Equivalent flag |
|-----|------|-----------------|
| `threshold` | float `0.0`–`1.0` | `--threshold` |
| `format` / `output_format` | `cli`, `json`, `sarif` | `--format` |
| `ecosystem` | ecosystem name, or `auto` | `--ecosystem` (`check` only) |
| `no_informational` | boolean | `--no-informational` |
| `ignore` | list of package names | `--ignore` |

Validation is lenient by design: an unrecognised key is dropped, a threshold
outside `0.0`–`1.0` is dropped, an unknown ecosystem or format is dropped, and a
value that cannot be normalised leaves the default in place. A typo silently
does nothing rather than failing a build. Keys are matched case-insensitively
and `-` is treated as `_`.

Measured behaviour:

```python
validate_config({
    "threshold": 0.85, "format": "SARIF", "ecosystem": "NODE",
    "no_informational": "yes", "ignore": ["a", "b"], "unknown": "x",
})
# -> {'threshold': 0.85, 'output_format': 'sarif', 'ecosystem': 'node',
#     'no_informational': True, 'ignore': ['a', 'b']}
```

`ignore` also accepts a comma-separated string, which is split into a list.

## Examples

### `.taintrace.toml`

```toml
[taintrace]
threshold = 0.85
output_format = "sarif"
no_informational = true
ignore = [
  "my-internal-mirror",
  "legit-package-with-similar-name",
]
```

### `.taintrace.yaml`

```yaml
taintrace:
  threshold: 0.85
  output_format: sarif
  no_informational: false
  ignore:
    - my-internal-mirror
    - ${CUSTOM_IGNORE_PKG}
```

### `pyproject.toml`

Keep taintrace settings with the rest of your project config:

```toml
[tool.taintrace]
threshold = 0.80
ignore = ["my-corp-pkg"]
```

## Environment variable interpolation

String values anywhere in the config support `$VAR` and `${VAR}`, substituted
recursively through nested tables and lists:

```yaml
taintrace:
  ignore:
    - ${CI_PROJECT_NAME}-internal
```

An unset variable is left as its literal `$NAME` text rather than becoming empty,
so a missing secret shows up in the ignore list as something obviously wrong
instead of silently ignoring `""`.

## Ignoring false positives

An ignored package is removed from the parsed results **before** thresholding,
so it is absent from `cli`, `json` and `sarif` output entirely — it does not
appear as a clean result, and it does not count towards the totals.

```bash
taintrace check examples/reports/python/requirements.txt --ignore reqeusts
```

```
╭──────────────────────────────────────────────────── Scan Results ────────────────────────────────────────────────────╮
│ taintrace v0.2.2 — scanning requirements.txt                                                                         │
│ Total deps: 0 | Suspects: 0                                                                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
✅ No typosquat suspects detected.
```

The same list in `.taintrace.toml` gives identical output and lets every
developer get the same verdict without remembering the flags:

```toml
[taintrace]
ignore = ["reqeusts"]
```

## Precedence

A CLI flag left at its default does **not** win — the config file is consulted
instead. A flag you pass explicitly always overrides the config file:

```bash
# .taintrace.toml says format = "json"
taintrace check Cargo.lock              # JSON output
taintrace check Cargo.lock --format cli # Rich table
```

Ignore lists are the exception: they are **unioned**, not overridden. CLI
`--ignore` entries and config entries both apply, so an ad-hoc `--ignore` on a
developer laptop does not wipe out the shared ignore list.

## Next steps

- [CI](ci.md) — the GitHub Action and the pre-commit hook
- [API Reference](api.md) — `taintrace.config` functions

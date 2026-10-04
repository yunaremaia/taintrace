# Usage

Three commands: `check`, `scan-directory` and `score`.

```bash
taintrace --help
```

```
Usage: taintrace [OPTIONS] COMMAND [ARGS]...

  taintrace — typosquat detector for AI coding agent dependencies.

Options:
  -v, --version  Show the version and exit.
  --help         Show this message and exit.

Commands:
  check           Check one or more lockfiles for typosquatting.
  scan-directory  Recursively scan a directory tree for typosquatting in...
  score           Score a single package name for typosquat risk.
```

## `check`

```bash
taintrace check [OPTIONS] [LOCKFILES]...
```

Check one or more lockfiles for typosquatting. At least one lockfile is
required; with none it prints `Error: at least one lockfile required` and exits
`2`.

```bash
taintrace check Cargo.lock
taintrace check Cargo.lock package-lock.json requirements.txt
```

### `check` options

| Option                    | Default  | Meaning |
|---------------------------|----------|---------|
| `-c`, `--config PATH`     | —        | Configuration file (`.toml`, `.yaml`, `.json`) |
| `-f`, `--format FORMAT`   | `cli`    | `cli`, `json` or `sarif` |
| `-t`, `--threshold FLOAT` | `0.7`    | Similarity threshold, `0.0`–`1.0` |
| `-e`, `--ecosystem NAME`  | `auto`   | `auto`, `rust`, `node`, `python`, `go`, `ruby`, `php`, `swift`, `elixir`, `java` |
| `--no-informational`      | off      | Suppress MEDIUM/LOW risk results |
| `-i`, `--ignore TEXT`     | —        | Ignore a package (repeatable) |

A CLI flag that is left at its default is overridden by the matching key in the
configuration file; a flag you pass explicitly always wins.

## `scan-directory`

```bash
taintrace scan-directory [OPTIONS] [PATH]
```

Recursively scan a directory tree for typosquatting in all lockfiles. `PATH`
defaults to `.`. Prints `No lockfiles found in <path>` and exits `0` when there
is nothing to scan.

```bash
taintrace scan-directory .
taintrace scan-directory /path/to/repo
taintrace scan-directory . --format sarif
```

### `scan-directory` options

Identical to `check` except that there is **no** `--ecosystem` flag — each
lockfile's ecosystem comes from its own filename.

| Option                    | Default  | Meaning |
|---------------------------|----------|---------|
| `-c`, `--config PATH`     | —        | Configuration file |
| `-f`, `--format FORMAT`   | `cli`    | `cli`, `json` or `sarif` |
| `-t`, `--threshold FLOAT` | `0.7`    | Similarity threshold, `0.0`–`1.0` |
| `--no-informational`      | off      | Suppress MEDIUM/LOW risk results |
| `-i`, `--ignore TEXT`     | —        | Ignore a package (repeatable) |

### Auto-discovered lockfiles

`Cargo.lock`, `Cargo.toml`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`,
`bun.lock`, `bun.lockb`, `requirements.txt`, `Pipfile.lock`, `poetry.lock`,
`uv.lock`, `pyproject.toml`, `go.sum`, `Gemfile.lock`, `composer.json`,
`composer.lock`, `Package.resolved`, `Package.swift`, `mix.lock`,
`build.gradle`, `build.gradle.kts`, `libs.versions.toml`.

Skipped directories: `.git`, `node_modules`, `vendor`, `.vendor`, `dist`,
`build`, `.cache`.

## `score`

```bash
taintrace score [OPTIONS] NAME
```

Score a single package name for typosquat risk, without needing a lockfile.

```bash
taintrace score proc-macro1
```

```
🚨 proc-macro1
Risk: CRITICAL | Score: 1.000
Similar to: proc-macro2, parking_lot, tracing-bunyan, tracing, tracing-subscriber
Reason: Near-identical to 'proc-macro2' – likely typosquat
```

A legitimate package scores clean:

```bash
taintrace score requests -e python
```

```
✅ requests — Known legitimate package
```

### `score` options

| Option                   | Default | Meaning |
|--------------------------|---------|---------|
| `-e`, `--ecosystem NAME` | `rust`  | `rust`, `node`, `python`, `go`, `ruby`, `php`, `swift`, `elixir`, `java` |

There is no `auto` here — `score` compares a bare name, so you name the
ecosystem yourself.

## Output formats

### `cli` (default)

A Rich panel with the dependency and suspect counts, then a table of suspects
with the top three matches and their similarity scores.

### `json`

```bash
taintrace check examples/reports/python/requirements.txt --format json
```

```json
{
  "tool": "taintrace",
  "version": "0.2.2",
  "summary": {
    "total": 1,
    "suspects": 1,
    "risk_levels": {
      "CRITICAL": 1,
      "HIGH": 0,
      "MEDIUM": 0
    }
  },
  "results": [
    {
      "package": "reqeusts",
      "version": "2.31.0",
      "risk_level": "CRITICAL",
      "risk_score": 1.0,
      "similar_to": ["requests", "mkdocs"],
      "similarity_scores": [
        {"package": "requests", "score": 1.0},
        {"package": "mkdocs", "score": 0.75}
      ],
      "reason": "Near-identical to 'requests' – likely typosquat"
    }
  ]
}
```

Every scanned dependency appears in `results`, not only the suspects — filter on
`risk_level` yourself if you want a short list. `summary.risk_levels` covers
`CRITICAL`, `HIGH` and `MEDIUM` only.

### `sarif`

```bash
taintrace check Cargo.lock --format sarif > taintrace.sarif
```

SARIF 2.1.0 with two rules — `TYPO001` (`TyposquatDetector`, default level
`error`) for names similar to a known package, and `TYPO002` (`UnknownPackage`,
default level `warning`) for names absent from the database. A finding is
`level: error` when its risk is `CRITICAL` or `HIGH`, otherwise `warning`.
Only suspects produce results; the artifact URI is the lockfile filename and the
region is line 1, column 1.

```json
{
  "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
  "version": "2.1.0",
  "runs": [
    {
      "tool": {
        "driver": {
          "name": "taintrace",
          "version": "0.2.2",
          "informationUri": "https://github.com/yunaremaia/taintrace"
        }
      },
      "results": [
        {
          "ruleId": "TYPO001",
          "level": "error",
          "message": {
            "text": "Near-identical to 'requests' – likely typosquat (score: 1.000)"
          },
          "locations": [
            {
              "physicalLocation": {
                "artifactLocation": {"uri": "requirements.txt"},
                "region": {"startLine": 1, "startColumn": 1}
              }
            }
          ]
        }
      ]
    }
  ]
}
```

## Exit codes

| Code | Meaning |
|------|---------|
| `0`  | No suspects found |
| `1`  | One or more suspects detected — the CI/CD gate |
| `2`  | `check` was invoked with no lockfile |

`scan-directory` returns `0` when it finds no lockfiles at all, so an empty
directory never fails a pipeline by accident.

## Ignoring false positives

```bash
taintrace check Cargo.lock --ignore proc-macro1 --ignore some-legit-package
```

Ignored packages are removed from the results before thresholding, so they do
not appear in `cli`, `json` or `sarif` output. For a persistent list, see
[Configuration](configuration.md).

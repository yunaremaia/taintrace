# CI

`taintrace` exits `1` when it finds a suspect, so the simplest gate is any CI
step that fails on a non-zero exit code.

```yaml
- run: pip install taintrace
- run: taintrace check Cargo.lock
```

## GitHub Action

The repo ships a composite action at `action.yml`.

```yaml
- uses: yunaremaia/taintrace@main
  with:
    lockfile: Cargo.lock
    format: sarif
    sarif-output: taintrace.sarif

- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: taintrace.sarif
```

Omit `lockfile` to auto-detect one in `path` (default `.`). The action tries
`Cargo.lock`, `package-lock.json`, `requirements.txt`, `go.sum`,
`pnpm-lock.yaml`, `yarn.lock` and `poetry.lock`, in that order; when none
exists it emits a warning and exits `0`, so adding the action to a repository
without a lockfile does not break the build.

### Inputs

| Input | Default | Meaning |
|-------|---------|---------|
| `lockfile` | `''` | Path to the lockfile to scan |
| `path` | `.` | Repository root, used when `lockfile` is empty |
| `format` | `cli` | `cli`, `json` or `sarif` |
| `threshold` | `0.7` | Similarity threshold, `0.0`–`1.0` |
| `ecosystem` | `auto` | Ecosystem name, or `auto` to detect from the filename |
| `sarif-output` | `taintrace.sarif` | Where the SARIF file is written |
| `fail-on-suspects` | `true` | Fail the step when suspects are found |

The action installs the published package from PyPI with `pip install
taintrace`; it does not run the checkout. Pin it to a tag (`@v0.2.2`) once you
are past evaluating it.

Set `fail-on-suspects: 'false'` to report without blocking:

```yaml
- uses: yunaremaia/taintrace@main
  with:
    format: sarif
    fail-on-suspects: 'false'
```

## GitHub Code Scanning

With `format: sarif` the action writes the SARIF file and uploads it with
`github/codeql-action/upload-sarif`, so findings appear in the Security tab
alongside CodeQL's. `TYPO001` (name resembles a known package) is uploaded as
an error, `TYPO002` (name absent from the database) as a warning.

Uploading manually is the same two steps:

```yaml
- run: pip install taintrace
- run: taintrace check Cargo.lock --format sarif > taintrace.sarif
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: taintrace.sarif
```

## Whole-repository scan

For a monorepo, `scan-directory` covers every lockfile in one run and prints a
per-file summary:

```yaml
- run: pip install taintrace
- run: taintrace scan-directory .
```

```yaml
- run: pip install taintrace
- run: taintrace scan-directory . --format sarif > taintrace.sarif
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: taintrace.sarif
```

## Pre-commit hook

```yaml
repos:
  - repo: https://github.com/yunaremaia/taintrace
    rev: v0.2.2
    hooks:
      - id: taintrace
```

The shipped hook runs `taintrace check --no-informational` on any of
`Cargo.lock`, `package-lock.json`, `requirements.txt`, `go.sum`,
`pnpm-lock.yaml`, `yarn.lock`, `poetry.lock`, `uv.lock`, `pyproject.toml`,
`Gemfile.lock`, `Pipfile.lock`, `bun.lock`, `bun.lockb`, `composer.json` and
`composer.lock`.

`--no-informational` is the right default for a commit hook: only `CRITICAL`
and `HIGH` findings block the commit, so an unfamiliar but plausible package
name cannot be committed while you think about it.

Project-specific ignores go in `.taintrace.toml` — the hook reads it
automatically, so no extra arguments are needed.

## Tuning for CI noise

CI databases are smaller than your laptop's lockfiles, and an unfamiliar private
package in a monorepo will show up as a suspect. Two levers, in order of
preference:

1. **Add an ignore entry.** `taintrace` only fails on what it is told to ignore:
   ```toml
   [taintrace]
   ignore = ["@acme-design-system", "acme-internal-sdk"]
   ```
2. **Raise the threshold** if you get findings that are genuinely unrelated:
   ```toml
   [taintrace]
   threshold = 0.85
   ```

Prefer ignores over `--no-informational` alone — suppressing a whole risk class
also suppresses real typosquats of that class.

## Next steps

- [Detection](detection.md) — what each risk level means
- [Configuration](configuration.md) — the `ignore` and `threshold` keys
- [Usage](usage.md) — exit codes and output formats

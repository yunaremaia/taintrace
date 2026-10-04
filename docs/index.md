# taintrace

**Typosquat detector for AI coding agent dependencies.**

`taintrace` scans your lockfiles for package names that suspiciously resemble
known legitimate packages — the vector used in the
[arrayref@0.3.10 attack](https://github.com/rustsec/advisory-db/pull/2045)
(August 2026), where `proc-macro1` imitated `proc-macro2` and executed
arbitrary code during `cargo build`.

AI coding agents install dependencies automatically. Typosquats pass
`cargo audit` / `npm audit` unnoticed because they have **no known CVE** — they
are brand-new packages with a malicious `build.rs` or proc-macro. Those scanners
check *known-bad*. `taintrace` checks *suspicious-similar*.

## I want to…

| I want to…                        | Do this                                                              |
|-----------------------------------|----------------------------------------------------------------------|
| Scan one lockfile                 | [`taintrace check Cargo.lock`](getting-started.md#scan-a-lockfile)  |
| Scan every lockfile in a repo     | [`taintrace scan-directory .`](usage.md#scan-directory)               |
| Gate a pipeline on typosquats     | Use the exit code (`1` = suspects) — see [CI](ci.md)                 |
| Publish findings to Code Scanning | `--format sarif` — see [CI](ci.md#github-code-scanning)               |
| Consume results as JSON           | `--format json` — see [Usage](usage.md#output-formats)               |
| Check one package name            | [`taintrace score proc-macro1`](usage.md#score)                      |
| Suppress a known false positive   | `--ignore` / `.taintrace.toml` — see [Configuration](configuration.md) |
| Use it from Python                | See the [API Reference](api.md)                                      |

## Install

```bash
pip install taintrace
```

Requires Python 3.10 or newer. No API keys, no network calls — the
known-package database ships inside the package.

## Sixty-second run

Given this `Cargo.lock`:

```toml
version = 3

[[package]]
name = "proc-macro1"
version = "0.3.10"

[[package]]
name = "serde"
version = "1.0.0"
```

```bash
taintrace check Cargo.lock
```

```
╭──────────────────────────────────────────────────── Scan Results ────────────────────────────────────────────────────╮
│ taintrace v0.2.2 — scanning Cargo.lock                                                                               │
│ Total deps: 2 | Suspects: 1                                                                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
                                                 🚨 Typosquat Suspects
┏━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Package     ┃ Risk     ┃ Score ┃ Similar To                               ┃ Reason                                   ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ proc-macro1 │ CRITICAL │  1.00 │ proc-macro2 (1.00), parking_lot (1.00),  │ Near-identical to 'proc-macro2' – likely │
│             │          │       │ tracing-log (0.75)                       │ typosquat                                │
└─────────────┴──────────┴───────┴──────────────────────────────────────────┴──────────────────────────────────────────┘

❌ 1 suspect(s) found — review required
```

Exit code `0` means clean, `1` means suspects were found.

## Supported ecosystems

Nine ecosystems are covered. The ecosystem is detected from the lockfile
filename unless you pass `--ecosystem`:

| Ecosystem | Lockfiles                                                                                   |
|-----------|---------------------------------------------------------------------------------------------|
| Rust      | `Cargo.lock`, `Cargo.toml`                                                                  |
| Node.js   | `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lock`, `bun.lockb`                   |
| Python    | `requirements.txt`, `poetry.lock`, `pyproject.toml`, `uv.lock`, `Pipfile.lock`                |
| Go        | `go.sum`                                                                                    |
| Ruby      | `Gemfile.lock`                                                                              |
| PHP       | `composer.json`, `composer.lock`                                                            |
| Swift     | `Package.resolved`, `Package.swift`                                                         |
| Elixir    | `mix.lock`                                                                                  |
| Gradle    | `build.gradle`, `build.gradle.kts`, `gradle/libs.versions.toml`                               |

Similarity suggestions come from a built-in, offline database: curated lists in
`taintrace/db.py` for Rust, Node.js, Python, Go, Ruby, PHP, Swift and Elixir,
plus 7,848 `groupId:artifactId` coordinates in
`src/taintrace/data/java_packages.txt` generated from the Maven Central index.

## Where to go next

- [Getting Started](getting-started.md) — install and first run
- [Usage](usage.md) — every CLI flag
- [Detection](detection.md) — how the score is actually computed
- [Configuration](configuration.md) — config discovery, keys, ignore lists
- [CI](ci.md) — GitHub Action, pre-commit hook, SARIF upload
- [Example typosquat reports](https://github.com/yunaremaia/taintrace/tree/main/examples/reports)
  — runnable fixtures for `reqeusts`, `lodahs` and `raills`

## Links

- [Source on GitHub](https://github.com/yunaremaia/taintrace)
- [Issues](https://github.com/yunaremaia/taintrace/issues)
- [Changelog](https://github.com/yunaremaia/taintrace/blob/main/CHANGELOG.md)
- [PyPI](https://pypi.org/project/taintrace/)
- [Contributing](https://github.com/yunaremaia/taintrace/blob/main/CONTRIBUTING.md)
- MIT licensed

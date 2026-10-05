# Changelog

All notable changes to taintrace will be documented in this file.

## [Unreleased]

## [0.2.5] - 2026-10-05

### Added
- **Verified Python 3.13 support.** The `Programming Language :: Python :: 3.13`
  classifier is published and a 3.13 leg joins the CI test matrix
  (now 3.10 / 3.11 / 3.12 / 3.13 / 3.14). The classifiers skipped 3.13 entirely,
  so PyPI's version filter hid taintrace from anyone filtering by the Python
  they actually run — the package installed fine and simply did not appear. The
  classifier is only correct because the full suite was run on CPython 3.13.16
  first: 426 passed, 1 skipped, 100% coverage.

- **`test_the_declared_versions_are_a_contiguous_run` derives the expected
  version set instead of listing it.** The existing matrix/classifier agreement
  test compares two hand-maintained lists, so it cannot notice a version missing
  from *both* — which is exactly how 3.13 shipped unclassified with a green
  suite. The new test builds the expected run from the `requires-python` floor
  up to the highest declared classifier, so dropping any version between the two
  ends fails it.

## [0.2.4] - 2026-10-05

### Added
- **Verified Python 3.14 support.** The `Programming Language :: Python :: 3.14`
  classifier is published and a 3.14 leg joins the CI test matrix
  (now 3.10 / 3.11 / 3.12 / 3.14). 3.14 is the current stable release, so PyPI's
  version filter was hiding taintrace from anyone filtering by the Python they
  actually run — the package installed fine and simply did not appear. The
  classifier is only correct because the full suite was run on CPython 3.14.7
  first: 425 passed, 1 skipped, 100% coverage.

- **A guard against the matrix and the classifiers drifting apart.**
  `tests/test_pypi_metadata.py` asserts the CI `python-version` list and the
  `Programming Language :: Python :: 3.x` classifiers are the same set, in both
  directions. Both were hand-maintained with nothing enforcing agreement, which
  is how 3.14 went unclassified and untested while `requires-python = ">=3.10"`
  quietly claimed it. A second test asserts the interpreter the suite is
  currently running on is one the project claims — the one claim that is always
  checkable from the inside.

### Fixed
- **`test_scoring_a_large_java_data_set_stays_fast` no longer fails on a loaded
  machine.** It measured a single run against a 5-second budget with only ~4x
  headroom over the real ~1.1s cost, so any CI runner that lost the CPU for a few
  seconds read as a slow scanner. It now takes the minimum of three runs — the
  minimum is the scan's own cost, the maximum is mostly a neighbour's — against a
  10-second budget. The guard is still load-bearing: reverting the Levenshtein
  comparison to the textbook pure-Python matrix measures 56.7s and fails it.

## [0.2.3] - 2026-10-04

### Fixed
- **`Homepage` now points at the published documentation site**
  (`https://yunaremaia.github.io/taintrace/`) instead of the bare repository,
  and a **`Documentation`** entry was added pointing at the first guide
  (`https://yunaremaia.github.io/taintrace/getting-started/`). Both URLs were
  verified to return HTTP 200 before being written down.

  0.2.2 made this choice deliberately: "`Homepage` deliberately stays on the
  repository: no docs site is deployed for this repo, so a `Documentation` link
  pointing at the unserved `docs/` directory would be dead on the project's most
  visible page." The reasoning was sound and the premise then expired — the
  mkdocs site shipped in `aa7caaa`, after the v0.2.2 tag — leaving the most
  prominent slot on the landing page pointing at a README while a 20-page
  documentation site went unlinked. PyPI is the only channel this project
  currently converts through, so a wasted slot there is a wasted slot.

  The repository is still linked, under `Source`, `Issues` and `Changelog`.
  `Documentation` deep-links rather than repeating the site root, so the landing
  page does not advertise one URL under two names.

- `DetectionResult.dependency` was annotated as the string `'Dependency'`
  while the name was never imported at module scope, so the annotation was
  unresolvable: `typing.get_type_hints(DetectionResult)` raised `NameError`.
  Consumers that introspect the dataclass at runtime (serializers, schema
  generators) hit that error. The annotation now resolves.

### Added
- A ruff (`F` / pyflakes) lint gate in CI. The repo previously had no
  linter, which is how the annotation bug above survived undetected.

- **Regression guard for the discovery metadata.**
  `tests/test_pypi_metadata.py` now pins `Homepage` to the published site,
  requires a `Documentation` entry that is a real page of that site and distinct
  from `Homepage`, and asserts `mkdocs.yml`'s `site_url` agrees with both. The
  metadata is parsed with `tomllib` and the mkdocs config as text, so the guard
  needs no dependency the `test` job does not install — the failure mode it
  guards is silent by construction: a wrong URL in `pyproject.toml` raises
  nothing anywhere, it just wastes a slot.

### Removed
- Four unused imports (`Text`, `RiskLevel`, `List`, `Tuple`) found by the new
  gate.

## [0.2.2] - 2026-10-03

### Added
- A PyPI downloads badge in the README, linking to the project page.
- `Source` added to `[project.urls]`, and new discovery keywords:
  `typosquatting`, `dependency-confusion`, `package-name`, `pypi`, `npm`,
  `maven`. The terms people actually search were previously absent.

## [0.2.0] - 2026-09-11

### Added
- Initial release: typosquat detector for AI coding agent dependencies
- Multi-ecosystem lockfile parsing (Cargo.lock, package-lock.json, requirements.txt, go.sum, pnpm-lock.yaml, yarn.lock, poetry.lock)
- Fuzzy matching (Levenshtein + Soundex + substring) with risk scoring
- CLI, JSON, and SARIF output formats
- GitHub Actions composite action + Code Scanning integration
- Pre-commit hook support

### Added (2026-09-12)
- Integrated into driftcheck v0.1.44 as typosquat drift detector

# Changelog

All notable changes to taintrace will be documented in this file.

## [Unreleased]

### Fixed
- `DetectionResult.dependency` was annotated as the string `'Dependency'`
  while the name was never imported at module scope, so the annotation was
  unresolvable: `typing.get_type_hints(DetectionResult)` raised `NameError`.
  Consumers that introspect the dataclass at runtime (serializers, schema
  generators) hit that error. The annotation now resolves.

### Added
- A ruff (`F` / pyflakes) lint gate in CI. The repo previously had no
  linter, which is how the annotation bug above survived undetected.

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

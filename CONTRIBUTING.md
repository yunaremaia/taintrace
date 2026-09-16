# Contributing to taintrace

Thanks for helping improve taintrace. This guide covers the local development workflow and what to include in a pull request.

## Development setup

Taintrace supports Python 3.10 and newer. Create a virtual environment, activate it, and install the project with its development dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## Running tests

Run the complete test suite before submitting a change:

```bash
pytest
```

During development, you can run a focused test file first, for example:

```bash
pytest tests/test_similarity.py
```

## Code style

Keep changes focused and follow the style of the surrounding code. Add or update tests for behavior changes, use clear names, and keep public-facing documentation in sync with user-visible behavior.

Before committing, run the tests and review your diff for unrelated changes:

```bash
pytest
git diff --check
```

## Pull request process

1. Create a descriptive branch, such as `fix/package-parser` or `docs/contributing-guide`.
2. Make focused commits with short, imperative messages, such as `fix: parse scoped package names`.
3. Add tests for code changes and update documentation when behavior changes.
4. Open a pull request that explains the problem, the approach, and how you validated the change.
5. Address review feedback with additional commits. Maintainers may ask for changes before merging.

For larger changes, open or reference an issue first so the approach can be discussed before substantial implementation work begins.

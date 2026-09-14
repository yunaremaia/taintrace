# Contributing to taintrace

Thank you for your interest in contributing to `taintrace`! We welcome contributions to improve typosquat detection, add new package registries/ecosystems, support more lockfile formats, and enhance documentation.

---

## 1. Development Setup

`taintrace` requires **Python 3.10** or higher.

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/<your-username>/taintrace.git
   cd taintrace
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv .venv

   # Linux / macOS:
   source .venv/bin/activate

   # Windows:
   .venv\Scripts\activate
   ```

3. **Install editable package with dev dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -e ".[dev]"
   ```

---

## 2. Running Tests

We use `pytest` for unit and integration testing. Run the test suite with:

```bash
pytest tests/ -v
```

To run with coverage reporting:
```bash
pytest tests/ --cov=src/taintrace
```

---

## 3. Code Style

- Keep changes aligned with the existing codebase style in `src/taintrace/`.
- Use type hints wherever appropriate.
- Keep dependencies minimal; `taintrace` relies on `click`, `rich`, and `rapidfuzz` for speed and offline operation.
- Write clean docstrings and descriptive commit messages.

---

## 4. Adding a New Lockfile Parser

Adding support for new lockfiles or package manifests is one of the most common contributions:

1. **Implement the parser in `src/taintrace/lockfile.py`:**
   - Define a parsing method on `LockfileParser` (e.g. `_parse_myformat(self, path: Path) -> List[Dependency]`).
   - Extract dependency names, versions, and specify the `ecosystem` string.
   - Register the file name and parser function in `EXTENDED_FORMATS` in `src/taintrace/lockfile.py`:
     ```python
     EXTENDED_FORMATS = {
         ...
         "myformat.lock": ("ecosystem_name", "_parse_myformat"),
     }
     ```
   - Update `LockfileParser.parse()` if special dispatch logic is needed.

2. **Register any new ecosystem in `src/taintrace/db.py`:**
   - If the parser introduces a new ecosystem, add it to `KnownPackagesDB.__init__()` and define its known package set.

3. **Add automated tests in `tests/`:**
   - Create `tests/test_<format>_parsers.py` with valid, empty, and edge-case lockfile samples.
   - Ensure tests pass with `pytest tests/ -v`.

4. **Update the README ecosystem table:**
   - Update the supported formats table in `README.md` to reflect support for the new lockfile.

---

## 5. Adding Known Legitimate Packages

To avoid false positives on popular packages:
1. Open `src/taintrace/db.py`.
2. Locate the corresponding ecosystem set (e.g., `_PYTHON_PACKAGES`, `_NODE_PACKAGES`, `_RUST_PACKAGES`, etc.).
3. Add the canonical package name in lowercase.
4. Run `pytest tests/` to ensure similarity matching and risk scoring behave as expected.

---

## 6. Release Process

For project maintainers releasing new versions:
1. Bump the version string in `pyproject.toml` and any version constants.
2. Update `CHANGELOG.md` with the new version section and summary of changes.
3. Commit the changes: `git commit -m "Release vX.Y.Z"`.
4. Tag the release: `git tag vX.Y.Z && git push --tags`.
5. Build distributions and publish to PyPI:
   ```bash
   python -m build
   twine upload dist/*
   ```

---

## 7. Submitting a Pull Request

1. Create a descriptive feature branch: `git checkout -b feat/my-new-feature` or `fix/my-bugfix`.
2. Ensure all tests pass locally.
3. Open a pull request against the `main` branch with a clear summary of your changes and reference any related issues (e.g., `Closes #123`).

"""Unit tests for the logic inside the packaging-contract guard itself.

``tests/test_declared_dependencies.py`` runs the guard against this repository,
once, and asserts the result is clean. That proves nothing about the guard: a
guard whose ``third_party_imports()`` always returned an empty set would pass
it forever while silently stopping to guard anything.

These tests drive the helper functions directly against synthetic package
trees, so each rule the guard is supposed to enforce is asserted in isolation:

- a repo without a ``src/`` layout is still walked;
- a repo that declares no dependencies at all is read as an empty list;
- an import nested in a function body or a ``TYPE_CHECKING`` block is found,
  because that is where ``config.py`` actually imports ``yaml`` and ``tomli``;
- a relative import is first-party and never reported as a dependency;
- a declared-but-never-imported dependency is reported in the reverse
  direction, not just the missing-declaration one;
- ``tomllib`` and ``tomli`` are one dependency spelled two ways, in BOTH
  directions, and ``tomllib`` counts as stdlib even on 3.10 where it is
  absent from ``sys.stdlib_module_names``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

import test_declared_dependencies as guard


@pytest.fixture
def synthetic_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Build a throwaway package tree and point the guard at it."""

    def build(
        sources: dict[str, str],
        dependencies: list[str] | None = None,
        layout: str = "src",
        module_name: str = guard.MODULE_NAME,
    ) -> Path:
        if layout == "src":
            package_root = tmp_path / "src" / module_name
        else:
            package_root = tmp_path / module_name
        package_root.mkdir(parents=True, exist_ok=True)
        (package_root / "__init__.py").write_text("", encoding="utf-8")
        for relative, body in sources.items():
            target = package_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")

        deps = dependencies if dependencies is not None else []
        rendered = ",\n".join(f'    "{dep}"' for dep in deps)
        (tmp_path / "pyproject.toml").write_text(
            "[project]\n"
            'name = "synthetic"\n'
            "dependencies = [\n"
            f"{rendered}\n"
            "]\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(guard, "PACKAGE_ROOT", package_root)
        monkeypatch.setattr(guard, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(guard, "MODULE_NAME", module_name)
        return package_root

    return build


class TestRepositoryLayout:
    """The guard must not assume this repository's own shape."""

    def test_a_repo_without_a_src_layout_is_still_walked(
        self, synthetic_repo
    ) -> None:
        """Flat layout: the package sits at the repo root, not under src/."""
        synthetic_repo(
            {"mod.py": "import yaml\n"},
            dependencies=["pyyaml>=6.0"],
            layout="flat",
        )

        assert guard.third_party_imports() == {"yaml"}

    def test_a_package_with_no_subpackages_is_handled(
        self, synthetic_repo
    ) -> None:
        """A single-module package has no subpackage directories to collect."""
        synthetic_repo({"only.py": "import rapidfuzz\n"}, dependencies=["rapidfuzz"])

        assert guard.third_party_imports() == {"rapidfuzz"}

    def test_a_subpackage_name_is_not_reported_as_a_dependency(
        self, synthetic_repo
    ) -> None:
        """First-party subpackages must not leak into the third-party set."""
        synthetic_repo(
            {
                "lockfile/__init__.py": "",
                "lockfile/parser.py": "import click\nimport rapidfuzz\n",
            },
            dependencies=["click", "rapidfuzz"],
        )

        assert guard.third_party_imports() == {"click", "rapidfuzz"}

    def test_a_repo_declaring_no_dependencies_yields_an_empty_declared_set(
        self, synthetic_repo
    ) -> None:
        """No ``dependencies`` entries means nothing is declared, not a crash."""
        synthetic_repo({"mod.py": "import click\n"}, dependencies=[])

        assert guard.read_pyproject_dependencies() == []
        assert guard.declared_import_names() == set()

    def test_a_repo_with_no_declared_dependencies_reports_every_import(
        self, synthetic_repo
    ) -> None:
        """The missing-declaration direction must fire when nothing is declared."""
        synthetic_repo({"mod.py": "import click\nimport yaml\n"}, dependencies=[])

        assert guard.third_party_imports() - guard.declared_import_names() == {
            "click",
            "yaml",
        }


class TestImportDiscovery:
    """Which import statements count as a dependency."""

    def test_an_import_inside_a_function_is_found(self, synthetic_repo) -> None:
        """This is where config.py imports yaml and tomli, so it must count."""
        synthetic_repo(
            {
                "mod.py": (
                    "def read_config(path):\n"
                    "    import yaml\n"
                    "    return yaml.safe_load(path)\n"
                )
            },
            dependencies=["pyyaml>=6.0"],
        )

        assert guard.third_party_imports() == {"yaml"}

    def test_an_import_in_a_type_checking_block_is_found(self, synthetic_repo) -> None:
        """A TYPE_CHECKING-only import is still a dependency of the source file."""
        synthetic_repo(
            {
                "mod.py": (
                    "from typing import TYPE_CHECKING\n"
                    "if TYPE_CHECKING:\n"
                    "    import rapidfuzz\n"
                )
            },
            dependencies=["rapidfuzz"],
        )

        assert guard.third_party_imports() == {"rapidfuzz"}

    def test_a_relative_import_is_not_a_dependency(self, synthetic_repo) -> None:
        """``from . import x`` is first-party; ``level > 0`` is what says so."""
        synthetic_repo(
            {"mod.py": "from . import sibling\nfrom .helpers import thing\n"},
            dependencies=[],
        )

        assert guard.third_party_imports() == set()

    def test_a_dotted_relative_import_is_not_a_dependency(
        self, synthetic_repo
    ) -> None:
        synthetic_repo({"mod.py": "from ..shared import util\n"}, dependencies=[])

        assert guard.third_party_imports() == set()

    def test_a_stdlib_import_is_not_a_dependency(self, synthetic_repo) -> None:
        synthetic_repo({"mod.py": "import json\nimport os\nimport re\n"}, dependencies=[])

        assert guard.third_party_imports() == set()

    def test_a_dev_only_import_is_not_a_dependency(self, synthetic_repo) -> None:
        """Test tooling lives in the dev extra and is never a runtime dependency."""
        synthetic_repo({"mod.py": "import pytest\nimport coverage\n"}, dependencies=[])

        assert guard.third_party_imports() == set()

    def test_a_dotted_import_is_reported_by_its_top_level_name(
        self, synthetic_repo
    ) -> None:
        """``import yaml.parser`` names the distribution ``pyyaml``."""
        synthetic_repo({"mod.py": "import yaml.parser\n"}, dependencies=["pyyaml"])

        assert guard.third_party_imports() == {"yaml"}


class TestVersionSpecifierParsing:
    """Declared specs are turned into import names."""

    def test_the_common_operator_forms_are_all_stripped(self) -> None:
        """A version pin must not leak into the name, whatever the operator."""
        expected = {"click"}
        specs = [
            "click",
            "click>=8.1",
            "click>8.1",
            "click<9",
            "click==8.1.7",
            "click!=8.0",
            "click~=8.1",
            "click[extra]>=8.1",
            "click >= 8.1",
        ]
        for spec in specs:
            assert guard.declared_import_names_for([spec]) == expected, spec

    def test_a_marker_expression_is_discarded(self) -> None:
        """The ``;`` environment marker is not part of the distribution name."""
        assert guard.declared_import_names_for(
            ["click>=8.1; python_version < '3.13'"]
        ) == {"click"}

    def test_a_direct_reference_url_is_stripped(self) -> None:
        """``name @ url`` is PEP 508 direct syntax; the name is what matters.

        Written without a space around the ``@`` so this test actually pins the
        ``@`` entry in the separator list. With a space, the ``" "`` entry
        splits the spec first and the ``@`` branch is never exercised, so
        deleting ``"@"`` from the separator list would leave this test green.
        """
        assert guard.declared_import_names_for(
            ["rich@https://example.invalid/rich.whl"]
        ) == {"rich"}
        assert guard.declared_import_names_for(
            ["rich @ https://example.invalid/rich.whl"]
        ) == {"rich"}

    def test_name_separators_are_normalised(self) -> None:
        """Distribution names may spell separators as ``-``, ``_`` or ``.``."""
        assert guard.declared_import_names_for(["zope.interface"]) == {"zope-interface"}
        assert guard.declared_import_names_for(["some_pkg"]) == {"some-pkg"}
        assert guard.declared_import_names_for(["Some-Dist"]) == {"some-dist"}

    def test_a_distribution_and_import_name_that_differ_is_mapped(
        self,
    ) -> None:
        """``pyyaml`` is declared, ``yaml`` is imported."""
        assert guard.declared_import_names_for(["pyyaml>=6.0"]) == {"yaml"}

    def test_an_empty_spec_contributes_no_name(self) -> None:
        """A stray separator must not add an empty name to the set."""
        assert guard.declared_import_names_for(["", "  ", "click"]) == {"click"}


class TestTomlTomliAliasing:
    """``tomllib`` and ``tomli`` are one dependency spelled two ways."""

    def test_canonical_maps_both_spellings_to_one_name(self) -> None:
        assert guard.canonical("tomllib") == "tomllib"
        assert guard.canonical("tomli") == "tomllib"

    def test_other_names_are_left_alone(self) -> None:
        assert guard.canonical("yaml") == "yaml"
        assert guard.canonical("tomli_w") == "tomli_w"

    def test_declaring_tomli_satisfies_a_tomllib_import(self) -> None:
        """Python 3.11+ imports stdlib tomllib; the backport is what is declared."""
        assert guard.declared_import_names_for(
            ["tomli>=2.0; python_version < '3.11'"]
        ) == {"tomllib"}

    def test_declaring_tomllib_satisfies_a_tomli_import(self) -> None:
        """The aliasing has to work in both directions, not just this one."""
        assert guard.declared_import_names_for(["tomllib"]) == {"tomllib"}
        assert guard.canonical("tomli") in guard.declared_import_names_for(["tomllib"])

    def test_tomllib_counts_as_stdlib_even_where_it_is_not_yet_stdlib(
        self,
    ) -> None:
        """3.10 has no tomllib, so the guard adds it to the stdlib set itself.

        Without that, a source tree importing stdlib tomllib would be reported
        as missing a dependency on every 3.10 run and the guard would be
        unusable on the oldest interpreter it supports. Asserted against
        ``stdlib_import_names()`` rather than ``sys.stdlib_module_names``, so
        the check holds on 3.11+ too -- otherwise it would only ever run on the
        one interpreter where the addition is a no-op.
        """
        assert "tomllib" in guard.stdlib_import_names()
        assert "tomli_w" in guard.stdlib_import_names()

    def test_the_stdlib_set_is_a_superset_of_the_running_interpreters_stdlib(
        self,
    ) -> None:
        assert guard.stdlib_import_names() >= set(sys.stdlib_module_names)

    def test_a_tomllib_import_is_not_reported_on_this_interpreter(
        self, synthetic_repo
    ) -> None:
        """The realistic 3.11+ shape: import tomllib, declare tomli."""
        if "tomllib" not in sys.stdlib_module_names:
            pytest.skip("tomllib is stdlib only on 3.11+")
        synthetic_repo(
            {"mod.py": "import tomllib\n"},
            dependencies=["tomli>=2.0; python_version < '3.11'"],
        )

        assert guard.third_party_imports() - guard.declared_import_names() == set()

    def test_a_tomli_import_is_satisfied_by_a_tomli_declaration(
        self, synthetic_repo
    ) -> None:
        """The 3.10 shape: the try/except falls back to importing tomli."""
        synthetic_repo(
            {"mod.py": "import tomli\n"}, dependencies=["tomli>=2.0"]
        )

        assert guard.third_party_imports() - guard.declared_import_names() == set()
        assert guard.declared_import_names() - guard.third_party_imports() == set()


class TestBothDirections:
    """The guard asserts two independent facts; each needs its own evidence."""

    def test_an_undeclared_import_is_reported(
        self, synthetic_repo
    ) -> None:
        """Direction one: imported but not declared."""
        synthetic_repo({"mod.py": "import yaml\n"}, dependencies=["click"])

        assert guard.third_party_imports() - guard.declared_import_names() == {"yaml"}

    def test_a_declared_but_unimported_dependency_is_reported(
        self, synthetic_repo
    ) -> None:
        """Direction two: declared but never imported.

        This is the reverse check the real guard makes in
        ``test_every_declared_dependency_is_imported``; a guard that only ever
        looked one way would pass a repository carrying dead dependencies.
        """
        synthetic_repo({"mod.py": "import click\n"}, dependencies=["click", "rapidfuzz"])

        assert guard.declared_import_names() - guard.third_party_imports() == {
            "rapidfuzz"
        }

    def test_the_310_text_parser_agrees_with_tomllib(
        self, synthetic_repo
    ) -> None:
        """3.10 has no tomllib, so the guard falls back to parsing text.

        That fallback is what actually reads ``pyproject.toml`` on the oldest
        interpreter the project supports, and it only runs there -- nothing
        would notice it drifting out of step with the tomllib path until a 3.10
        CI run disagreed with the other two legs. Both paths are computed here
        from the same file and required to be equal.
        """
        synthetic_repo(
            {"mod.py": "import click\nimport yaml\n"},
            dependencies=["click>=8.1", "pyyaml>=6.0"],
        )
        text = (guard.REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

        # The exact expression from read_pyproject_dependencies' 3.10 branch.
        body = text.split("dependencies = [", 1)[1].split("]", 1)[0]
        via_text = [
            line.strip().strip('",')
            for line in body.splitlines()
            if line.strip().startswith('"')
        ]

        assert via_text == ["click>=8.1", "pyyaml>=6.0"]
        assert guard.declared_import_names_for(via_text) == {
            "click",
            "yaml",
        }

    def test_the_shipped_pyproject_is_read_identically_on_both_paths(
        self,
    ) -> None:
        """Same equivalence, against the real pyproject this guard enforces."""
        if guard.tomllib is None:
            pytest.skip("running on 3.10: only the text path is available here")
        text = (guard.REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        via_tomllib = list(guard.tomllib.loads(text)["project"]["dependencies"])

        body = text.split("dependencies = [", 1)[1].split("]", 1)[0]
        via_text = [
            line.strip().strip('",')
            for line in body.splitlines()
            if line.strip().startswith('"')
        ]

        assert via_text == via_tomllib

    def test_a_fully_consistent_tree_reports_nothing_in_either_direction(
        self, synthetic_repo
    ) -> None:
        synthetic_repo(
            {"mod.py": "import click\nimport yaml\n"},
            dependencies=["click>=8.1", "pyyaml>=6.0"],
        )

        assert guard.third_party_imports() - guard.declared_import_names() == set()
        assert guard.declared_import_names() - guard.third_party_imports() == set()


class TestVersionFallbackGuards:
    """The AST helpers that protect the version contract."""

    @staticmethod
    def _parse(source: str) -> ast.AST:
        return ast.parse(source)

    def test_a_literal_version_inside_the_handler_is_allowed(self) -> None:
        tree = self._parse(
            "try:\n"
            "    __version__ = version('pkg')\n"
            "except PackageNotFoundError:\n"
            "    __version__ = '0.0.0.dev0'\n"
        )

        assert guard._package_not_found_fallback_lines(tree) == {4}

    def test_a_literal_version_at_module_level_is_not_allowed(self) -> None:
        tree = self._parse("__version__ = '1.2.3'\n")

        assert guard._package_not_found_fallback_lines(tree) == set()

    def test_a_tuple_handler_is_recognised(self) -> None:
        """``except (ImportError, PackageNotFoundError):`` is the same contract."""
        tree = self._parse(
            "try:\n"
            "    __version__ = version('pkg')\n"
            "except (ImportError, PackageNotFoundError):\n"
            "    __version__ = '0.0.0.dev0'\n"
        )

        assert guard._package_not_found_fallback_lines(tree) == {4}

    def test_a_handler_for_a_different_exception_does_not_guard(self) -> None:
        tree = self._parse(
            "try:\n"
            "    __version__ = version('pkg')\n"
            "except ValueError:\n"
            "    __version__ = '0.0.0.dev0'\n"
        )

        assert guard._package_not_found_fallback_lines(tree) == set()

    def test_an_annotated_target_is_still_a_version_assignment(self) -> None:
        """``__version__: str = ...`` assigns the name just the same."""
        tree = self._parse(
            "try:\n"
            "    pass\n"
            "except PackageNotFoundError:\n"
            "    __version__: str = '0.0.0.dev0'\n"
        )

        assert guard._package_not_found_fallback_lines(tree) == {4}

    def test_a_plain_assignment_and_an_annotated_one_are_both_literals(
        self,
    ) -> None:
        """A type annotation does not make a version literal any safer.

        Both spellings are collected, and the reported kind distinguishes them so
        the failure message names the form that was actually found.
        """
        found = guard._version_literal_assignments(
            self._parse(
                "__version__: str = '1.2.3'\n"
                "other = 'not the version'\n"
                "elsewhere = 42\n"
            )
        )

        assert found == [(1, "annotated assignment")]

    def test_an_unannotated_literal_is_reported_as_an_assignment(self) -> None:
        found = guard._version_literal_assignments(
            self._parse("__version__ = '1.2.3'\n")
        )

        assert found == [(1, "assignment")]

    def test_a_computed_version_is_not_a_literal(self) -> None:
        """A value derived from metadata is the whole point; not a defect."""
        found = guard._version_literal_assignments(
            self._parse("__version__ = version('pkg')\n")
        )

        assert found == []

    def test_a_non_string_constant_is_not_a_version_literal(self) -> None:
        found = guard._version_literal_assignments(self._parse("__version__ = 3\n"))

        assert found == []

    def test_a_guarded_literal_is_not_reported_as_stale(self) -> None:
        """The two helpers compose: guarded lines are excluded from ``stale``."""
        tree = self._parse(
            "try:\n"
            "    __version__ = version('pkg')\n"
            "except PackageNotFoundError:\n"
            "    __version__ = '0.0.0.dev0'\n"
        )
        guarded = guard._package_not_found_fallback_lines(tree)

        stale = [
            found
            for found in guard._version_literal_assignments(tree)
            if found[0] not in guarded
        ]

        assert stale == []

    def test_an_unguarded_annotated_literal_is_reported_as_stale(self) -> None:
        """The composed check catches the annotated form at module level."""
        tree = self._parse("__version__: str = '1.2.3'\n")
        guarded = guard._package_not_found_fallback_lines(tree)

        stale = [
            found
            for found in guard._version_literal_assignments(tree)
            if found[0] not in guarded
        ]

        assert stale == [(1, "annotated assignment")]

    def test_this_repository_has_no_undeclared_import(self) -> None:
        """The real guard, re-asserted here so a break is visible in two files."""
        assert guard.third_party_imports() - guard.declared_import_names() == set()

    def test_this_repository_declares_nothing_unused(self) -> None:
        assert guard.declared_import_names() - guard.third_party_imports() == set()

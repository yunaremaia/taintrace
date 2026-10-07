"""Parser edge cases: malformed and unusual input for every lockfile format.

The existing parser tests feed each format a well-formed file. These tests feed
the ones the parsers are explicitly written to tolerate -- comments, blank
lines, unknown keys, wrong types, non-object entries -- because every one of
those guards is a line of code that would otherwise never run.
"""

from __future__ import annotations

import re
from pathlib import Path

from taintrace.lockfile import LockfileParser


def _write(tmp_path: Path, name: str, content: str) -> Path:
    target = tmp_path / name
    target.write_text(content, encoding="utf-8")
    return target


def _names(deps) -> list[str]:
    return [dep.name for dep in deps]


class TestDispatch:
    def test_unknown_filename_falls_back_to_the_cargo_parser(self, tmp_path: Path) -> None:
        """An unrecognised name is read as a Cargo.lock rather than failing."""
        lockfile = _write(
            tmp_path,
            "mystery.lock",
            '[[package]]\nname = "serde"\nversion = "1.0.0"\n',
        )

        deps = LockfileParser().parse(lockfile)

        assert [(d.name, d.ecosystem) for d in deps] == [("serde", "rust")]

    def test_dispatch_is_case_insensitive(self, tmp_path: Path) -> None:
        lockfile = _write(
            tmp_path, "CARGO.LOCK", '[[package]]\nname = "serde"\nversion = "1.0.0"\n'
        )

        assert _names(LockfileParser().parse(lockfile)) == ["serde"]


class TestYarn:
    def test_quoted_specs_comments_and_missing_at_sign_are_skipped(self, tmp_path: Path) -> None:
        """A quoted entry header cannot be split, so it is skipped, not guessed at.

        ``spec_match`` requires the whole first line to be one quoted or bare
        spec, so ``"@scope/pkg@npm:1.0.0":`` (trailing colon, inner quotes) and a
        header with no ``@`` are both dropped.
        """
        lockfile = _write(
            tmp_path,
            "yarn.lock",
            "# yarn lockfile v1\n"
            "\n"
            "\n"
            '"@scope/pkg@npm:1.0.0":\n'
            '  version "1.0.0"\n'
            "\n"
            "no-at-sign:\n"
            '  version "9.9.9"\n',
        )

        assert LockfileParser().parse(lockfile) == []

    def test_workspace_protocol_entries_are_skipped(self, tmp_path: Path) -> None:
        lockfile = _write(
            tmp_path,
            "yarn.lock",
            "local-pkg@workspace:packages/local-pkg:\n"
            '  version "0.0.0-use.local"\n',
        )

        assert LockfileParser().parse(lockfile) == []

    def test_block_without_a_version_line_falls_back_to_the_header_spec(
        self, tmp_path: Path
    ) -> None:
        """With no ``version "..."`` line the header spec is used as the version.

        The trailing colon on the header is the key separator, not part of the
        descriptor, so it is not carried into the version.
        """
        lockfile = _write(tmp_path, "yarn.lock", "serde@^1.0:\n  resolved \"x\"\n")

        assert [(d.name, d.version) for d in LockfileParser().parse(lockfile)] == [
            ("serde", "^1.0")
        ]

    def test_a_whitespace_only_block_is_skipped(self, tmp_path: Path) -> None:
        """Blocks are split on blank lines, so a line of spaces is one too.

        It is not a valid entry header, but it must be discarded rather than
        parsed: the blocks either side of it still yield their dependency.
        """
        lockfile = _write(
            tmp_path,
            "yarn.lock",
            'serde@^1.0:\n  version "1.0.0"\n\n   \n\nflask@^2.0:\n  version "2.0.0"\n',
        )

        assert [(d.name, d.version) for d in LockfileParser().parse(lockfile)] == [
            ("serde", "1.0.0"),
            ("flask", "2.0.0"),
        ]


class TestPnpm:
    def test_legacy_dependencies_section_with_comments_and_blanks(self, tmp_path: Path) -> None:
        """Comments, blanks and non-``name: version`` lines are skipped.

        A quoted key keeps its quotes: the legacy matcher captures the whole
        ``name:`` prefix without stripping surrounding quotes.
        """
        lockfile = _write(
            tmp_path,
            "pnpm-lock.yaml",
            "dependencies:\n"
            "  # a comment\n"
            "\n"
            "  lodash: 4.17.21\n"
            "  '@scope/pkg': ^2.0.0\n"
            "  malformed-line-without-version\n",
        )

        deps = LockfileParser().parse(lockfile)

        assert [(d.name, d.version) for d in deps] == [
            ("lodash", "4.17.21"),
            ("'@scope/pkg'", "^2.0.0"),
        ]

    def test_packages_section_skips_non_package_lines(self, tmp_path: Path) -> None:
        lockfile = _write(
            tmp_path,
            "pnpm-lock.yaml",
            "packages:\n"
            "  /lodash/4.17.21:\n"
            "    resolution: {}\n"
            "  not-a-package-line\n"
            "  /@scope/pkg/2.0.0:\n"
            "    resolution: {}\n",
        )

        assert _names(LockfileParser().parse(lockfile)) == ["lodash", "@scope/pkg"]


class TestGradleVersionCatalog:
    def test_entry_without_a_module_is_skipped(self, tmp_path: Path) -> None:
        catalog = _write(
            tmp_path,
            "libs.versions.toml",
            "[versions]\n"
            "\n"
            "guava = \"33.0.0\"\n"
            "[libraries]\n"
            'guava = { module = "com.google.guava:guava", version.ref = "guava" }\n'
            'version-only = { version = "1.0.0" }\n'
            'ref-only = { module = "org.example:thing", version.ref = "missing" }\n',
        )

        deps = LockfileParser().parse(catalog)

        assert [(d.name, d.version) for d in deps] == [
            ("com.google.guava:guava", "33.0.0"),
            ("org.example:thing", ""),
        ]

    def test_direct_version_wins_over_version_ref(self, tmp_path: Path) -> None:
        catalog = _write(
            tmp_path,
            "libs.versions.toml",
            "[versions]\n"
            'guava = "33.0.0"\n'
            "[libraries]\n"
            'guava = { module = "com.google.guava:guava", version = "32.0.0" }\n',
        )

        assert [(d.name, d.version) for d in LockfileParser().parse(catalog)] == [
            ("com.google.guava:guava", "32.0.0")
        ]

    def test_entries_outside_a_known_section_are_ignored(self, tmp_path: Path) -> None:
        catalog = _write(
            tmp_path,
            "libs.versions.toml",
            "[metadata]\n"
            'orphan = { module = "org.example:orphan" }\n'
            "unquoted = 1\n"
            "[libraries]\n"
            'real = { module = "org.example:real", version = "1.0" }\n',
        )

        assert _names(LockfileParser().parse(catalog)) == ["org.example:real"]


class TestCargoToml:
    def test_workspace_inherited_versions_are_resolved(self, tmp_path: Path) -> None:
        root = _write(
            tmp_path,
            "Cargo.toml",
            "[workspace]\nmembers = [\"app\"]\n"
            "[workspace.dependencies]\n"
            'serde = "1.0.200"\n'
            'tokio = { version = "1.36.0", features = ["full"] }\n'
            "# a comment\n"
            "invalid-line-without-equals\n"
            'quoted-name = "9.9.9"\n'
            "[workspace.metadata]\n"
            'not-a-dependency = "0.0.1"\n',
        )
        member = tmp_path / "app" / "Cargo.toml"
        member.parent.mkdir()
        member.write_text(
            "[package]\nname = \"app\"\n"
            "[dependencies]\n"
            "serde = { workspace = true }\n"
            "tokio = { workspace = true }\n"
            "quoted-name = { workspace = true }\n",
            encoding="utf-8",
        )

        deps = LockfileParser().parse(member)

        assert [(d.name, d.version) for d in deps] == [
            ("serde", "1.0.200"),
            ("tokio", "1.36.0"),
            ("quoted-name", "9.9.9"),
        ]
        assert root.is_file()

    def test_missing_workspace_section_yields_no_inherited_versions(self, tmp_path: Path) -> None:
        root = _write(tmp_path, "Cargo.toml", '[package]\nname = "root"\nversion = "0.1.0"\n')
        member = tmp_path / "app" / "Cargo.toml"
        member.parent.mkdir()
        member.write_text("[dependencies]\nserde = { workspace = true }\n", encoding="utf-8")

        assert [(d.name, d.version) for d in LockfileParser().parse(member)] == [
            ("serde", "workspace")
        ]
        assert root.is_file()

    def test_workspace_root_without_a_dependencies_section_yields_nothing(
        self, tmp_path: Path
    ) -> None:
        """``[workspace]`` alone declares no shared versions to inherit.

        The root is still found and walked, but with no
        ``[workspace.dependencies]`` table there is nothing to resolve against,
        so the member keeps the literal ``workspace`` specifier.
        """
        _write(tmp_path, "Cargo.toml", '[workspace]\nmembers = ["app"]\n')
        member = tmp_path / "app" / "Cargo.toml"
        member.parent.mkdir()
        member.write_text(
            "[dependencies]\nserde = { workspace = true }\n", encoding="utf-8"
        )

        assert [(d.name, d.version) for d in LockfileParser().parse(member)] == [
            ("serde", "workspace")
        ]

    def test_unterminated_inline_table_is_committed_with_a_placeholder_version(
        self, tmp_path: Path
    ) -> None:
        """A brace left open must not swallow the rest of the file (#92)."""
        manifest = _write(
            tmp_path,
            "Cargo.toml",
            "[dependencies]\n"
            "rand = {\n"
            '    features = ["small_rng"]\n'
            "[dev-dependencies]\n"
            'serde = "1.0"\n',
        )

        assert [(d.name, d.version) for d in LockfileParser().parse(manifest)] == [
            ("rand", "0.0.0"),
            ("serde", "1.0"),
        ]

    def test_sub_table_without_a_version_key(self, tmp_path: Path) -> None:
        manifest = _write(
            tmp_path,
            "Cargo.toml",
            "[dependencies.local-crate]\n"
            'path = "../local-crate"\n'
            "\n"
            "[dependencies.other]\n"
            'version = "1.2.3"\n',
        )

        assert [(d.name, d.version) for d in LockfileParser().parse(manifest)] == [
            ("other", "1.2.3"),
        ]

    def test_a_line_inside_a_sub_table_with_no_equals_is_skipped(
        self, tmp_path: Path
    ) -> None:
        """Inside ``[dependencies.<name>]`` every line is split on ``=``.

        A line without one is not part of any spec, so it is dropped; the
        sub-table's real ``version`` still applies.
        """
        manifest = _write(
            tmp_path,
            "Cargo.toml",
            "[dependencies.other]\n"
            'version = "1.2.3"\n'
            "a-line-without-an-equals-sign\n",
        )

        assert [(d.name, d.version) for d in LockfileParser().parse(manifest)] == [
            ("other", "1.2.3"),
        ]

    def test_sub_table_version_workspace_inheritance(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "Cargo.toml",
            "[workspace]\n"
            "[workspace.dependencies]\n"
            'anyhow = "1.0.86"\n',
        )
        member = tmp_path / "app" / "Cargo.toml"
        member.parent.mkdir()
        member.write_text(
            "[dependencies.anyhow]\nversion.workspace = true\n", encoding="utf-8"
        )

        assert [(d.name, d.version) for d in LockfileParser().parse(member)] == [
            ("anyhow", "1.0.86")
        ]

    def test_target_specific_and_bare_tables_are_ignored(self, tmp_path: Path) -> None:
        """``[target.'cfg(unix)'.dependencies]`` counts; ``[target]`` alone does not.

        A bare ``[target]`` header has no dependency section to name, and
        ``[dependencies.]`` has an empty crate name, so both are ignored --
        only the real dependency tables contribute entries.
        """
        manifest = _write(
            tmp_path,
            "Cargo.toml",
            "[target]\n"
            "[target.'cfg(unix)'.dependencies]\n"
            'libc = "0.2"\n'
            "[dependencies.]\n"
            "[dependencies]\n"
            'serde = "1.0"\n',
        )

        assert _names(LockfileParser().parse(manifest)) == ["libc", "serde"]

    def test_quoted_and_unparseable_keys_are_skipped(self, tmp_path: Path) -> None:
        manifest = _write(
            tmp_path,
            "Cargo.toml",
            "[dependencies]\n"
            '"quoted-name" = "1.0"\n'
            "no_equals_sign\n"
            "serde = \"1.0\"\n",
        )

        assert _names(LockfileParser().parse(manifest)) == ["serde"]

    def test_dev_dependency_does_not_override_the_production_one(self, tmp_path: Path) -> None:
        manifest = _write(
            tmp_path,
            "Cargo.toml",
            "[dev-dependencies]\n"
            'serde = "1.0.100"\n'
            "[build-dependencies]\n"
            'serde = "1.0.150"\n'
            "[dependencies]\n"
            'serde = "1.0.200"\n',
        )

        assert [(d.name, d.version) for d in LockfileParser().parse(manifest)] == [
            ("serde", "1.0.200")
        ]

    def test_production_entry_replaces_an_earlier_dev_one_in_place(self, tmp_path: Path) -> None:
        """The upgraded crate keeps the earlier position in the output order."""
        manifest = _write(
            tmp_path,
            "Cargo.toml",
            "[dev-dependencies]\n"
            'first = "0.1"\n'
            'serde = "1.0.100"\n'
            'last = "0.3"\n'
            "[dependencies]\n"
            'serde = "1.0.200"\n',
        )

        assert _names(LockfileParser().parse(manifest)) == ["first", "serde", "last"]


class TestPipfileLock:
    def test_non_dict_package_entries_are_skipped(self, tmp_path: Path) -> None:
        lockfile = _write(
            tmp_path,
            "Pipfile.lock",
            '{"default": {"requests": {"version": "==2.31.0"}, "broken": "not-a-dict"},'
            ' "develop": {"pytest": {"version": "==8.0.0"}}}',
        )

        assert [(d.name, d.version) for d in LockfileParser().parse(lockfile)] == [
            ("requests", "2.31.0"),
            ("pytest", "8.0.0"),
        ]

    def test_missing_version_defaults_to_empty(self, tmp_path: Path) -> None:
        lockfile = _write(
            tmp_path, "Pipfile.lock", '{"default": {"requests": {"hashes": ["sha256:x"]}}}'
        )

        assert [(d.name, d.version) for d in LockfileParser().parse(lockfile)] == [
            ("requests", "")
        ]

    def test_malformed_json_returns_no_dependencies(self, tmp_path: Path) -> None:
        assert LockfileParser().parse(_write(tmp_path, "Pipfile.lock", "{nope")) == []


class TestComposerLock:
    def test_non_dict_package_entries_are_skipped(self, tmp_path: Path) -> None:
        lockfile = _write(
            tmp_path,
            "composer.lock",
            '{"packages": ["not-a-dict", {"name": "guzzlehttp/guzzle", "version": "7.8.0"}],'
            ' "packages-dev": [{"name": "phpunit/phpunit", "version": "10.5.0"}]}',
        )

        assert _names(LockfileParser().parse(lockfile)) == [
            "guzzlehttp/guzzle",
            "phpunit/phpunit",
        ]

    def test_package_without_a_name_is_skipped(self, tmp_path: Path) -> None:
        lockfile = _write(
            tmp_path, "composer.lock", '{"packages": [{"version": "1.0.0"}]}'
        )

        assert LockfileParser().parse(lockfile) == []

    def test_package_without_a_version_defaults(self, tmp_path: Path) -> None:
        lockfile = _write(
            tmp_path, "composer.lock", '{"packages": [{"name": "guzzlehttp/guzzle"}]}'
        )

        assert [(d.name, d.version) for d in LockfileParser().parse(lockfile)] == [
            ("guzzlehttp/guzzle", "0.0.0")
        ]

    def test_malformed_json_returns_no_dependencies(self, tmp_path: Path) -> None:
        assert LockfileParser().parse(_write(tmp_path, "composer.lock", "{nope")) == []


class TestComposerJson:
    def test_constraint_that_strips_to_nothing(self, tmp_path: Path) -> None:
        lockfile = _write(
            tmp_path, "composer.json", '{"require": {"guzzlehttp/guzzle": "^"}}'
        )

        assert [(d.name, d.version) for d in LockfileParser().parse(lockfile)] == [
            ("guzzlehttp/guzzle", "0.0.0")
        ]

    def test_malformed_json_returns_no_dependencies(self, tmp_path: Path) -> None:
        assert LockfileParser().parse(_write(tmp_path, "composer.json", "{nope")) == []

    def test_non_dict_section_is_skipped(self, tmp_path: Path) -> None:
        lockfile = _write(
            tmp_path, "composer.json", '{"require": ["guzzlehttp/guzzle"]}'
        )

        assert LockfileParser().parse(lockfile) == []


class TestPackageLock:
    def test_non_node_modules_entries_are_skipped(self, tmp_path: Path) -> None:
        lockfile = _write(
            tmp_path,
            "package-lock.json",
            '{"packages": {"": {"name": "root"}, "node_modules/lodash": '
            '{"version": "4.17.21"}}}',
        )

        assert _names(LockfileParser().parse(lockfile)) == ["lodash"]

    def test_package_without_a_version_defaults(self, tmp_path: Path) -> None:
        lockfile = _write(
            tmp_path, "package-lock.json", '{"packages": {"node_modules/lodash": {}}}'
        )

        assert [(d.name, d.version) for d in LockfileParser().parse(lockfile)] == [
            ("lodash", "0.0.0")
        ]

    def test_malformed_json_returns_no_dependencies(self, tmp_path: Path) -> None:
        assert LockfileParser().parse(_write(tmp_path, "package-lock.json", "{not json")) == []

    def test_nested_node_modules_entries_are_not_name_mangled(self, tmp_path: Path) -> None:
        """str.replace strips every occurrence; removeprefix strips only the leading one."""
        lockfile = _write(
            tmp_path,
            "package-lock.json",
            '{"packages": {"": {"name": "app"}, "node_modules/lodahs": {"version": "4.17.20"}, '
            '"node_modules/a/node_modules/lodahs": {"version": "4.17.20"}}}',
        )

        deps = LockfileParser().parse(lockfile)
        names = _names(deps)
        assert "lodahs" in names
        assert "a/node_modules/lodahs" in names
        assert "a/lodahs" not in names


class TestRequirementsTxt:
    def test_comments_and_blank_lines_are_skipped(self, tmp_path: Path) -> None:
        lockfile = _write(
            tmp_path,
            "requirements.txt",
            "# a comment\n"
            "\n"
            "requests==2.31.0\n"
            "  # indented comment\n"
            "flask>=3.0\n",
        )

        assert _names(LockfileParser().parse(lockfile)) == ["requests", "flask"]

    def test_line_without_a_version_specifier(self, tmp_path: Path) -> None:
        lockfile = _write(tmp_path, "requirements.txt", "requests\n")

        assert [(d.name, d.version) for d in LockfileParser().parse(lockfile)] == [
            ("requests", "0.0.0")
        ]

    def test_unparseable_line_is_skipped(self, tmp_path: Path) -> None:
        lockfile = _write(
            tmp_path, "requirements.txt", "!!! not a requirement\nrequests==2.31.0\n"
        )

        assert _names(LockfileParser().parse(lockfile)) == ["requests"]

    def test_pip_options_are_skipped(self, tmp_path: Path) -> None:
        """Lines starting with - are pip options, not package names."""
        lockfile = _write(
            tmp_path,
            "requirements.txt",
            "--index-url https://pypi.org/simple\n"
            "-r other-requirements.txt\n"
            "-e .\n"
            "--find-links https://example.com/packages\n"
            "-c constraints.txt\n"
            "requests==2.31.0\n",
        )

        assert _names(LockfileParser().parse(lockfile)) == ["requests"]

    def test_direct_urls_are_skipped(self, tmp_path: Path) -> None:
        """Direct URL references are not package names."""
        lockfile = _write(
            tmp_path,
            "requirements.txt",
            "https://example.com/package.tar.gz\n"
            "git+https://github.com/user/repo.git\n"
            "svn+https://svn.example.com/repo\n"
            "requests==2.31.0\n",
        )

        assert _names(LockfileParser().parse(lockfile)) == ["requests"]

    def test_local_paths_are_skipped(self, tmp_path: Path) -> None:
        """Local path references are not package names."""
        lockfile = _write(
            tmp_path,
            "requirements.txt",
            "./local-package\n"
            "/absolute/path/to/package\n"
            "requests==2.31.0\n",
        )

        assert _names(LockfileParser().parse(lockfile)) == ["requests"]


class TestYarnScopedDescriptors:
    def test_scoped_descriptors_are_parsed(self, tmp_path: Path) -> None:
        """Yarn v1 quotes scoped descriptors; the parser must not drop them."""
        lockfile = _write(
            tmp_path,
            "yarn.lock",
            "# yarn lockfile v1\n"
            "\n"
            "lodash@^4.17.21:\n"
            '  version "4.17.21"\n'
            '  resolved "https://registry.yarnpkg.com/lodash/-/lodash-4.17.21.tgz"\n'
            "\n"
            '"@babel/core@^7.20.0":\n'
            '  version "7.20.12"\n'
            '  resolved "https://registry.yarnpkg.com/@babel/core/-/core-7.20.12.tgz"\n'
            "\n"
            '"@types/node@^20.0.0":\n'
            '  version "20.11.0"\n'
            '  resolved "https://registry.yarnpkg.com/@types/node/-/node-20.11.0.tgz"\n',
        )

        deps = LockfileParser().parse(lockfile)
        names = _names(deps)
        assert "lodash" in names
        assert "@babel/core" in names
        assert "@types/node" in names


class TestPyprojectToml:
    def test_comments_and_the_python_constraint_are_skipped(self, tmp_path: Path) -> None:
        manifest = _write(
            tmp_path,
            "pyproject.toml",
            "[project]\n"
            'dependencies = ["requests>=2.31.0",\n'
            '  # a comment\n'
            '  "flask",\n'
            '  ""]\n'
            "[tool.poetry.dependencies]\n"
            'python = "^3.10"\n'
            "# a comment\n"
            'requests = "^2.31.0"\n',
        )

        assert _names(LockfileParser().parse(manifest)) == ["requests", "flask", "requests"]

    def test_non_pep621_project_section_is_ignored(self, tmp_path: Path) -> None:
        manifest = _write(
            tmp_path,
            "pyproject.toml",
            "[other]\n"
            'dependencies = ["not-a-dependency"]\n',
        )

        assert LockfileParser().parse(manifest) == []

    def test_tomli_fallback_when_tomllib_unavailable(self, tmp_path: Path, monkeypatch) -> None:
        """When tomllib is unavailable, tomli is used as fallback."""
        import sys
        import types

        monkeypatch.setitem(sys.modules, "tomllib", None)

        fake_tomli = types.ModuleType("tomli")
        fake_tomli.load = lambda f: {"project": {"dependencies": ["requests>=2.0"]}}
        monkeypatch.setitem(sys.modules, "tomli", fake_tomli)

        pyproject = _write(
            tmp_path,
            "pyproject.toml",
            '[project]\n'
            'name = "test"\n'
            'dependencies = ["requests>=2.0"]\n',
        )

        deps = LockfileParser().parse(pyproject)
        assert len(deps) == 1
        assert deps[0].name == "requests"
        assert deps[0].ecosystem == "python"


class TestPackageResolved:
    def test_pin_with_a_non_dict_state(self, tmp_path: Path) -> None:
        lockfile = _write(
            tmp_path,
            "Package.resolved",
            '{"pins": [{"identity": "alamofire", '
            '"location": "https://github.com/Alamofire/Alamofire.git", '
            '"state": "unexpected"}]}',
        )

        assert [(d.name, d.version) for d in LockfileParser().parse(lockfile)] == [
            ("github.com/Alamofire/Alamofire", "")
        ]

    def test_pin_with_no_location_falls_back_to_its_identity(self, tmp_path: Path) -> None:
        """A local/unknown pin has no GitHub location, so its identity names it."""
        lockfile = _write(
            tmp_path,
            "Package.resolved",
            '{"pins": [{"identity": "nameless", "location": ""}]}',
        )

        assert [(d.name, d.version) for d in LockfileParser().parse(lockfile)] == [
            ("nameless", "")
        ]

    def test_pin_with_no_resolvable_name_at_all_is_skipped(self, tmp_path: Path) -> None:
        """Neither a location nor an identity means there is nothing to score."""
        lockfile = _write(
            tmp_path,
            "Package.resolved",
            '{"pins": [{"location": "", "identity": "", "package": ""}]}',
        )

        assert LockfileParser().parse(lockfile) == []

    def test_branch_version_is_used_as_a_last_resort(self, tmp_path: Path) -> None:
        lockfile = _write(
            tmp_path,
            "Package.resolved",
            '{"pins": [{"identity": "swift-log", '
            '"location": "https://github.com/apple/swift-log", '
            '"state": {"branch": "main"}}]}',
        )

        assert [(d.name, d.version) for d in LockfileParser().parse(lockfile)] == [
            ("github.com/apple/swift-log", "main")
        ]

    def test_malformed_json_returns_no_dependencies(self, tmp_path: Path) -> None:
        assert LockfileParser().parse(_write(tmp_path, "Package.resolved", "{nope")) == []


class TestPackageSwift:
    def test_declaration_without_a_usable_location_is_skipped(self, tmp_path: Path) -> None:
        manifest = _write(
            tmp_path,
            "Package.swift",
            '.package(url: "https://example.com/not-github/pkg", from: "1.0.0")\n'
            '.package(name: "no-location")\n',
        )

        assert LockfileParser().parse(manifest) == []

    def test_declaration_without_a_version_specifier(self, tmp_path: Path) -> None:
        manifest = _write(
            tmp_path,
            "Package.swift",
            '.package(url: "https://github.com/apple/swift-log")\n',
        )

        assert [(d.name, d.version) for d in LockfileParser().parse(manifest)] == [
            ("github.com/apple/swift-log", "")
        ]


class TestPomXml:
    def test_basic_dependencies(self, tmp_path: Path) -> None:
        pom = _write(
            tmp_path,
            "pom.xml",
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
            "  <dependencies>\n"
            "    <dependency>\n"
            "      <groupId>com.google.guava</groupId>\n"
            "      <artifactId>guava</artifactId>\n"
            "      <version>33.0.0</version>\n"
            "    </dependency>\n"
            "    <dependency>\n"
            "      <groupId>junit</groupId>\n"
            "      <artifactId>junit</artifactId>\n"
            "      <version>4.13.2</version>\n"
            "    </dependency>\n"
            "  </dependencies>\n"
            "</project>\n",
        )

        deps = LockfileParser().parse(pom)

        assert [(d.name, d.version, d.ecosystem) for d in deps] == [
            ("com.google.guava:guava", "33.0.0", "java"),
            ("junit:junit", "4.13.2", "java"),
        ]

    def test_namespace_handling(self, tmp_path: Path) -> None:
        """POM without namespace should still parse."""
        pom = _write(
            tmp_path,
            "pom.xml",
            "<project>\n"
            "  <dependencies>\n"
            "    <dependency>\n"
            "      <groupId>org.example</groupId>\n"
            "      <artifactId>no-ns</artifactId>\n"
            "      <version>1.0</version>\n"
            "    </dependency>\n"
            "  </dependencies>\n"
            "</project>\n",
        )

        deps = LockfileParser().parse(pom)

        assert [(d.name, d.version) for d in deps] == [
            ("org.example:no-ns", "1.0"),
        ]

    def test_empty_dependencies(self, tmp_path: Path) -> None:
        pom = _write(
            tmp_path,
            "pom.xml",
            '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
            "  <dependencies>\n"
            "  </dependencies>\n"
            "</project>\n",
        )

        assert LockfileParser().parse(pom) == []

    def test_pom_xml_invalid_returns_empty(self, tmp_path: Path) -> None:
        """Invalid XML (ParseError) should return empty list, not raise."""
        pom = _write(
            tmp_path,
            "pom.xml",
            '<project>\n  <dependencies>\n    <dependency>\n',
        )
        assert LockfileParser().parse(pom) == []

    def test_pyproject_toml_no_tomllib_no_tomli_returns_empty(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """When neither tomllib nor tomli is available, return empty list."""
        import sys

        monkeypatch.setitem(sys.modules, "tomllib", None)
        monkeypatch.setitem(sys.modules, "tomli", None)

        pyproject = _write(
            tmp_path,
            "pyproject.toml",
            '[project]\n'
            'name = "test"\n'
            'dependencies = ["requests>=2.0"]\n',
        )

        assert LockfileParser().parse(pyproject) == []


class TestGradleBuildFile:
    def test_map_form_dependency_is_parsed(self, tmp_path: Path) -> None:
        build = _write(
            tmp_path,
            "build.gradle",
            "dependencies {\n"
            '    implementation "com.google.guava:guava:33.0.0"\n'
            '    implementation group: "org.example", name: "thing", version: "1.0"\n'
            "}\n",
        )

        assert _names(LockfileParser().parse(build)) == [
            "com.google.guava:guava",
            "org.example:thing",
        ]

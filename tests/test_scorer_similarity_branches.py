"""Scorer, similarity and detector branches that the known-package tests miss.

``test_java_packages.py`` covers the similarity engine against a large data set
and ``test_taintrace.py`` against known typosquats, but three code paths stay
unexercised by those: the Soundex saturation fallback, the dependency-confusion
verdict, and the detector's own ignore filter.
"""

from __future__ import annotations

from pathlib import Path

from taintrace.db import KnownPackagesDB
from taintrace.detector import TyposquatDetector
from taintrace.scorer import RiskLevel, RiskScorer
from taintrace.similarity import SOUNDEX_TRUSTED_LENGTH, SimilarityEngine


class TestSoundexSaturation:
    """``_phonetic_similarity`` on names whose Soundex codes saturate."""

    # Two long Maven-style coordinates that collide on the same saturated
    # four-character code (``o621``) while being genuinely unrelated packages.
    COLLIDING = ("org.apache.commons:commons-lang3", "org.projectlombok:lombok.ast")

    def test_saturated_codes_fall_back_to_levenshtein(self) -> None:
        engine = SimilarityEngine()
        long_a, long_b = self.COLLIDING

        assert max(len(long_a), len(long_b)) > SOUNDEX_TRUSTED_LENGTH
        assert engine._soundex(long_a) == engine._soundex(long_b)
        assert engine._phonetic_similarity(long_a, long_b) < 1.0

    def test_the_fallback_is_the_levenshtein_score_passed_in(self) -> None:
        """The cached ``lev_score`` argument is reused instead of recomputed."""
        engine = SimilarityEngine()
        long_a, long_b = self.COLLIDING

        assert engine._phonetic_similarity(long_a, long_b, lev_score=0.42) == 0.42

    def test_the_fallback_recomputes_when_no_score_is_supplied(self) -> None:
        """Calling the helper directly must still produce the same damped score."""
        engine = SimilarityEngine()
        long_a, long_b = self.COLLIDING

        expected = engine._levenshtein_similarity(long_a, long_b)
        assert engine._phonetic_similarity(long_a, long_b) == expected

    def test_a_collision_does_not_reach_a_typosquat_level_score(self) -> None:
        """The damped phonetic score must stay well under the 0.7 suspect floor."""
        engine = SimilarityEngine()
        long_a, long_b = self.COLLIDING

        assert engine.similarity(long_a, long_b) < 0.7

    def test_short_names_still_score_a_perfect_phonetic_match(self) -> None:
        engine = SimilarityEngine()

        assert engine._phonetic_similarity("react", "reakt") == 1.0

    def test_empty_name_has_an_empty_soundex_code(self) -> None:
        assert SimilarityEngine._soundex("") == ""

    def test_memoised_soundex_returns_the_same_code(self) -> None:
        assert SimilarityEngine._soundex("serde") == SimilarityEngine._soundex("serde")


class TestCouldMatchPrefilter:
    def test_an_empty_name_cannot_match_a_long_one(self) -> None:
        """Length rules out the match and an empty Soundex code cannot rescue it."""
        engine = SimilarityEngine()

        assert engine.could_match("", "a-fairly-long-package-name", 0.7) is False
        assert engine.could_match("a-fairly-long-package-name", "", 0.7) is False

    def test_a_length_compatible_pair_is_kept(self) -> None:
        engine = SimilarityEngine()

        assert engine.could_match("serde", "serdej", 0.7) is True

    def test_the_prefilter_is_a_superset_of_real_matches(self) -> None:
        """Anything ``could_match`` rejects must score below the threshold."""
        engine = SimilarityEngine()
        query, candidate = "k8s.io/client-go", "k8s.io/client-goo"

        assert engine.could_match(query, candidate, 0.9)
        assert engine.similarity(query, candidate) >= 0.9


class TestDependencyConfusion:
    """The internal-naming verdict in ``RiskScorer.score``."""

    def test_internal_naming_with_no_similar_package_is_high_risk(self) -> None:
        result = RiskScorer().score("corp-billing-api", "node", 0.7)

        assert result.level == RiskLevel.HIGH
        assert result.score == 0.85
        assert "dependency confusion" in result.reason.lower()
        assert result.similar_packages == []

    def test_a_scoped_internal_name_is_also_flagged(self) -> None:
        """The ``-private``/``private-`` spelling reaches the same verdict."""
        result = RiskScorer().score("corp-private-api", "go", 0.7)

        assert result.level == RiskLevel.HIGH
        assert "dependency confusion" in result.reason.lower()
        assert result.similar_packages == []

    def test_internal_naming_loses_to_a_stronger_similarity_match(self) -> None:
        """The dependency-confusion verdict only applies to unmatched packages.

        ``corp-secret-store`` resembles ``grpc`` closely enough to be scored on
        that similarity instead, so the internal-naming branch is not taken.
        """
        result = RiskScorer().score("corp-secret-store", "go", 0.7)

        assert result.level == RiskLevel.MEDIUM
        assert result.similar_packages
        assert "dependency confusion" not in result.reason.lower()

    def test_a_known_package_is_never_treated_as_confusion(self) -> None:
        result = RiskScorer().score("express", "node", 0.7)

        assert result.level == RiskLevel.LOW
        assert result.reason == "Known legitimate package"

    def test_an_unknown_package_without_internal_naming_is_only_medium(self) -> None:
        result = RiskScorer().score("nubmy", "python", 0.7)

        assert result.level == RiskLevel.MEDIUM
        assert result.score == 0.3
        assert "unknown package" in result.reason.lower()


class TestMinorSimilarity:
    """A match below the MEDIUM cut-off, which is the LOW 'Minor similarity' verdict."""

    def test_a_weak_match_scores_low(self) -> None:
        """Every candidate here ties at 0.5, so only the verdict is asserted.

        Which tied package sorts first depends on set iteration order, so
        pinning a specific winner would make this test flaky rather than strict.
        """
        result = RiskScorer().score("helqqq", "node", 0.5)

        assert result.level == RiskLevel.LOW
        assert result.reason.startswith("Minor similarity to '")
        assert result.similar_packages
        assert all(score == 0.5 for _, score in result.similar_packages)

    def test_a_low_match_is_not_a_suspect_for_the_detector(self) -> None:
        detector = TyposquatDetector(ecosystem="node", similarity_threshold=0.5)

        result = detector.scan_dependency("helqqq", ecosystem="node")

        assert result.is_suspect is False
        assert result.risk_level == "LOW"

    def test_a_high_match_is_a_suspect_for_the_detector(self) -> None:
        detector = TyposquatDetector(ecosystem="python", similarity_threshold=0.7)

        result = detector.scan_dependency("reqeusts", ecosystem="python")

        assert result.is_suspect is True
        assert result.risk_level == "CRITICAL"
        # Only the top-scoring match decides the verdict, so assert that the
        # verdict names ``requests``. Pinning the whole list would be brittle:
        # any other python package that happens to score >= the 0.7 threshold
        # is legitimately included alongside it.
        assert result.similarity_scores[0] == ("requests", 1.0)
        assert max(result.similarity_scores, key=lambda pair: pair[1]) == ("requests", 1.0)
        assert "Near-identical to 'requests'" in result.reason


class TestDetectorIgnoreFilter:
    def test_ignored_packages_are_dropped_before_scoring(self, tmp_path: Path) -> None:
        """``scan`` honours the ignore list sitting next to the lockfile."""
        (tmp_path / ".taintrace.toml").write_text(
            '[taintrace]\nignore = ["reqeusts"]\n', encoding="utf-8"
        )
        lockfile = tmp_path / "requirements.txt"
        lockfile.write_text("reqeusts==2.31.0\nrequests==2.31.0\n", encoding="utf-8")

        results = TyposquatDetector(ecosystem="python").scan(lockfile)

        assert [result.dependency.name for result in results] == ["requests"]

    def test_nothing_is_dropped_without_a_config(self, tmp_path: Path) -> None:
        lockfile = tmp_path / "requirements.txt"
        lockfile.write_text("reqeusts==2.31.0\n", encoding="utf-8")

        results = TyposquatDetector(ecosystem="python").scan(lockfile)

        assert [result.dependency.name for result in results] == ["reqeusts"]


class TestKnownPackageData:
    def test_every_registered_ecosystem_reports_its_data(self) -> None:
        db = KnownPackagesDB()

        for ecosystem in db.ecosystems():
            assert db.has_ecosystem_data(ecosystem), ecosystem

    def test_java_artifact_ids_resolve_across_groups(self) -> None:
        """An artifactId is only unique within a group, so resolution spans groups."""
        db = KnownPackagesDB()

        assert db.is_known("guava", "java")
        assert db.is_known("com.google.guava:guava", "java")
        assert not db.is_known("guavv", "java")

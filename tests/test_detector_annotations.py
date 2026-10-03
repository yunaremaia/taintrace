"""Regression tests for the detector's runtime-resolvable annotations.

`DetectionResult.dependency` was annotated as the string ``'Dependency'``
while `Dependency` was never imported at module scope, so the annotation was
unresolvable: `typing.get_type_hints()` raised `NameError`. Any consumer
that introspects the dataclass at runtime (serializers, schema generators,
validation helpers) hit that error.

These tests assert the annotations actually resolve, which is what the
pyflakes gate added in the same PR now enforces statically.
"""

import typing

from taintrace.detector import DetectionResult, TyposquatDetector
from taintrace.lockfile import Dependency


def test_detection_result_annotations_resolve() -> None:
    """get_type_hints must resolve every field, not raise NameError."""
    hints = typing.get_type_hints(DetectionResult)
    assert hints["dependency"] is Dependency


def test_every_detection_result_field_resolves() -> None:
    """No field may carry an unresolvable forward reference."""
    for name in DetectionResult.__annotations__:
        typing.get_type_hints(DetectionResult)[name]  # raises if unresolvable


def test_module_exposes_dependency_name() -> None:
    """`Dependency` must be a module-level name, not only a local import."""
    import taintrace.detector as detector_module

    assert hasattr(detector_module, "Dependency")


def test_detection_result_stores_dependency_instance() -> None:
    """The fixed annotation still describes the real runtime value."""
    dep = Dependency(name="reqests", version="2.0.0", ecosystem="python")
    result = DetectionResult(
        dependency=dep,
        is_suspect=True,
        risk_level="HIGH",
        risk_score=0.9,
        similar_packages=["requests"],
        similarity_scores=[("requests", 0.95)],
        reason="transposed characters",
    )
    assert result.dependency is dep
    assert typing.get_type_hints(type(result))["dependency"] is Dependency


def test_scan_dependency_returning_result_keeps_resolvable_hints() -> None:
    """A result built through the public API is introspectable too."""
    detector = TyposquatDetector(ecosystem="python")
    result = detector.scan_dependency("reqests", "2.0.0", ecosystem="python")
    assert typing.get_type_hints(type(result))["dependency"] is Dependency
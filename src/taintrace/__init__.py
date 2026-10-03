"""taintrace public API."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _metadata_version

from taintrace.lockfile import LockfileParser, Dependency
from taintrace.similarity import SimilarityEngine
from taintrace.db import KnownPackagesDB, UnknownEcosystemError
from taintrace.scorer import RiskScorer, RiskResult, RiskLevel
from taintrace.detector import TyposquatDetector, DetectionResult

try:
    __version__ = _metadata_version("taintrace")
except PackageNotFoundError:  # running from a source checkout, not an install
    __version__ = "0.0.0.dev0"

__all__ = [
    "LockfileParser",
    "Dependency",
    "SimilarityEngine",
    "KnownPackagesDB",
    "UnknownEcosystemError",
    "RiskScorer",
    "RiskResult",
    "RiskLevel",
    "TyposquatDetector",
    "DetectionResult",
]

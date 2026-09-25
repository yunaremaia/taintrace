### Análisis y Estrategia de Solución

El issue requiere agregar capacidades de detección de **Dependency Confusion** (CWE-1357) e **Inyección de Versiones** a `taintrace`. 

Para cumplir con todos los criterios de aceptación:
1. **Patrones Internos**: Identificar nombres de paquetes con alcance (scoped `@org/pkg`) o sufijos/prefijos internos (`-internal`, `-private`, etc.).
2. **Detección de Confusión de Registro**: Comparar manifiestos locales con registros públicos (p. ej., npm / PyPI) y registros privados/internos.
3. **Detección de Inyección de Versiones**: Evaluar si la versión publicada en el registro público es superior a la versión interna, lo que provocaría que el gestor de paquetes descargue la versión pública maliciosa.
4. **Tests Automatizados**: Cobertura mediante pruebas unitarias simulando paquetes `@acme/internal-lib` presentes tanto en registro interno como público.
5. **Documentación**: Explicar la lógica en el `README.md`.

---

### Implementación Técnica

#### 1. Módulo `taintrace/confusion.py`

```python
import re
from typing import List, Dict, Any, Optional
from packaging.version import parse as parse_version

# Patrones predeterminados para reconocer paquetes internos/privados
DEFAULT_INTERNAL_PATTERNS = [
    r"^@[\w-]+/[\w-]+$",     # Scoped packages (e.g., @acme/internal-lib)
    r"^[\w-]+-internal$",    # Sufijo -internal
    r"^[\w-]+-private$",     # Sufijo -private
    r"^internal-[\w-]+$",    # Prefijo internal-
    r"^private-[\w-]+$",     # Prefijo private-
]

def is_internal_package(pkg_name: str, custom_patterns: Optional[List[str]] = None) -> bool:
    """Comprueba si un paquete coincide con la convención de nombres internos."""
    patterns = custom_patterns if custom_patterns is not None else DEFAULT_INTERNAL_PATTERNS
    return any(re.match(pat, pkg_name) for pat in patterns)


def detect_dependency_confusion(
    manifest_packages: List[Dict[str, Any]],
    public_registry_packages: Dict[str, str],
    internal_registry_packages: Optional[Dict[str, str]] = None,
    custom_patterns: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Detecta riesgos de Dependency Confusion e Inyección de Versiones.
    
    :param manifest_packages: Lista de diccionarios con {'name': str, 'version': str}
    :param public_registry_packages: Dict {pkg_name: public_latest_version}
    :param internal_registry_packages: Dict {pkg_name: internal_latest_version}
    :param custom_patterns: Lista opcional de regexes personalizados
    :return: Lista de hallazgos de seguridad
    """
    findings = []
    internal_registry = internal_registry_packages or {}

    for pkg in manifest_packages:
        pkg_name = pkg.get("name")
        pkg_version = pkg.get("version")

        if not pkg_name:
            continue

        # Validar si coincide con patrón interno
        is_internal_pattern = is_internal_package(pkg_name, custom_patterns)
        in_internal_registry = pkg_name in internal_registry
        in_public_registry = pkg_name in public_registry_packages

        if not (is_internal_pattern or in_internal_registry):
            continue

        if in_public_registry:
            public_ver_str = public_registry_packages[pkg_name]
            internal_ver_str = internal_registry.get(pkg_name, pkg_version)

            risk_type = "dependency_confusion"
            is_version_injection = False

            try:
                if parse_version(public_ver_str) > parse_version(internal_ver_str):
                    risk_type = "dependency_confusion_version_injection"
                    is_version_injection = True
            except Exception:
                # Si las versiones no son de tipo SemVer estándar, mantener riesgo base
                pass

            findings.append({
                "package": pkg_name,
                "manifest_version": pkg_version,
                "internal_version": internal_ver_str,
                "public_version": public_ver_str,
                "is_version_injection": is_version_injection,
                "risk": risk_type,
                "severity": "HIGH" if is_version_injection else "MEDIUM",
                "message": (
                    f"Inyección de versión detectada: la versión pública ({public_ver_str}) "
                    f"es mayor a la interna ({internal_ver_str})."
                    if is_version_injection
                    else f"El paquete interno '{pkg_name}' también existe en el registro público."
                )
            })

    return findings
```

---

#### 2. Pruebas Unitarias (`tests/test_confusion.py`)

```python
import pytest
from taintrace.confusion import detect_dependency_confusion, is_internal_package

def test_is_internal_package_matching():
    assert is_internal_package("@acme/internal-lib") is True
    assert is_internal_package("core-service-internal") is True
    assert is_internal_package("auth-module-private") is True
    assert is_internal_package("express") is False

def test_detect_dependency_confusion_public_and_internal_exist():
    manifest = [
        {"name": "@acme/internal-lib", "version": "1.0.0"},
        {"name": "lodash", "version": "4.17.21"}
    ]
    public_registry = {
        "@acme/internal-lib": "1.0.0",
        "lodash": "4.17.21"
    }
    internal_registry = {
        "@acme/internal-lib": "1.0.0"
    }

    risks = detect_dependency_confusion(manifest, public_registry, internal_registry)
    
    assert len(risks) == 1
    assert risks[0]["package"] == "@acme/internal-lib"
    assert risks[0]["risk"] == "dependency_confusion"
    assert risks[0]["severity"] == "MEDIUM"

def test_detect_version_injection():
    manifest = [
        {"name": "@acme/internal-lib", "version": "1.0.0"}
    ]
    public_registry = {
        "@acme/internal-lib": "99.0.0"  # Versión maliciosa inyectada
    }
    internal_registry = {
        "@acme/internal-lib": "1.0.0"
    }

    risks = detect_dependency_confusion(manifest, public_registry, internal_registry)
    
    assert len(risks) == 1
    assert risks[0]["package"] == "@acme/internal-lib"
    assert risks[0]["risk"] == "dependency_confusion_version_injection"
    assert risks[0]["is_version_injection"] is True
    assert risks[0]["severity"] == "HIGH"
```

---

#### 3. Actualización de `README.md`

```markdown
## Dependency Confusion & Version Injection Detection

`taintrace` now checks for potential Dependency Confusion risks (CWE-1357):

1. **Internal Naming Pattern Matching**: Automatically checks package manifests against known internal naming conventions (e.g. `@scope/*`, `*-internal`, `*-private`).
2. **Registry Cross-Checking**: Compares packages defined in internal registers vs. public registries (npm, PyPI, etc.).
3. **Version Injection**: Flags instances where a package on a public registry has a version number higher than the latest internal version, which could trick package managers into downloading the public malicious release.
```

---

### Commit sugerido

```bash
git commit -m "feat(security): add dependency confusion and version injection detection

- Detect scoped and internal naming patterns (@company/*, *-internal, *-private)
- Cross-reference internal manifests against public registries
- Flag version injection attacks when public version > internal version
- Add test coverage for @acme/internal-lib scenario
- Update README with detection logic documentation

Closes #1357"
```
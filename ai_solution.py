To address the dependency confusion, we add version comparison to the function.

```python
from packaging import version

INTERNAL_PATTERNS = [
    r'^@[\w-]+/[\w-]+$',  # scoped packages
    r'^[\w-]+-internal$',  # -internal suffix
    r'^[\w-]+-private$',  # -private suffix
]

def detect_dependency_confusion(manifest_packages, registry_packages):
    """Detect packages that exist in both internal and public registries with higher public versions."""
    confusion_risks = []
    for pkg in manifest_packages:
        if any(re.match(pat, pkg['name']) for pat in INTERNAL_PATTERNS):
            if pkg['name'] in registry_packages:
                public_version = registry_packages[pkg['name']]
                if version.parse(public_version) > version.parse(pkg['version']):
                    confusion_risks.append({
                        'package': pkg['name'],
                        'internal_version': pkg['version'],
                        'public_version': public_version,
                        'risk': 'dependency_confusion'
                    })
    return confusion_risks
```
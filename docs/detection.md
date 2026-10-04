# Detection

## What a scan does

1. **Parse** the lockfile into `(name, version, ecosystem)` triples. The
   ecosystem comes from the filename, or from `--ecosystem`.
2. **Skip** anything on the ignore list (CLI `--ignore` plus the
   `ignore` config key).
3. **Compare** every remaining name against the offline known-package database
   for that ecosystem.
4. **Filter** to suspects at or above `--threshold`, and — with
   `--no-informational` — to `CRITICAL` and `HIGH` only.
5. **Report** in the requested format and exit `1` if anything survived.

## Similarity

Four signals are computed for each candidate pair, and the score is the
**maximum** of them plus a weighted blend:

| Signal | What it catches | Example |
|--------|-----------------|---------|
| Levenshtein | Edits — transpositions, insertions, deletions | `reqeusts` → `requests` (distance 2) |
| Soundex | Homophones | `night` → `n230`, `nite` → `n300` |
| Substring | Containment | `serde` ⊂ `serde-json` |
| Homoglyph | Visually confusable characters | `аpple` (Cyrillic а) → `apple` |

The weighted blend is
`0.5 * levenshtein + 0.1 * phonetic + 0.1 * substring + 0.3 * homoglyph`.

Because the final score is a maximum, a single strong signal is enough. Measured
with `SimilarityEngine().similarity()`:

```
'proc-macro1'   vs 'proc-macro2'              1.000
'reqeusts'      vs 'requests'                 1.000
'lodahs'        vs 'lodash'                   1.000
'raills'        vs 'rails'                    1.000
'аpple'         vs 'apple'                    1.000
'requests'      vs 'reqwest'                  0.750
'serde'         vs 'serde-json'               0.750
'unknown-pkg'   vs 'requests'                 0.111
```

The homoglyph pass normalises a curated set of confusables — Cyrillic
`а е о р с у х і ј ѕ`, Greek `ɡ ɑ ε ο υ`, and full-width digits — so a name
that is visually identical to a real package scores `1.000` while string
comparison sees nothing.

### Soundex on long names

Soundex emits a fixed four-character code, so it saturates: every
`org.*` Maven coordinate hashes to `o621`. Beyond 12 characters the code is no
longer trusted on its own; when two codes collide on a long name the phonetic
score is damped by the Levenshtein similarity of the full strings, so an
unrelated package is not promoted to a perfect phonetic match.

## Risk levels

The highest similarity to a known package sets the level:

| Level | Highest similarity | Reason text |
|-------|--------------------|-------------|
| `CRITICAL` | ≥ 0.95 | Near-identical to 'X' – likely typosquat |
| `HIGH` | ≥ 0.85 | Very similar to 'X' – possible typosquat |
| `MEDIUM` | ≥ 0.75 | Somewhat similar to 'X' |
| `LOW` | below 0.75 | Minor similarity to 'X' |

Reasons gain a ` (homoglyph)` suffix when the name matches a known package only
after confusable normalisation.

The numeric `risk_score` is that similarity, **halved** for `MEDIUM`. Special
cases bypass the similarity ladder entirely:

| Situation | Level | Score | Reason |
|-----------|-------|-------|--------|
| Name is in the known database | `LOW` | 0.0 | Known legitimate package |
| No similar known package, name looks internal (`@scope`, `-internal`, `-private`, `-corp`, …) | `HIGH` | 0.85 | Potential dependency confusion: internal package naming convention not found in public registry |
| No similar known package | `MEDIUM` | 0.3 | Unknown package – not in known packages list |
| Ecosystem has no known-package data | `MEDIUM` | 0.3 | No known-package data for ecosystem 'X' – typosquatting cannot be assessed |

That last row is deliberate: an ecosystem without data must not look like a
clean bill of health.

```bash
taintrace score private-zzqxv -e node
```

```
🚨 private-zzqxv
Risk: HIGH | Score: 0.850
Similar to:
Reason: Potential dependency confusion: internal package naming convention not found in public registry
```

## The threshold

`--threshold` (default `0.7`) sets the minimum similarity considered during
matching. Raise it to cut noise, lower it to catch subtler near-misses:

```bash
taintrace check Cargo.lock --threshold 0.85
```

A suspect must satisfy **both** `is_suspect` and `risk_score >= threshold`, so
raising the threshold filters the output twice over — it narrows which
candidates are compared and which of the results are reported.

`--no-informational` then drops everything except `CRITICAL` and `HIGH`:

```bash
taintrace check Cargo.lock --no-informational
```

## Known-package data

| Ecosystem | Source |
|-----------|--------|
| Rust, Node.js, Python, Go, Ruby, PHP, Swift, Elixir | curated lists in `taintrace/db.py` |
| Java / Maven | `src/taintrace/data/java_packages.txt` — 7,848 `groupId:artifactId` coordinates generated from the [Maven Central repository index](https://repo1.maven.org/maven2/) |

Java coordinates are matched in `groupId:artifactId` form, the same shape the
Gradle parsers emit; a bare `artifactId` is also accepted. The data file ships
as package data, so it is present in the wheel.

Refresh it against Maven Central with:

```bash
python scripts/generate_java_packages.py           # regenerate
python scripts/generate_java_packages.py --check   # validate the committed file (offline)
python scripts/generate_java_packages.py --verify  # re-query Maven Central and diff
```

## Programmatic access

The engine is a plain class — see the [API Reference](api.md) for the full
surface.

```python
from pathlib import Path
from taintrace.detector import TyposquatDetector

detector = TyposquatDetector(ecosystem="rust", similarity_threshold=0.7)
for result in detector.scan(Path("Cargo.lock")):
    if result.is_suspect:
        print(result.dependency.name, result.risk_level, result.risk_score)
```

## Next steps

- [Configuration](configuration.md) — set the threshold and ignore list in a file
- [CI](ci.md) — fail a pipeline on exit code 1, or upload SARIF
- [API Reference](api.md) — every class and method

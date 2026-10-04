# Getting Started

## Install

```bash
pip install taintrace
```

Requires Python 3.10 or newer. The known-package database is bundled, so
`taintrace` works fully offline and never makes a network call.

Check the install:

```bash
taintrace --version
```

```
taintrace, version 0.2.2
```

## Scan a lockfile

Point it at any lockfile it recognises. The ecosystem is detected from the
filename. Given a `Cargo.lock` containing `proc-macro1`:

```bash
taintrace check Cargo.lock
```

```
╭──────────────────────────────────────────────────── Scan Results ────────────────────────────────────────────────────╮
│ taintrace v0.2.2 — scanning Cargo.lock                                                                               │
│ Total deps: 2 | Suspects: 1                                                                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
                                                 🚨 Typosquat Suspects
┏━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Package     ┃ Risk     ┃ Score ┃ Similar To                               ┃ Reason                                   ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ proc-macro1 │ CRITICAL │  1.00 │ proc-macro2 (1.00), parking_lot (1.00),  │ Near-identical to 'proc-macro2' – likely │
│             │          │       │ tracing-log (0.75)                       │ typosquat                                │
└─────────────┴──────────┴───────┴──────────────────────────────────────────┴──────────────────────────────────────────┘

❌ 1 suspect(s) found — review required
```

The process exits **1** here, because suspects were found. That is the CI gate.

## Try it on the shipped fixtures

The repo ships runnable typosquat examples — a transposed `reqeusts`, a
transposed `lodahs` and an extra-letter `raills`:

```bash
git clone https://github.com/yunaremaia/taintrace.git
cd taintrace

taintrace check examples/reports/python/requirements.txt --format json
taintrace check examples/reports/node/package-lock.json --format json
taintrace check examples/reports/ruby/Gemfile.lock --format json
```

`examples/reports/python/requirements.txt` produces (exit code `1`):

```json
{
  "tool": "taintrace",
  "version": "0.2.2",
  "summary": {
    "total": 1,
    "suspects": 1,
    "risk_levels": {
      "CRITICAL": 1,
      "HIGH": 0,
      "MEDIUM": 0
    }
  },
  "results": [
    {
      "package": "reqeusts",
      "version": "2.31.0",
      "risk_level": "CRITICAL",
      "risk_score": 1.0,
      "similar_to": [
        "requests",
        "mkdocs"
      ],
      "similarity_scores": [
        {
          "package": "requests",
          "score": 1.0
        },
        {
          "package": "mkdocs",
          "score": 0.75
        }
      ],
      "reason": "Near-identical to 'requests' – likely typosquat"
    }
  ]
}
```

The Node.js and Ruby fixtures report `lodahs → lodash` and `raills → rails` the
same way. Full context for each is in
[`examples/reports/README.md`](https://github.com/yunaremaia/taintrace/blob/main/examples/reports/README.md).

## Scan a whole repository

`scan-directory` walks a tree, auto-discovers every lockfile it knows, and
reports per-file counts before the aggregate:

```bash
taintrace scan-directory examples/reports
```

```
Scanned 3 lockfiles in examples/reports

  🚨 node/package-lock.json — 1 deps, 1 suspect(s)
  🚨 python/requirements.txt — 1 deps, 1 suspect(s)
  🚨 ruby/Gemfile.lock — 1 deps, 1 suspect(s)

Aggregated suspects across 3 lockfiles:
╭──────────────────────────────────────────────────── Scan Results ────────────────────────────────────────────────────╮
│ taintrace v0.2.2 — scanning package-lock.json, requirements.txt, Gemfile.lock                                        │
│ Total deps: 3 | Suspects: 3                                                                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
                                                 🚨 Typosquat Suspects
┏━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Package  ┃ Risk     ┃ Score ┃ Similar To                                ┃ Reason                                     ┃
┡━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ lodahs   │ CRITICAL │  1.00 │ lodash (1.00), lodash-es (1.00), redux    │ Near-identical to 'lodash' – likely        │
│          │          │       │ (0.75)                                    │ typosquat                                  │
├──────────┼──────────┼───────┼───────────────────────────────────────────┼────────────────────────────────────────────┤
│ reqeusts │ CRITICAL │  1.00 │ requests (1.00), mkdocs (0.75)            │ Near-identical to 'requests' – likely      │
│          │          │       │                                           │ typosquat                                  │
├──────────┼──────────┼───────┼───────────────────────────────────────────┼────────────────────────────────────────────┤
│ raills   │ CRITICAL │  1.00 │ rails (1.00), rails-html-sanitizer        │ Near-identical to 'rails' – likely         │
│          │          │       │ (0.75), reline (0.75)                     │ typosquat                                  │
└──────────┴──────────┴───────┴───────────────────────────────────────────┴────────────────────────────────────────────┘

❌ 3 suspect(s) found — review required
```

It descends into subdirectories but skips `.git`, `node_modules`, `vendor`,
`.vendor`, `dist`, `build` and `.cache`. Symlinked directories are not
followed, and results are de-duplicated by resolved path.

## Ignore a known false positive

```bash
taintrace check examples/reports/python/requirements.txt --ignore reqeusts
```

```
╭──────────────────────────────────────────────────── Scan Results ────────────────────────────────────────────────────╮
│ taintrace v0.2.2 — scanning requirements.txt                                                                         │
│ Total deps: 0 | Suspects: 0                                                                                          │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
✅ No typosquat suspects detected.
```

Exit code `0`. For a permanent ignore list, see
[Configuration](configuration.md).

## Next steps

- [Usage](usage.md) — every flag, with its default
- [Detection](detection.md) — what the score actually means
- [Configuration](configuration.md) — ignore lists and thresholds in a file
- [CI](ci.md) — fail a pipeline on exit code 1, or upload SARIF

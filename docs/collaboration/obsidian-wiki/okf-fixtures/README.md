# OKF round-trip conformance fixtures (seed)

Seed corpus for the shared **Open Knowledge Format** round-trip suite (collaboration Angle B). The
goal: a neutral set of golden bundles that both obsidian-wiki and agentic-fs — and any future
filesystem/PKM tool — can certify against, so "does OKF round-trip?" becomes a test, not a debate.

## The round-trip contract

```
native  --(emit)-->  OKF  --(ingest)-->  native'        # native' == native  (modulo documented lossy fields)
OKF     --(ingest)--> native --(emit)--> OKF'           # OKF'    == OKF
```

A tool *conforms* if, for every fixture directory:
1. emitting OKF from `native.md` produces `expected.okf.md` byte-for-byte (after normalization), and
2. the generated per-directory index equals `expected.index.md`.

## Frontmatter mapping under test

Per @Ar9av's obsidian-wiki implementation, the native↔OKF frontmatter mapping is:

| native (obsidian-wiki) | OKF        |
|------------------------|------------|
| `title`                | `title`    |
| `category`             | `type`     |
| `summary`              | `description` |
| `sources`              | `resource` |
| `tags`                 | `tags`     |
| `created` / `updated`  | `timestamp` |

## Layout

```
okf-fixtures/
  README.md                     # this file — the contract + mapping
  example-note/
    native.md                   # native frontmatter (obsidian-wiki schema)
    expected.okf.md             # emitted OKF
    expected.index.md           # conformant per-directory index (the hard part)
```

## Status

Not yet wired into a test runner — this is the seed shape to align on with obsidian-wiki before
graduating to a neutral `open-knowledge-format/conformance` repo and a `pytest` harness in
`tests/fixtures/okf/`.

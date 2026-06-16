# EGGuard architecture

A short tour of how EGGuard is put together, for contributors.

## Pipeline

A `refresh` run is a fan-out over the selected categories, each going through
the same pipeline, followed by a single engine reload:

```
select categories
      │
      ▼
 for each category:
   fetch (conditional) ──304/unchanged──► skip (no write)
      │ changed
      ▼
   parse domains  ──too few / malformed──► fail (category only)
      │ ok
      ▼
   write list  +  write policy  +  record state
      │
      ▼
 (after all)  reload engine once, iff anything changed
      │
      ▼
 emit JSON summary
```

A failure in one category never aborts the run; it is recorded and the others
continue. The process exit code reflects the aggregate (`0` all good, `1` some
failed, `2` could not start).

## Modules

| Module | Responsibility |
| ------ | -------------- |
| `categories.py` | The static catalogue: 66 `Category` records (name, description, suggested `Disposition`). Pure data + lookups. |
| `config.py` | The `Config` dataclass and strict YAML loading/validation. |
| `state.py` | `CategoryState` + `StateStore` — atomic per-category JSON cache of ETag / Last-Modified / sha256 / count. |
| `fetcher.py` | `Fetcher` — conditional HTTP GET with retries/backoff; raises `NotModified` on 304. |
| `parser.py` | `extract_domains` — safe tar.gz extraction (size cap, traversal guard) and domain normalisation. |
| `policy.py` | `render_policy` — turns a category + list path + action into `.policy` text. |
| `engine.py` | `EngineBridge` protocol with a toolbox backend (`enforcegate_toolbox`) and a filesystem fallback for local/CI. |
| `refresh.py` | `Refresher` orchestration, category selection, action resolution, `RefreshSummary`. |
| `cli.py` | argparse front-end, subcommands, exit codes, signal/pipe handling. |

## Key design choices

- **Two runtime dependencies only** (`requests`, `PyYAML`). Both ship in the
  EnforceGate vX toolbox, so EGGuard runs there with no `pip install`. The
  `engine.py` bridge means the same code runs locally (writing files directly)
  and in the toolbox (using the helper library), without branching at call
  sites.

- **Conditional fetching first.** ETag/If-Modified-Since plus a content-hash
  check means a routine daily run does almost no work and triggers no engine
  reload when UT1 hasn't changed — keeping load off the upstream servers.

- **Operator policy always wins.** Generated policies use a configurable
  numeric precedence prefix (default `60-`), and the engine loads
  operator-authored rules first, so a community list can propose but never
  silently override a hand-authored verdict.

- **Defensive parsing.** The tarballs are third-party input, so the parser caps
  uncompressed size (decompression-bomb guard) and rejects path-traversal
  members before reading anything.

## Action resolution

For each category the action is resolved in priority order:

1. an explicit per-category override in `config.actions`
2. `config.default_action`, if set
3. the category's suggested `Disposition` from the catalogue

`egguard list` prints the result of this resolution for every category under
the active config, so you can confirm exactly what a refresh will enforce.

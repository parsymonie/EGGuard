# Changelog

All notable changes to EGGuard are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The package is now importable as a library: `egguard` re-exports the public
  API (`get`, `extract_domains`, `render_policy`, `Fetcher`, `Refresher`,
  `Config`, `Disposition`, `CATALOGUE`, …) so list/policy creation for a
  category can be automated from Python.

### Changed

- `refresh` now takes categories **positionally** (`egguard refresh adult
  malware`) instead of the repeatable `-C/--category` flag.
- `refresh --action ACTION` forces the action for the refreshed categories
  (`deny`/`warn`/`aup`/`permit`, with `block`/`allow` aliases), overriding
  config and catalogue suggestions for that run.
- Running `egguard` with no subcommand prints help and exits, instead of
  defaulting to a full refresh.

- Default `policies_dir` is now `/etc/enforcegate-shared/rules.d` to match the
  shared rules directory introduced in EnforceGate vX 2026.32.0. On older
  appliances, set `policies_dir: /etc/enforcegate-shared/policies` in the config.
- Documentation now reflects the Debian (bookworm-slim) toolbox shipped in
  2026.32.0 and its `python3-requests` / `python3-yaml` packages.

### Fixed

- Toolbox bridge passes the bare list/policy name (no path, no extension) to
  `enforcegate_toolbox.lists.write` / `policies.write`, which own the shared
  dirs and add the extension themselves. Full paths were rejected and a passed
  extension produced doubled names like `ut1-x.list.list`.
- In toolbox mode EGGuard no longer tries to create the shared `lists`/`rules.d`
  directories itself; the helper library owns and provisions them.

## [1.0.0] — 2026-06-16

### Added

- Initial release.
- `egguard refresh` — download every UT1 Capitole category, write an
  EnforceGate domain list and a matching `.policy` rule for each, and trigger a
  single live engine reload.
- `egguard list` — print the 66-category catalogue with the action resolved for
  each category under the current configuration.
- `egguard version`.
- Conditional HTTP downloads (ETag / If-Modified-Since) plus content-hash
  comparison, so unchanged categories are skipped and no needless engine reload
  is triggered.
- Per-category download state cached atomically on the toolbox volume.
- Bounded retries with exponential backoff per category.
- Decompression-bomb and path-traversal guards in the tarball parser.
- YAML configuration with per-category action overrides, a `default_action`
  fallback, and `include` / `skip` category selection.
- Toolbox launcher (`scripts/egguard`) that runs from a clone without
  `pip install`, plus `deploy/` config and cron templates.
- One-line JSON run summary for SIEM ingestion.
- Apache-2.0 license for the code; `NOTICE` carrying the upstream CC BY-SA 4.0
  attribution for the UT1 data.

[Unreleased]: https://github.com/parsymonie/egguard/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/parsymonie/egguard/releases/tag/v1.0.0

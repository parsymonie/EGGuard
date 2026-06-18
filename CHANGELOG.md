# Changelog

All notable changes to EGGuard are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Multi-source feeds: the catalogue is no longer UT1-only. A `Category` now
  carries a `source` (which namespaces its file/rule names as
  `<source>-<name>`) and a feed format, and the parser handles hosts-format
  lists in addition to UT1 tarballs.
- abuse.ch feeds: `urlhaus` (active malware hosts, ~600 domains) and
  `threatfox` (malware-IOC domains across many families, ~44,000), both `deny`
  by default and installable like any other category. They need a free Auth-Key
  (`abusech_auth_key` in config, or the `EGGUARD_ABUSECH_AUTH_KEY` env var when
  you'd rather keep the secret off disk). The key is sent as the `Auth-Key` HTTP
  header (never in a URL) and is redacted from logs/errors. Blank or placeholder
  keys are treated as unset, so installing an abuse.ch feed without a key
  reports that one is needed instead of failing on the download. A feed can name
  an absolute download URL, so feeds on different abuse.ch hosts work.
- Both `egguard list` and the `select` picker now show a SOURCE column
  (`UT1` / `abuse.ch`) so it is clear which feed each category comes from; the
  picker only adds the column when more than one source is present, and shows a
  column header.

### Changed

- Every run now reports how much was loaded: a `loaded N domains across M
  rules` line, and `rules` / `domains` totals in the one-line JSON summary (the
  picker's done screen shows the domain total too).
- Require Python **3.10+** (`requires-python = ">=3.10"`). The dataclasses use
  `slots=True`, which needs 3.10, so 3.9 never actually worked; the CI matrix
  drops 3.9 accordingly.

## [2.1.1] — 2026-06-18

### Fixed

- The picker no longer leaks the run's JSON onto the curses screen. The toolbox
  library writes its structured logs straight to stdout (not via Python
  logging), so the picker now skips the SIEM summary log during its run and
  captures stdout/stderr for the duration of the in-place install.

## [2.1.0] — 2026-06-18

### Added

- The `select` picker shows live per-category status from each run result
  (`+ adult  updated (N domains)`, `= … unchanged`, `! … failed: …`) and a
  one-line summary on the done screen (e.g. `4 updated, 0 unchanged | engine
  reloaded`). The progress bar is now a reverse-video fill.

### Fixed

- In the picker, the `a` key starts the action cycle from the action currently
  in effect, so the first press always advances (previously it was a no-op when
  the row was already on the displayed action).
- The picker no longer lets the install's log output corrupt the curses screen:
  Python logging is disabled and stderr is redirected for the duration of the
  in-place install.
- README: the "install once" step uses the in-toolbox launcher directly, since
  this toolbox's `repo run` does not forward `-- args`.

## [2.0.0] — 2026-06-17

### Added

- A pink curses category picker (`egguard select`): browse the catalogue
  (each row shows its current effective action), toggle with space, set a
  per-category action with `a`, then install in place with a progress bar. An
  alternative to the verbs; the pink theme is confined to this picker.
- `egguard help` prints the same top-level help as running with no arguments.
- Package-manager style CLI: `install CATEGORY…`, `update [CATEGORY…]`
  (refreshes the installed set; the cron command), `remove CATEGORY…`, and
  `list` (now marks installed categories). Categories are positional.
- `install`/`update --action ACTION` sets the action (`deny`/`warn`/`aup`/
  `permit`, with `block`/`allow` aliases). An action chosen on `install` is
  remembered, so a later `update` keeps it.
- The package is now importable as a library: `egguard` re-exports the public
  API (`get`, `extract_domains`, `render_policy`, `Fetcher`, `Refresher`,
  `Config`, `Action`, `CATALOGUE`, …) so list/policy creation for a category
  can be automated from Python. `Fetcher.fetch` no longer requires a state
  argument.

### Changed

- **Renamed** the `Disposition` action enum to `Action`.
- Replaced the single `refresh` command with `install`/`update`/`remove`.
- `egguard list` shows just the installed marker, name and action (the
  description column is gone).
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

[Unreleased]: https://github.com/parsymonie/egguard/compare/v2.1.1...HEAD
[2.1.1]: https://github.com/parsymonie/egguard/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/parsymonie/egguard/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/parsymonie/egguard/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/parsymonie/egguard/releases/tag/v1.0.0

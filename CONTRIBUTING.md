# Contributing to EGGuard

Thanks for your interest in improving EGGuard. This is a small, focused tool,
so the contribution process is light.

## Development setup

```bash
git clone https://github.com/parsymonie/egguard.git
cd egguard
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Before opening a pull request

Run the full local check suite — CI runs the same thing:

```bash
ruff check .            # lint
ruff format --check .   # formatting
mypy                    # static typing (strict)
pytest                  # tests
```

All four must pass. New behaviour should come with tests.

## Guidelines

- **Keep runtime dependencies to `requests` and `PyYAML`.** Both are
  pre-installed in the EnforceGate vX toolbox sidecar, which lets EGGuard run
  there without `pip install`. Adding a third runtime dependency needs a strong
  justification.
- **Target Python 3.9+.** Use `from __future__ import annotations` so modern
  typing syntax works on the older interpreters some Alpine images ship.
- **Keep the parser defensive.** It consumes third-party archives; preserve the
  decompression-size cap and path-traversal checks.
- **Never commit downloaded UT1 data or generated `.list` / `.policy` files.**
  They are runtime artefacts (and the data is CC BY-SA 4.0).

## Updating the category catalogue

The UT1 category set occasionally changes. The catalogue lives in
`src/egguard/categories.py`. When adding a category, include a concise English
description and a sensible default `Disposition`. Confirm the count and the
`egguard list` output still look right.

## Reporting issues

Use the issue templates. For parsing or download problems, include the category
name, the EGGuard version (`egguard version`), and the relevant log line.

## Licensing of contributions

By contributing you agree that your contributions are licensed under the
project's [Apache-2.0](LICENSE) license.

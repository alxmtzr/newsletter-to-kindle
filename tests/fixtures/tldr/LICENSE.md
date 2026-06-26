This directory contains sanitized TLDR newsletter `.eml` files used as test fixtures.

## Sanitization

All real `.eml` files must be sanitized before committing:
- `To:` and `Delivered-To:` headers replaced with `test@example.com`
- `Message-ID` replaced with a fixture identifier
- Tracking URLs replaced with `SANITIZED` placeholder paths
- Subscriber IDs, unsubscribe tokens, and personal data removed

Run `python scripts/sanitize_eml.py <input.eml> <output.eml>` to sanitize a new fixture.

## Copyright

These fixture files are abridged/redacted excerpts of TLDR newsletter emails,
used solely for automated testing of the parsing code.
TLDR content is © TLDR Newsletter (https://tldr.tech).
Use here constitutes fair use for software testing purposes only.

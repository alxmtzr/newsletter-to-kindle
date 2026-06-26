# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly.

**Contact:** dev.alxmtzr@gmail.com

I will acknowledge your report within one week and work to address confirmed issues promptly.

Please do not open public GitHub issues for security vulnerabilities.

## Scope

This is a personal automation tool. The attack surface is minimal — the application makes
outbound connections only (IMAP, SMTP, optional healthcheck ping) and exposes no inbound
network ports.

All credentials are stored in a `.env` file on the VPS host, never in the repository.

# Security Policy

## Supported Versions

`register-mcp` is pre-1.0; only the latest `main` and the most recent tagged
release receive security fixes.

| Version    | Supported          |
| ---------- | ------------------ |
| `main`     | :white_check_mark: |
| `0.1.x`    | :white_check_mark: |
| `< 0.1`    | :x:                |

## Reporting a Vulnerability

Please report security issues **privately**, not via public GitHub issues.

- Open a [GitHub Security Advisory](https://github.com/malkreide/register-mcp/security/advisories/new) — preferred.
- Or email the maintainer (see the GitHub profile of [@malkreide](https://github.com/malkreide)).

Include, if possible:

- A description of the issue and its impact
- Steps to reproduce or a proof-of-concept
- The affected version / commit SHA
- Any suggested mitigation

## Response Targets

| Step                | Target               |
| ------------------- | -------------------- |
| Acknowledgement     | within 5 working days|
| Triage & severity   | within 10 working days|
| Fix or mitigation   | best effort; critical issues are prioritised|

## Scope

This repository ships an MCP server that reads from the public Zefix REST API.
In-scope are:

- The Python package `register_mcp` (server, middleware, logging)
- The published Docker image
- CI workflows under `.github/workflows/`

Out of scope:

- Zefix-side API behaviour or data quality (report to `zefix@bj.admin.ch`)
- Issues only reproducible in a fork with modified middleware / auth removed
- Findings in dependencies — please file with the upstream project; we patch
  via Dependabot weekly.

## Hardening Notes for Operators

When deploying the SSE transport publicly, in addition to the built-in
`MCP_API_KEY` + rate limit:

1. Put a real gateway (Cloudflare Access, Railway internal networking,
   API-Gateway) in front of the container.
2. Restrict egress to `www.zefix.admin.ch:443` at the network layer.
3. Rotate `MCP_API_KEY` on a schedule and on personnel changes.
4. Forward the JSON logs to a SIEM and alert on sustained `auth_failed`
   or `rate_limited` events.

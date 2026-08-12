# Security Policy

## Reporting a vulnerability

Please use GitHub Private Vulnerability Reporting instead of opening a public issue.
Include affected versions, a minimal reproduction, and the potential impact. Repository
maintainers should enable private reporting under **Settings → Security → Code security**
before the first public release.

## Scope

Script Boundary parses untrusted source text and can optionally download repositories
listed in a local registry. It does not execute analyzed MATLAB code. Only use registry
entries you trust, keep revisions pinned to full commit SHAs, and review licenses before
redistributing any downloaded material.

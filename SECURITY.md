# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest  | ✅        |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.
Instead, e-mail the maintainers directly or use GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
feature. You should receive an acknowledgement within 48 hours.

## Scope

This policy applies to `taintrace` (`yunaremaia/taintrace`), including the
`action.yml` GitHub Action, the CI workflow templates, and the documentation
served from this repository.

Because `taintrace` reads third-party lockfiles and package registries, findings
that let a crafted lockfile or manifest cause the scanner to execute an
unexpected command, or that let attacker-controlled data escape into a
downstream SARIF or JSON report consumed by CI, are in scope.

## Safe Harbor

If you report a vulnerability in accordance with this policy, you will not be
subject to legal action or retaliation for good-faith security research.

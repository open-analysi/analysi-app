# Contributing to Analysi

Thanks for your interest in contributing. This document describes how to submit changes.

## License

Analysi is licensed under **AGPL-3.0-or-later**. By contributing, you agree that your contribution will be licensed under the same terms. See [LICENSE](LICENSE).

## Developer Certificate of Origin (DCO)

All contributions must be certified under the [Developer Certificate of Origin](https://developercertificate.org/). The DCO is a lightweight, contributor-friendly alternative to a Contributor License Agreement: you assert — on each commit — that you wrote the code (or otherwise have the right to submit it) and that it can be distributed under the project's license.

The full text (v1.1) reads:

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

### How to sign off

Add a `Signed-off-by` line to every commit message:

```
Signed-off-by: Jane Doe <jane@example.com>
```

Git can do this automatically:

```bash
git commit -s -m "Your commit message"
```

Configure `user.name` and `user.email` to match your real identity (pseudonymous sign-offs are not accepted).

To sign off a commit you already made:

```bash
git commit --amend --signoff
```

To sign off a range of past commits on a branch:

```bash
git rebase --signoff main
```

## Pull requests

1. Fork the repo and create a topic branch from `main`.
2. Make your changes with clear, focused commits (each `Signed-off-by`).
3. Run `poetry run ruff check --fix`, `poetry run ruff format`, and the relevant test suite (`make test-unit` at minimum).
4. Open a PR describing *what* you changed and *why*.

CI will verify that every commit in the PR carries a valid `Signed-off-by` line. PRs without sign-off will be asked to amend before review.

## Reporting security issues

Please do **not** open public issues for security vulnerabilities. See [SECURITY.md](SECURITY.md) for private reporting channels (GitHub Security Advisories or **openanalysi.security@gmail.com**).

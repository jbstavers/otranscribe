# Publishing (TestPyPI + PyPI)

This project uses **GitHub Actions + Trusted Publishing (OIDC)** to publish releases.
You should **not** publish from your local machine.

## Prerequisites

- You must be a maintainer of the project repo.
- Trusted Publishing must be configured in:
  - **PyPI** for this GitHub repo/workflow
  - **TestPyPI** for this GitHub repo/workflow
- The workflow file must exist on the commit you tag:
  - `.github/workflows/publish.yml`

## Versioning and tags

Publishing is triggered by **pushing a git tag** that starts with `v`.

We use two tag types:

### 1) Test releases (TestPyPI only)
Use **release candidate tags** containing `rc`:

- `v0.1.1-rc.1`
- `v0.1.1-rc.2`

These publish to **TestPyPI** only.

### 2) Final releases (PyPI only)
Use final tags without `rc`:

- `v0.1.1`
- `v0.2.0`

These publish to **PyPI** only.

## Release process

### A) Verify you are tagging the correct commit

```bash
git checkout main
git pull
git log -1 --oneline
ls .github/workflows/publish.yml

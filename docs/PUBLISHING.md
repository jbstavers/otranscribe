# Publishing

This project uses **GitHub Actions + Trusted Publishing (OIDC)** to publish releases to PyPI and TestPyPI.

**Do not publish from your local machine.** All releases go through GitHub Actions.

## Prerequisites

- You must be a maintainer of the project repo
- Trusted Publishing must be configured in:
  - **PyPI** for this GitHub repo/workflow
  - **TestPyPI** for this GitHub repo/workflow
- The workflow file `.github/workflows/publish.yml` must exist on the commit you tag

## Versioning

Publishing is triggered by pushing a git tag starting with `v`. Tags must follow **PEP 440** format.

**Critical: Tag format matters.** Incorrect format breaks `setuptools-scm` version detection.

### Test releases (TestPyPI only)
Use release candidate tags in format `vX.Y.ZrcN` (no dot before `rc`, no dash):

```
v0.1.1rc1
v0.1.1rc2
v1.0.0rc1
```

❌ Wrong: `v0.1.1-rc.1` or `v0.1.1rc.1`
✅ Right: `v0.1.1rc1`

### Final releases (PyPI only)
Use final tags in format `vX.Y.Z`:

```
v0.1.1
v0.2.0
v1.0.0
```

## Configuration

### setuptools-scm tag regex (pyproject.toml)

Ensure your `pyproject.toml` has the correct regex to match PEP 440 tags:

```toml
[tool.setuptools_scm]
tag_regex = "^v(?P<version>\\d+\\.\\d+\\.\\d+(?:rc\\d+)?)$"
```

This regex matches:
- `v0.1.1rc1` ✅ (RC, no dot before rc, no dash)
- `v0.1.1` ✅ (final release)
- `v0.1.1-rc.1` ❌ (wrong format)
- `v0.1.1rc.1` ❌ (wrong format)

### GitHub Actions checkout (publish.yml)

Ensure your workflow fetches full history so `setuptools-scm` can find tags:

```yaml
- name: Checkout
  uses: actions/checkout@v4
  with:
    fetch-depth: 0
```

The `fetch-depth: 0` removes shallow clones, ensuring tags are available for version discovery.

---

## Release workflow

### 1. Prepare main branch

Ensure `main` is ready:

```bash
git checkout main
git pull
git log -1 --oneline
```

Verify the workflow file exists:

```bash
ls .github/workflows/publish.yml
```

### 2. Update version

Update the version in your version source (typically `pyproject.toml` or `otranscribe/__init__.py`):

```toml
[project]
version = "0.2.0"
```

Commit:

```bash
git add pyproject.toml
git commit -m "bump: version 0.2.0"
git push
```

### 3. Tag the release

**Final release** (format: `vX.Y.Z`):

```bash
git tag v0.2.0
git push origin v0.2.0
```

**Test release** (format: `vX.Y.ZrcN` – no dot before `rc`, no dash):

```bash
git tag v0.2.0rc1
git push origin v0.2.0rc1
```

**If you created a broken tag** (e.g., `v0.2.0-rc.1` or `v0.2.0rc.1`), delete and recreate:

```bash
git tag -d v0.2.0-rc.1
git push --delete origin v0.2.0-rc.1

git tag v0.2.0rc1
git push origin v0.2.0rc1
```

### 4. Monitor the workflow

Go to your GitHub repo → **Actions** tab. You should see the publish workflow running.

- **Test release** (`*rc*`): publishes to TestPyPI
- **Final release** (no `rc`): publishes to PyPI

Check the workflow logs for errors. If `setuptools-scm` says "tag … no version found":
- Your tag format is wrong (see **Versioning** section above)
- Verify regex in `pyproject.toml` matches your tag
- Verify `checkout` has `fetch-depth: 0` (see **Configuration** section)

If it fails, delete the bad tag and create a new one with the correct format.

### 5. Verify the release

**For TestPyPI:**

```bash
pip install -i https://test.pypi.org/simple/ otranscribe==0.2.0rc1
```

**For PyPI:**

```bash
pip install --upgrade otranscribe
```

Check the package page:
- TestPyPI: https://test.pypi.org/project/otranscribe/
- PyPI: https://pypi.org/project/otranscribe/

## Troubleshooting

### setuptools-scm says "tag … no version found"

**Problem**: Your tag format doesn't match the regex in `pyproject.toml`.

**Common mistakes:**
- `v0.2.0-rc.1` ❌ (dash, dot before rc)
- `v0.2.0rc.1` ❌ (dot before rc)
- `v0.2.0rc1` ✅ (correct)

**Solution**:
1. Verify your tag format matches `vX.Y.ZrcN` (no dash, no dot before rc)
2. Check `pyproject.toml` has the correct regex:
   ```toml
   [tool.setuptools_scm]
   tag_regex = "^v(?P<version>\\d+\\.\\d+\\.\\d+(?:rc\\d+)?)$"
   ```
3. Verify `.github/workflows/publish.yml` has `fetch-depth: 0`
4. Delete the bad tag and create the correct one

### Checkout warning: shallow clone

**Problem**: Workflow logs show "shallow clone" warning. `setuptools-scm` can't find tags.

**Solution**: In `.github/workflows/publish.yml`, ensure checkout step includes:

```yaml
- name: Checkout
  uses: actions/checkout@v4
  with:
    fetch-depth: 0
```

### Workflow didn't trigger

- Tag must start with `v` (e.g., `v0.2.0`, not `0.2.0`)
- `.github/workflows/publish.yml` must exist on the tagged commit
- Check GitHub Actions logs for errors

### TestPyPI and PyPI both published

- You tagged with `rc` but it published to PyPI (shouldn't happen)
- Check the workflow logic in `.github/workflows/publish.yml`

### Need to re-publish the same version

- You can't re-push the same tag
- Create a new `rc` tag and test again, or bump to the next version

### Forgot to update version number

- Delete the tag locally and remotely, fix version, and retag:
  ```bash
  git tag -d v0.2.0
  git push --delete origin v0.2.0
  # fix version in pyproject.toml
  git add pyproject.toml
  git commit -m "fix: update version"
  git push
  git tag v0.2.0
  git push origin v0.2.0
  ```

## Notes

- **Trusted Publishing (OIDC)**: GitHub Actions authenticates with PyPI/TestPyPI without storing API keys. Credentials are short-lived and tied to the workflow run.
- **No local publishing**: Never generate and upload distributions manually. Always use the GitHub Actions workflow.
- **Pre-release workflow**: Test releases on TestPyPI first. Install and verify before publishing to PyPI.

## Memorize this

**Tag format rule** (PEP 440 compliant):
- RC tag: `vX.Y.ZrcN` (example: `v0.1.4rc1`)
- Final tag: `vX.Y.Z` (example: `v0.1.4`)

No dashes. No dots before `rc`. Non-negotiable.

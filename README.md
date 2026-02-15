# MinePainter

## GitHub Release Packaging

This repository has a release workflow at:

`/Users/ohirzel/Code/MinePainter/.github/workflows/release.yml`

When you push a tag that starts with `v` (example: `v0.1.0`), GitHub Actions will:

1. Build macOS and Windows binaries with PyInstaller.
2. Produce:
   - `MinePainter.app.zip` (contains `MinePainter.app`)
   - `MinePainter-windows.exe`
3. Attach both files to the GitHub Release for that tag.

Tag and push example:

```bash
git tag v0.1.0
git push origin v0.1.0
```

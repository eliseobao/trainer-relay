# Releasing TrainerRelay

## Local Windows build

Install Python 3.13 x64 and the pinned development requirements. From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
```

The script checks formatting, lints, runs tests, builds the executable, generates dependency notices, and packages:

- `release/TrainerRelay-0.1.0-windows-x64.zip` (version comes from `app_info.py`)
- `release/SHA256SUMS.txt`

The ZIP contains `TrainerRelay.exe`, user docs, this project's license, and full dependency notices. Extract all files. It bundles Python but not the ANT driver. No signing certificate is configured.

## GitHub release

1. Update `VERSION` in `app_info.py`, changelog, and any version examples in docs.
2. Run the local build, inspect the interface, and complete the documented hardware checks for radio changes.
3. Push the reviewed commit to `main` and wait for Checks to pass.
4. Create and push a matching tag, such as `v0.1.0`.
5. The release workflow independently builds on Windows, verifies the tag matches the application version, and publishes a **prerelease** containing the ZIP and checksums. Review the local notes, checksums, and artifact before pushing the tag. Prerelease status communicates the limited hardware coverage.

The workflow's repository token needs write access to contents. Fork pull requests only run checks and never publish. CI builds need no Bluetooth hardware and never start an ANT test.

Verify an extracted download using:

```powershell
Get-FileHash .\TrainerRelay-0.1.0-windows-x64.zip -Algorithm SHA256
```

Compare with `SHA256SUMS.txt` from the same release. Checksums detect corruption; they are not a code-signing identity.

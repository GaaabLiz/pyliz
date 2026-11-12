# Snapshot E2E tests

These tests exercise public snapshot operations against real files and directories. They do not download sample data or mock filesystem calls.

Run the complete E2E suite from the repository root:

```bash
./test/e2e/snap/run.py
```

Python can also launch it when the executable bit is unavailable:

```bash
python test/e2e/snap/run.py
```

Each run uses a unique directory under `test_local/snapshot_e2e`. Successful workspaces are removed. Failed workspaces are retained and their path is printed. Use `--keep` to retain successful runs too, or `--root /path/to/test-area` to put the isolated run beneath another local directory or mounted share. Additional pytest options go after `--`, for example `./test/e2e/snap/run.py -- --capture=tee-sys`.

The scenarios cover create and reload, capture manifests and empty directories, search, source synchronization, merge and replacement install, installed-copy removal, identity-based association edits, duplicate independence, snapshot and catalogue export/import, renamed standalone AD restore with destination mapping, SD recovery after deletion, integrity failures, and reporting missing source folders.

The existing tests under `test/core/os/snap` remain the unit and integration suite. The E2E suite is separate because it exercises long public workflows on a real filesystem. Run both with:

```bash
python -m pytest test/core/os/snap test/e2e/snap
```

Run the E2E runner on Windows, macOS, and Linux to cover each platform's filesystem behavior. Network share behavior requires running it with `--root` on a mounted test share; the local default cannot validate a remote server's permissions, durability, or disconnect behavior.

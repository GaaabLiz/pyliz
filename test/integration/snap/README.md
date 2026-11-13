# Snapshot integration tests

These tests exercise public snapshot operations against real files and directories using generated local data. The cleanup-failure scenarios patch `shutil.rmtree` to simulate interrupted cleanup. Each test gets a unique workspace under `test_local/snapshot_integration`, which is removed after success and retained after failure. The snapshot safety checks reject OS-managed temporary directories as destructive targets, so these scenarios need the repository's `test_local` area.

Run the integration suite from the repository root:

```bash
uv run pytest test/integration/snap -v
```

Use the executable runner when you want to choose the filesystem where the scenarios run:

```bash
./test/integration/snap/run.py
```

The runner defaults to a unique workspace under `test_local/snapshot_integration`. Successful workspaces are removed; failed workspaces are retained and their path is printed. Use `--keep` to retain successful runs, or `--root /path/to/mounted/share` to exercise another filesystem. Additional pytest options go after `--`, for example `./test/integration/snap/run.py -- --capture=tee-sys`.

The scenarios cover create and reload, capture manifests and empty directories, search, source synchronization, merge and replacement install, installed-copy removal, identity-based association edits, duplicate independence, snapshot and catalogue export/import, renamed standalone AD restore with destination mapping, SD recovery after deletion, integrity failures, and reporting missing source folders.

Unit tests live under `test/unit/core/os/snap`; integration scenarios are grouped by feature in this directory. They run on isolated local storage or, through the runner, on a mounted share. Run both groups with:

```bash
uv run pytest test/unit/core/os/snap test/integration/snap
```

Run the integration suite on Windows, macOS, and Linux to cover each platform's filesystem behavior. Network share behavior requires running the executable with `--root` on a mounted test share; local storage cannot validate a remote server's permissions, durability, or disconnect behavior.

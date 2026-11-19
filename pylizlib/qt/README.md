# Qt

`pylizlib.qt` contains PySide6-based components for desktop interfaces:
configuration and preferences, menus and toolbars, graphical resources,
widgets, and background tasks.

## Main areas

| Package or module | Contents |
| --- | --- |
| `domain/` | Types for configuration, preferences, themes, resources, and menus |
| `handler/` | Configuration, action, toolbar, and concurrent-operation handling |
| `util/` | Action creation and helpers for layouts and preferences |
| `widget/` | Reusable widgets such as path selectors and status bars |
| `scripts.py` | Generation of Qt resources and Python modules from `.qrc` and CSS files |
| `debug/` | Support for inspecting operations during development |

`Operation` and `OperationRunner` organize tasks, signals, progress, cancellation,
and concurrent execution. `ResHandler` and the types in `domain/` handle
graphical resources and themes.

To show the ETA at startup, pass an initial duration in seconds with
`OperationInfo("Search", "Search files", estimated_duration=8.0)`. The estimate
is recalibrated as tasks progress. Without an initial duration, the ETA appears
after two distinct progress updates, so preparation before the first update is
excluded from the work-rate calculation. The `op_eta_update` signal is emitted
whenever the displayed value changes.

## Dependencies and tests

Install the `qt` extra to use these components:

```bash
uv sync --extra qt
```

Unit tests are under `test/unit/qt/`; workflows using real widgets are under
`test/integration/qt/`.

# Qt Fluent Widgets

`pylizlib.qtfw` provides components based on PySide6-Fluent-Widgets for settings
and desktop interfaces. It includes configuration models, validators,
reusable widgets, and helpers for composing UIs.

## Main areas

| Package | Contents |
| --- | --- |
| `domain/` | Models for settings and software data |
| `model/` | Validators and helpers for Fluent configuration |
| `widgets/` | Cards, dialogs, inputs, progress indicators, and text elements |
| `util/` | Helpers for layouts and UI operations |
| `ui/` | Component demos |

## Dependencies and tests

The `qtfw` extra installs PySide6 and PySide6-Fluent-Widgets:

```bash
uv sync --extra qtfw
```

Unit tests are under `test/unit/qtfw/`; tests for composed workflows are under
`test/integration/qtfw/`. For general Qt components, see [qt/README.md](../qt/README.md).

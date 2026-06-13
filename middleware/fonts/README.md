# Badge fonts

`badges/generator.py` renders athlete badges (Issue #77) using these fonts,
resolved in priority order:

| Role | Preferred file (drop here) | System fallback |
|---|---|---|
| bold | `Inter-Bold.ttf` | Windows Arial Bold; Linux Liberation/DejaVu Sans Bold |
| regular | `Inter-Regular.ttf` | Windows Arial; Linux Liberation/DejaVu Sans |
| mono | `JetBrainsMono-Regular.ttf` | Windows Consolas; Linux Liberation/DejaVu Mono |

The Windows and Linux fallback fonts are scalable and support Vietnamese.
The renderer fails clearly when none are available instead of silently
producing missing-glyph boxes with Pillow's bitmap default.

Optional branding fonts:

- Inter: https://github.com/rsms/inter/releases
- JetBrains Mono: https://github.com/JetBrains/JetBrainsMono/releases

These TTFs are intentionally not committed to keep the repo lean. Inter and
JetBrains Mono remain optional branding upgrades; the checked system-font paths
provide a readable default on supported Windows and Linux environments.

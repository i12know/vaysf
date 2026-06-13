# Badge fonts

`badges/generator.py` renders athlete badges (Issue #77) using these fonts,
resolved in priority order:

| Role     | Preferred file (drop here)   | Why |
|----------|------------------------------|-----|
| bold     | `Inter-Bold.ttf`             | Title + athlete name. Full Vietnamese (Latin Extended) coverage. |
| regular  | `Inter-Regular.ttf`          | Church name, event-info rows, captions. |
| mono     | `JetBrainsMono-Regular.ttf`  | Athlete ID (fixed-width). |

If a preferred file is absent, the generator falls back to system Liberation
fonts, then to Pillow's built-in default — so rendering never hard-fails in
CI. For production-quality Vietnamese diacritics, add the Inter and JetBrains
Mono TTFs to this directory.

Download:
- Inter: https://github.com/rsms/inter/releases (Inter-Bold.ttf, Inter-Regular.ttf)
- JetBrains Mono: https://github.com/JetBrains/JetBrainsMono/releases

These TTFs are intentionally **not committed** to keep the repo lean; the
fallback chain covers local dev and CI without them.

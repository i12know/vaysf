# AGENTS.md — vaysf

Context and conventions for Codex when working on the VAY Sports Fest integration. Read this and the referenced skill before writing or modifying any code in this repo.

## Skills

This project uses the shared ChMeetings skill, vendored as a git submodule at:

    .Codex/skills/vay-chmeetings/skill/SKILL.md

Codex should read that file before writing any ChMeetings integration code, whenever a task touches the ChMeetings API, MCP server, webhooks, or the `CHM_FIELDS` mapping. The skill is authoritative for conventions shared across `vaysf`, `rp-pathway-app`, and `vdmansys`. Project-specific notes that don't belong in the shared skill are captured below in this file.

To update the skill to the latest upstream version:

    git submodule update --remote .Codex/skills/vay-chmeetings
    git add .Codex/skills/vay-chmeetings
    git commit -m "update vay-chmeetings skill to $(cat .Codex/skills/vay-chmeetings/VERSION)"

Upstream: https://github.com/i12know/vay-chmeetings-skill

## Project in one paragraph

`vaysf` is the production bridge between **ChMeetings** (where VAY Sports Fest participants register) and **WordPress on Bluehost** (where staff and pastors run the tournament). It runs on Windows, is written in Python (middleware, 64.5%) and PHP (WordPress plugin, 35.5%), and is MIT-licensed. Its job each season: pull registrations from ChMeetings, validate them against JSON rules, route pastor approvals through WordPress, build team rosters, and sync approval status back to ChMeetings groups — entirely via API, no Selenium, no manual Excel import.

## Tenant scope

This repo operates at the **VAY SM (a church) level** within the **VAY diocese** in ChMeetings. Bumble is the ChMeetings Owner for the VAY diocese. Any API key used by this project is scoped to VAY SM, not to Redemption Point and not to the Vietnamese District. Do not cross-wire scopes.

## Architecture

Three tiers, each with a narrow job:

1. **ChMeetings (core data)** — participant registration, profile management, church registration, team/group management, payment processing. This is the source of truth for *who registered*.
2. **Python middleware on Windows** — data synchronization, JSON-rule validation via Pydantic, error handling, logging. This is the orchestrator. All code lives under `middleware/`.
3. **WordPress plugin on Bluehost** — custom plugin exposing a REST API, pastor approval UI, admin dashboard, roster management, validation-issue tracking. This is what staff and pastors interact with day-to-day. Plugin code lives under `plugins/`.

Data generally flows: ChMeetings → middleware → WordPress for registration/validation, and WordPress → middleware → ChMeetings for approval sync.

## Repo layout

```
vaysf/
├── .Codex/skills/vay-chmeetings/   # shared skill (submodule, do not edit here)
├── docs/
│   ├── INSTALLATION.md
│   ├── USAGE.md
│   ├── ARCHITECTURE.md
│   ├── SEASON_TRANSITION.md
│   ├── CHMEETINGS_API_MIGRATION.md
│   ├── TROUBLESHOOTING.md
│   └── CONTRIBUTING.md
├── middleware/                      # Python, all middleware code lives here
│   ├── .env.template                # committed; real .env is gitignored
│   ├── requirements.txt
│   ├── main.py                      # CLI entry: sync, sync-churches, export-*
│   ├── tests/                       # pytest; mock by default, LIVE_TEST=true for real API
│   └── ...
├── plugins/                         # WordPress plugin (PHP)
│   └── vaysf.zip                    # distributable plugin (kept in repo)
├── chmeetings_openapi_v1.json       # snapshot of the ChMeetings OpenAPI spec
├── CHANGELOG.md
├── LICENSE                          # MIT
└── README.md
```

When Codex creates new files, they go in the language-appropriate tier — Python under `middleware/`, PHP under `plugins/`. Do not create a `src/` at the repo root; that's not the convention here.

## Setup and run

```bash
# From the middleware/ directory
cd middleware
pip install -r requirements.txt

# Configure credentials
copy .env.template .env
# edit .env with real values

# Run a full sync
python main.py sync --type full

# Sync churches from an Excel file
python main.py sync-churches --file "data/Church Application Form.xlsx"

# Sync approvals to ChMeetings (API-based; preferred)
python main.py sync --type approvals

# Sync approvals using the legacy Excel export (fallback only)
python main.py sync --type approvals --excel-fallback

# Sync a specific participant by ChMeetings ID (for debugging)
python main.py sync --type participants --chm-id <CHMEETINGS_ID>

# Export Excel reports for all church teams
python main.py export-church-teams

# Export Excel report for a single church
python main.py export-church-teams --church-code ABC
```

## Testing

```bash
# From middleware/, mock mode (default, no credentials required)
pytest tests/ -v

# Live mode — requires real API keys in .env
set LIVE_TEST=true && pytest tests/ -v -s
```

Mock mode is the default and is what CI runs. Live tests are run locally before a release. Fixtures under `tests/fixtures/` are real ChMeetings responses with PII redacted; when the schema shifts, re-record and commit new fixtures rather than patching around stale ones.

## Conventions specific to this repo

**API-first, always.** The v1.05/v1.06 releases specifically removed Selenium in favor of pure API calls and eliminated all manual Excel import steps. Do not reintroduce browser automation. Do not reintroduce manual Excel as a primary path — Excel export is a diagnostic fallback only (`--excel-fallback`).

**`CHM_FIELDS` is the only way to reference ChMeetings field names.** If you see a literal ChMeetings field string anywhere in middleware business logic, treat it as a bug. Update `CHM_FIELDS` and route through it. See the shared skill's §6 for the full pattern.

**Pagination uses `total_count`.** v1.05 introduced robust pagination via the API's `total_count` field. Never assume an empty page means the end; always reconcile against `total_count` and log the final tally.

**Run the field inspector before each release.** It detects new or renamed ChMeetings fields so we catch drift before it breaks production. If the inspector flags something, update `CHM_FIELDS` and note it in `CHANGELOG.md`.

**WordPress plugin versioning.** Plugin backups (`plugins/vaysf*.zip` except `vaysf.zip`) are gitignored. The current distributable is always `plugins/vaysf.zip`. When releasing a new plugin version, update the plugin header, rebuild `vaysf.zip`, and tag the release.

**Logging path.** `middleware/logs/` is gitignored. Do not commit log output. Log files follow the structured-logging conventions in the skill's §9.2 — include tenant (always `VAY SM`), scope, endpoint, status, duration, and a request ID.

**Bilingual names.** Participants have Vietnamese names with diacritics. Never lowercase or strip accents for display. Normalize for matching only, and always preserve the original for output. See the skill's §8.

## Validation rules

Validation is JSON-driven with Pydantic models. The rules live in a JSON file read at startup; changes to validation logic generally mean editing that JSON, not the Python code. When a rule change is needed:

1. Edit the rules JSON.
2. Add or update a fixture that exercises the new rule.
3. Run `pytest` (mock mode) to confirm the rule behaves as intended.
4. Note the rule change in `CHANGELOG.md` with a reference to the issue or request that motivated it.

## Pastor approval workflow

Pastors approve (or decline) their church's participants through the WordPress admin or via email link. The middleware pulls approval status from WordPress, then writes it back to ChMeetings group membership via API. If the API sync fails repeatedly, the `--excel-fallback` path is available but should be treated as a symptom that needs root-cause investigation, not a permanent workaround.

## Release workflow

1. All target issues for the release are closed or moved.
2. Field inspector run and any drift resolved.
3. `pytest` passes in mock mode and in `LIVE_TEST=true` mode.
4. `CHANGELOG.md` updated with the new version entry.
5. Tag the release (`git tag v1.0X`) and push tags.
6. If the WordPress plugin changed, rebuild `plugins/vaysf.zip` and commit it.

## Issue conventions

Issues are tracked on GitHub. When closing an issue via a commit, use the form:

```
<scope>: <imperative summary> — closes #N
```

Example:

```
middleware: centralize 429 retry logic into _api_request() — closes #64
```

## What NOT to do in this repo

- Do **not** add contributions/accounting/giving logic. That belongs in future RP or VD-level projects, not here.
- Do **not** add sermon or discipleship features. That's `rp-pathway-app`'s future scope.
- Do **not** add district-level cross-church reporting. That's `vdmansys`'s future scope.
- Do **not** generalize the code to "any church". The value of this repo is its VAY-specific fit.

When a feature request starts to feel like it doesn't quite belong, say so and propose the right home rather than stretching `vaysf` to cover it.

## Contact

Maintainer: Bumble — Lead Pastor at Redemption Point; Owner of VAY diocese in ChMeetings. API work in this repo targets the VAY SM church tenant.

For more documentation, see the files under `docs/`.

# Sports Fest Retrospectives — Index

Narrative records of how this system got built, covering 2016 through 2026.
These are history, not specification: for the technical state of the system read
`ARCHITECTURE_REVIEW_2026.md`, and for how to operate it read `USAGE.md` and
`SCHEDULE-HOW-TO.md`.

## The series

| Document | Era | Drafted by | Reconstructed from |
|---|---|---|---|
| [`RETROSPECTIVE_PODIO_2016_2024.md`](RETROSPECTIVE_PODIO_2016_2024.md) | 2016–2024 | Codex | Podio workspace + Globiflow XML archaeology |
| [`RETROSPECTIVE_2025.md`](RETROSPECTIVE_2025.md) | 2025 | Claude | 61 commits, CHANGELOG 0.1–1.04, the 2025 docs tree |
| [`RETROSPECTIVE_2026.md`](RETROSPECTIVE_2026.md) | 2026 (canonical) | Claude | 544 commits, 191 issues, release history |
| [`RETROSPECTIVE_2026_COMPANION.md`](RETROSPECTIVE_2026_COMPANION.md) | 2026 (companion) | Codex | Independent reflection, same season |

All four were reviewed and approved by Bumble.

## Reading order

Chronological is the right order — the arc only makes sense forward.

1. **`RETROSPECTIVE_PODIO_2016_2024.md`** — Access, then Podio and Globiflow.
   Nine seasons of accumulated operational knowledge, and the specific ways a
   platform-configured system becomes brittle: meaning hidden in display labels,
   validation buried in 128-step visual flows, annual behavior copied forward
   instead of versioned. Read this first; much of what follows is a set of
   countermeasures to it.
2. **`RETROSPECTIVE_2025.md`** — year one of the replacement. A good architecture
   designed largely before the repository existed, carried by manual Excel loops,
   Selenium, and an operator standing in the middle of it.
3. **`RETROSPECTIVE_2026.md`** — the season the system grew up. Seven dated acts,
   the CP-SAT solver that became a validator, and the identity problems that
   define the 2027 backlog. This is the canonical 2026 record.
4. **`RETROSPECTIVE_2026_COMPANION.md`** — a second reading of 2026 written the
   same morning. Preserved as an independent view and as provenance for findings
   folded into the canonical document, most importantly the Track & Field
   boundary.

If you only read one, read `RETROSPECTIVE_2026.md`. If you are deciding what to
build next, read the Podio document's *Open Migration Questions* alongside the
2026 document's *What 2027 inherits* — together they are the real backlog.

## The through-line

Each era solved the previous era's binding constraint and created the next one.

| Era | What it solved | What it left |
|---|---|---|
| Access | A custom database VAY controlled | Local files, desktop-only, no distribution |
| Podio + Globiflow | Cloud access for many churches and volunteers | Logic in platform config, no source control, no canonical identity |
| 2025 `vaysf` | Source-controlled rules, tested validation, API-first sync | Manual Excel loops, no CI, no tags, one load-bearing operator |
| 2026 `vaysf` | Scheduling, live scoring, results, public display | Identity drift, scheduling cockpit, Track & Field intake |

Two themes recur across all four documents and are worth naming directly:

- **Automation is only honest where the source of truth exists.** Track & Field
  in 2026 is the clean case study; the Podio-era `Ping Pong` / `Table Tennis`
  label hack is the same lesson wearing different clothes.
- **Human authority was never the obstacle.** Unstructured capture of that
  authority was — in Globiflow flow chains, in coordinator spreadsheets, in
  colored cells. Every era's biggest pain traces back to a decision that was made
  well and recorded badly.

## Conventions

- Named for the **era** they cover, not the tool that drafted them. Authorship and
  review status live in each document's header.
- Reconstructed from evidence — commits, issues, exported XML, changelogs — with
  inference marked inline as inference.
- No participant names, contact details, or other personal data.
- Historical records. When a claim is superseded, correct it in place and note
  the correction rather than silently rewriting the past.

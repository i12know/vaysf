# VAYSF Access/Office Era Retrospective, 1998-2015

*Drafted by Codex on 2026-07-28 from a read-only archaeology pass through the
VAY-SM Dropbox archive and a temporary copy of `SM2015.mdb`. Reviewed and
approved by Bumble.*

*This is the earliest document in the retrospective set — see
`RETROSPECTIVES.md` for the full series and reading order.
`RETROSPECTIVE_PODIO_2016_2024.md` picks up where the Access database leaves
off.*

> **On the date range.** The surviving artifacts are concentrated in 2015 and
> later: `SM2015.mdb` is the database that survived, and the Bible Challenge
> game files date from the same season. The 1998 start is attested by
> operational memory rather than by any file in the archive — earlier databases
> and their working files did not survive migration across machines and storage
> generations. Treat the schema, counts, and query names below as firmly
> evidenced for 2015, and the seventeen years before it as a period this
> document knows happened but cannot show.

## The First Digital Sports Fest Operating System

Before Podio, before ChMeetings, before the current `vaysf` middleware and WordPress plugin, VAY Sports Fest already had a digital operating system. It was built from Microsoft Access, Excel, Word, PowerPoint, PDFs, Photoshop files, printed forms, score sheets, badges, signage, and a lot of human judgment.

That matters because the current system did not invent the VAY Sports Fest operating model in 2026. Podio did not invent it in 2016 either. The operational grammar was already present in the Access era: churches, athletes, church reps, pastors, player numbers, primary and secondary sports, gender divisions, rosters, score sheets, Bible Challenge verses, rankings, staff, surveys, ceremonies, handbooks, deadlines, fees, badges, maps, and print packets.

The innovation of the Access/Office era was that VAY used the tools available at the time to turn a large, multi-church youth event into a database-backed operation. In the late 1990s and early 2000s, Microsoft Access was one of the few practical ways for a local ministry operator to build a custom application without hiring a software team. Access 97-era thinking was radical in a quiet way: tables, queries, forms, and reports could be assembled by one technically capable person into a working line-of-business application.

For Sports Fest, that meant the event could be more than a stack of paper forms. It could have a data model.

## Evidence Captured

This retrospective is based on a read-only archaeology pass through:

```text
S:\Dropbox\VAY-SM (Vu's)\
```

The most important artifact is:

```text
S:\Dropbox\VAY-SM (Vu's)\SM2015.mdb
```

I inspected a temporary copy of that database under the Windows temp directory so the Dropbox original would not be modified or locked. I extracted schema, table row counts, column names, saved query names, and query definitions where available. I did not copy participant rows, names, phone numbers, addresses, or other personal data into this document.

I also inspected the surrounding artifact ecosystem:

- Access databases, including the main `SM2015.mdb` and 2015 Bible Challenge game `.mdb` files.
- Excel workbooks used for schedules, questions, player registration exports, and later Bible Challenge tooling.
- PDFs for handbooks, score sheets, schedules, rankings, badges, surveys, and print packets.
- Photoshop, Illustrator, JPEG, GIF, and PNG files for badges, signage, ranking boards, name tags, and ceremony graphics.
- PowerPoint files for Bible Challenge games, opening/closing ceremonies, and later Bible quizzing/Jeopardy-style game flows.

The Dropbox folder currently contains hundreds of historical artifacts. By file type, it includes 135 PDFs, 88 PSD files, 57 XLSX workbooks, 46 PPTM files, 22 MDB databases, 18 DOC files, 17 PPT files, 16 CSV files, 15 AI files, and many image/audio/template files.

That distribution is itself part of the story. Access was the structured data core, but Office and Adobe files were the publication, ceremony, and print-production system around it.

## The Access Data Model

The 2015 Access database was not a single flat spreadsheet. It had a recognizable event schema.

Key tables included:

- `Main Athlete Table`: 389 athlete records.
- `Sports Festival's Teams`: 21 church/team records.
- `SM Staff`: staff records.
- `Bible Verses`: 208 scripture records.
- `Bible Challenge`: Bible Challenge game/scoring records.
- Sport game tables for Basketball, Volleyball, Badminton, Ping Pong, Tennis, Track & Field, and Tug-of-war style events.
- Sport-specific roster tables split by gender and event.
- `Rankings`: bracket/ranking state.
- `Team Scoring System`: team points by church/team.
- `Survey`: post-event or participant feedback fields.
- Raw, backup, blank, import-error, and paste-error tables.

The main athlete table used the essential fields that still echo through the current system:

- Church ID.
- Player number.
- First, middle, and last name.
- Gender.
- Primary sport.
- Secondary sport.
- Birthdate.

The raw and blank athlete tables had a wider intake model, including phone, address, city, state, zip, emergency contact, emergency phone, emergency relationship, status, email, notes, Track & Field, swimming, medical release, signature, balance, payment, late payment, lost name tag, qualified, staff ID, photo, and ID badge fields.

That is striking. The Access-era model already understood that a participant was more than a name on a roster. A participant had identity, eligibility, emergency contact, consent, payment, notes, photo/badge output, and status.

It is worth stating the implication directly, because it changes how a piece of current work should be read. `REGISTRANT_TRUST_RFC.md` (epic #307) is the 2026 effort to give `vaysf` a first-class model of roles, verification, consent, and guardian relationships. Set against this table, that RFC is not introducing a new concept — it is **recovering one the operation had in 2015 and lost across two migrations**. Emergency contact and relationship, medical release, signature, qualified status, and payment state were all columns in a single Access table. They became scattered across Podio apps and Globiflow flows, then across ChMeetings fields, WordPress rows, and consent forms. The 2026 work is closing a loop, not opening one.

## The 2015 Season In The Database

The 2015 `Main Athlete Table` had 389 rows. By gender, the database showed:

- Female: 144.
- Male: 245.

Primary sport distribution:

- Volleyball: 196.
- Basketball: 101.
- Bible Challenge: 37.
- Tennis: 18.
- Ping Pong: 8.
- Blank primary sport: 29.

Secondary sport distribution:

- Blank secondary sport: 254.
- Volleyball: 54.
- Basketball: 33.
- Ping Pong: 22.
- Bible Challenge: 22.
- Tennis: 4.

The records were distributed across church/team codes such as TLC, ORN, MWC, SGV, RPC, GGP, ANH, SFV, NHC, GLA, OCC, WAG, LBC, and OCB.

This looks familiar because the core registration shape has barely changed. The system still needs to know who belongs to which church, which sport they entered, whether a sport is primary or secondary, and how to turn that into rosters, schedules, badges, and event-day accountability.

## Queries As Automation

The saved Access queries are the clearest evidence of the old programming model.

The database had delete/reset queries for sport tables:

- Delete Bible Challenge table.
- Delete Double Ping Pong.
- Delete Double Tennis.
- Delete Men's Basketball.
- Delete Men's Volleyball.
- Delete Women's Volleyball.
- Delete Men's/Women's Ping Pong.
- Delete Men's/Women's Tennis.
- Delete Men's/Women's Badminton.

It also had make-table queries that generated rosters from the main athlete table:

- Make Basketball Roster Table.
- Make Bible Challenge Roster Table.
- Make Men's Volleyball Roster Table.
- Make Women's Volleyball Roster Table.
- Make Men's Ping Pong Roster Table.
- Make Women's Ping Pong Roster Table.
- Make Men's Tennis Roster Table.
- Make Women's Tennis Roster Table.
- Make Men/Women Double Badminton Roster Table.
- Make Men/Women Swimming Roster Table.
- Make Mix Double Tennis Roster Table.
- Make Double Ping Pong Roster Table.

The pattern was simple but powerful:

```text
Main Athlete Table
  -> filter by gender and Primary Sport / Secondary Sport text
  -> create sport-specific roster table
  -> feed forms, reports, score sheets, badges, and print output
```

This is the ancestor of two later systems:

```text
Access make-table roster queries
  -> Podio/Globiflow sports-list recalculation
  -> vaysf structured roster export and validation logic
```

The Access queries also show the old brittleness. Sports were text fields. Gender was text. A query found eligible athletes by expressions such as "gender like M" and "Primary Sport like Volleyball." That worked because a human operator controlled the environment. It became harder as registration moved online, participants self-entered information, and multiple systems started holding related identity data.

But for its time, it was an elegant solution. It took one master registration table and turned it into every sport's working roster.

## Forms And Reports As The User Interface

Access was not just a database. It was the user interface and reporting engine.

The database exposed form/report-related object names that reveal how operators likely interacted with it:

- Athlete Registration.
- Sports Festival's Teams.
- SM Staff.
- Survey.
- Bible Verses and Bible Verses Subform.
- Bible Challenge and team subforms.
- Basketball, Volleyball, Badminton, Ping Pong, Tennis, and Track & Field entry forms.
- Track & Field Page 2 and Page 3.
- Ranking System and Bible Challenge Ranking System.

It also had report outputs for:

- ID Badge Label - Church.
- ID Badge Label - General.
- ID Badge Label - Tournament.
- Men's and Women's Volleyball score sheets.
- Basketball score sheets.
- Badminton score sheets.
- Ping Pong score sheets.
- Tennis score sheets.
- Bible Challenge score sheets.
- Track & Field score sheets for 100M, 200M, 400M, relay, mile/half-mile, and Tug-of-war.
- Rankings and Bible Challenge ranking.
- Men's Volleyball roster and team subreports.

This is the important Access-era lesson: the system was not just storing data; it was producing paper. Access reports were the bridge between structured data and event-day operations. A query generated a roster table. A report turned that data into a score sheet, badge label, ranking sheet, or printable packet.

The current `vaysf` system is still solving the same problem, just with different tools.

## Bible Challenge As A Parallel System

Bible Challenge had its own unusually rich artifact trail.

The 2015 Bible Challenge folder contained:

- A schedule workbook with tabs for 11-team and 12-team formats.
- A question workbook with tabs for Prelim 1-12, semifinal groups, finals, categories, and questions.
- Word documents for prelim, semifinal, final, and translated question sets.
- PowerPoint files for each final/prelim game.
- PDFs for each game.
- Small Access `.mdb` files for individual games.

One representative game database, `Prelim 1.mdb`, contained:

- `tblCategories`: 6 rows.
- `tblQuestions`: 26 rows.

This shows that Bible Challenge was not merely another sport inside the main database. It had its own content-management and game-production workflow. Questions were authored in Word/Excel, converted into Access-like game databases, exported into PDFs or PowerPoint decks, and then used in live competition.

That is the historical ancestor of the later Bible Challenge verse bank in Podio and the 2026 WordPress Bible Challenge verse-management and scoring work.

The deeper continuity is not technical; it is operational. Bible Challenge always needed:

- A question/verse source.
- A schedule.
- Teams and players.
- Host/judge coordination.
- Game packets or presentation decks.
- Score capture.
- Advancement or final placement.

The tools changed. The workflow need stayed.

## Office And Adobe As The Event-Day Publishing Stack

The Dropbox archive makes it impossible to describe the Access era as "just Access."

The surrounding files show a full event-publishing stack:

- Photoshop and Illustrator files for church badges, staff badges, name tags, signage, rankings, and ceremony graphics.
- PDFs under `Files To Print` for many church codes.
- Staff and executive staff badge pages.
- Opening ceremony graphics and presentation files.
- Closing ceremony and worship/event slides.
- Ranking graphics for Basketball, Volleyball, Tennis, Badminton, Ping Pong, and Bible Challenge.
- Score sheet PDFs for sport-specific preliminary, quarterfinal, semifinal, and final rounds.
- Survey PDFs.
- Maps, campsite assignments, and handbooks.

In other words, a lot of what looks "new" in the 2026 application is actually old Sports Fest knowledge moving from static printable artifacts into structured software.

## The Publishing Stack Outlived Two Migrations

The most consequential thing the archive shows is something the era boundaries obscure.

Podio replaced the Access **database** around 2016. It did not replace the Office and Adobe **publishing stack**, which kept running largely unchanged for years afterward — which is why several of the clearest artifacts in this archive are dated well inside the Podio era:

- **`NameTag.jpg` (2017)** — a badge background carrying annual theme, logo, year, and venue, with empty space reserved for participant-specific data. The same pattern reappears in Podio badge-generation flows and again in the 2026 `vaysf` hosted-badge work.
- **Ranking graphics (2018)** — bracket boards with seeds, church codes, game times, courts, quarterfinals, semifinals, final, and third-place game. The direct ancestor of 2026 playoff advancement and the public bracket display.
- **Schedule image (2019)** — the schedule grammar that still exists today: multiple weekends, venue columns, time rows, setup blocks, opening ceremony, dinner and chapel hour, community time, sport colors, playoffs, finals, and a version marker.

These are catalogued here rather than in `RETROSPECTIVE_PODIO_2016_2024.md` because they belong to a lineage that begins in the Access era and does not break at the platform boundary. Read across the whole series, the pattern is clear enough to state plainly:

> The database migrated twice. The publishing pipeline did not migrate at all — it was carried forward by hand, season after season, in Photoshop and Illustrator files.

That is why badge generation, score sheets, ranking boards, and printable schedules were among the *last* capabilities to be absorbed into software, arriving only with the 2026 badge-image, scoresheet, and public-display work. It also explains why `RETROSPECTIVE_PODIO_2016_2024.md` lists badge generation and document production among the Podio-era capabilities `vaysf` had not yet fully rebuilt: those workflows were never fully in Podio either. They lived in design files and an operator's hands from the Access era straight through to 2026.

## The Handbook And Policy Layer

The 2018 handbook is later than the Access-to-Podio transition, but it preserves the policy structure that grew out of the earlier era. Its table of contents included:

- Introduction.
- Mission and vision.
- Implementation plan.
- Policies and guidelines.
- Procedures and fees.
- Sport rules and regulations.
- Facility and parking information.
- Committee staff contact information.
- Church registration forms.
- Participant application forms.
- Medical release and disclaimer forms.
- Dates and deadlines.
- Proof of insurance certificate.

That is the non-code operating system. Access could store athletes and generate score sheets, but the handbook defined what the data meant and how humans should act on it.

This division still matters. `vaysf` can encode rules, permissions, rosters, approvals, schedules, and results. But policy decisions still have to come from the ministry and tournament leadership. The best software in this lineage has always been the part that faithfully carried those decisions into operations.

## What Was Innovative

The Access-era system was innovative because it gave a volunteer ministry an internal application years before "no-code" and "low-code" became common language.

It combined:

- A relational-ish data model.
- Custom data-entry forms.
- Saved queries as repeatable transformations.
- Reports as printable event-day artifacts.
- Office integration for Excel, Word, PowerPoint, and PDF workflows.
- Adobe design files for public-facing materials.
- Manual operator judgment where automation would have been too expensive.

The event was too complex for paper alone. It needed:

- Hundreds of participants.
- Dozens of church teams.
- Multiple sports.
- Gender divisions.
- Primary and secondary sport handling.
- Score sheets and rosters.
- Bible Challenge content.
- Track & Field and Tug-of-war result structures.
- Staff assignments.
- Badges and signage.
- Schedules, ceremonies, and handbooks.

Access made that complexity manageable by giving VAY a custom tool shaped around its own event. That was a genuinely advanced use of the technology available to a local ministry at the time.

## What Became Difficult

The same strengths eventually became limits.

Access was powerful, but it was local. It assumed a small number of operators with access to the file, the right Windows environment, and the knowledge to run the right queries/reports in the right order.

The workflow depended on:

- Manual data entry or copy/paste from forms and spreadsheets.
- Text consistency in sport fields.
- Human control of when delete/make-table queries were run.
- Local report generation.
- Manual distribution of PDFs, schedules, badges, and score sheets.
- Knowledge embedded in one person's habits.
- Files and folders as the archive.

That model could work beautifully when one operator understood the whole machine. It became harder as Sports Fest needed distributed church registration, remote collaboration, web intake, online approvals, and a shared operational surface.

That is why Podio was attractive. It did not replace a failed Access system. It gave a successful Access system the cloud collaboration layer it did not naturally have.

## How This Led To Podio

The move from Access to Podio can be read as a very logical next step:

- Access tables became Podio apps.
- Access records became Podio items.
- Access fields became Podio fields.
- Access forms became Podio forms/webforms.
- Access queries became Podio views and Globiflow filters.
- Access reports became PDFs generated through Globiflow and external document services.
- Access manual workflows became status fields, comments, emails, and workflow triggers.
- Local file outputs became Dropbox/PDF/email artifacts.

Podio kept the important idea: Sports Fest should be modeled as data. But it moved that data into a collaborative cloud environment.

Globiflow then restored the automation power that Access queries, forms, and reports had provided locally. The 2024 Podio system's sports-list recalculation flow is recognizably the grandchild of the Access make-table roster queries. It solved the same problem: take messy registration selections and turn them into sport-specific operational lists.

## How This Led To `vaysf`

The current `vaysf` system is the third phase of the same long project.

Access proved that Sports Fest could be modeled.

Podio proved that the model needed to be collaborative and cloud-accessible.

`vaysf` is proving that the model also needs to be source-controlled, testable, API-first, and live-event aware.

The deepest technical lineage looks like this:

```text
Access 97-era tables, forms, queries, and reports
  -> Podio apps, views, comments, and Globiflow automations
  -> ChMeetings + Python middleware + WordPress operational system
```

The operational lineage looks like this:

```text
Paper forms and local database
  -> cloud registration and workflow records
  -> API-backed registration, validation, approvals, scheduling, scoring, and results
```

And the artifact lineage looks like this:

```text
Access reports, PDFs, PSD badges, printed score sheets, and schedule images
  -> Podio-generated PDFs and badge workflows
  -> vaysf-generated workbooks, score sheets, badge images, live schedules, and public results
```

The current system should preserve that lineage consciously. The old artifacts were not accidental clutter. They were the visible surface of a real operating framework.

## What To Remember

1. The modern Sports Fest system stands on a long data-modeling tradition.
2. Access was not primitive in context. It was a powerful local application platform for its time.
3. The Access system already understood the major entities: churches, athletes, sports, rosters, staff, score sheets, rankings, Bible Challenge content, and badges.
4. Queries were the first automation layer.
5. Reports were the first event-day UI.
6. Office and Adobe files were the first publishing pipeline.
7. Podio was the cloud successor to Access, not a replacement for a failed experiment.
8. `vaysf` is the source-controlled successor to Podio, not a rejection of the old systems.
9. Some operational wisdom still lives only in historical artifacts.
10. Future development should ask not only "what should the software do?" but "which old artifact was doing this job before?"

## The Historical Judgment

The Access/Office era should be remembered as the first serious digital transformation of VAY Sports Fest.

It took a large, complicated, multi-church event and gave it a custom operational backbone. It produced rosters, score sheets, rankings, badges, schedules, Bible Challenge materials, staff artifacts, and print packets. It made the event repeatable before the tools were collaborative. It gave later systems a vocabulary to inherit.

The best way to honor that era is not nostalgia and not replacement for replacement's sake. It is careful translation.

When `vaysf` turns a printed score sheet into a structured result, it is translating the Access report era.

When it turns a badge PSD and roster table into a generated hosted badge image, it is translating the print-production era.

When it turns a sport text field into a canonical sport code, it is translating the make-table query era.

When it turns Bible Challenge decks and question sheets into manageable seed data and scoring workflows, it is translating the Bible Challenge side system.

The past was more sophisticated than it first looks. The future will be better if it remembers that.


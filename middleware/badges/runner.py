# badges/runner.py
"""
BadgeRunner — orchestrates v1 athlete-badge generation (local render only).

Pipeline per participant:
  1. Fetch approved participants from WordPress (canonical source for name,
     church, sport, approval state).
  2. Resolve the profile photo from the ChMeetings person record (``photo``),
     falling back to the WordPress ``photo_url``; if neither is usable the
     generator draws an initials placeholder.
  3. Render the PNG locally via BadgeGenerator.

No WordPress upload or ChMeetings write-back happens in v1 — those are a
deliberate follow-up (see Issue #77 plan comment).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests
from loguru import logger
from tqdm import tqdm

from badges.generator import BadgeGenerator

# Approval statuses that count as "approved" for badge eligibility.
APPROVED_STATUSES = {"approved"}

_PAGE_LIMIT = 50          # safety cap on pagination loops
_PER_PAGE = 100


class BadgeRunner:
    """Drives badge generation against live (or mocked) connectors."""

    def __init__(self, chm_connector, wp_connector, generator: Optional[BadgeGenerator] = None) -> None:
        self.chm = chm_connector
        self.wp = wp_connector
        self.generator = generator or BadgeGenerator()
        self._church_names: Optional[Dict[str, str]] = None

    # ── Public entry point ─────────────────────────────────────────────────────

    def run(
        self,
        *,
        church_code: Optional[str] = None,
        chm_id: Optional[str] = None,
        dry_run: bool = False,
        force: bool = False,
    ) -> bool:
        """Generate badges for approved athletes.

        Args:
            church_code: Limit to a single church (by code).
            chm_id: Limit to a single ChMeetings person ID.
            dry_run: List who would be rendered; write nothing, fetch no photos.
            force: Re-render even when a current PNG already exists.

        Returns:
            True if the run completed without fatal errors.
        """
        scope = (
            f"chm_id={chm_id}" if chm_id
            else f"church={church_code}" if church_code
            else "all approved athletes"
        )
        mode = "[DRY RUN] " if dry_run else ""
        logger.info(f"{mode}Generating athlete badges — scope: {scope}")

        participants = self._fetch_approved_participants(church_code=church_code, chm_id=chm_id)
        if not participants:
            logger.warning("No approved participants matched the requested scope; nothing to do.")
            return True

        logger.info(f"{len(participants)} approved athlete(s) to process "
                    f"(output: {self.generator.output_dir})")

        rendered = skipped = errors = 0
        for p in tqdm(participants, desc="Rendering badges", unit="badge"):
            name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip() or p.get("chmeetings_id")
            if not str(p.get("chmeetings_id") or "").strip():
                skipped += 1
                logger.warning(
                    f"Skipping approved participant without chmeetings_id: "
                    f"wp_participant_id={p.get('participant_id')}, name={name or 'unknown'}"
                )
                continue
            if dry_run:
                logger.info(f"[DRY RUN] Would render badge for {name} "
                            f"(chm_id={p.get('chmeetings_id')}) -> {self.generator.filename_for(p)}")
                rendered += 1
                continue
            try:
                self._enrich(p)
                photo_bytes = self._fetch_photo_bytes(p)
                out_path = self.generator.render_to_file(p, photo_bytes=photo_bytes, force=force)
                if self.generator.last_write_skipped:
                    skipped += 1
                else:
                    rendered += 1
                logger.debug(f"Badge ready for {name}: {out_path.name}")
            except Exception as e:  # noqa: BLE001 - one bad record shouldn't abort the batch
                errors += 1
                logger.error(f"Failed to render badge for {name} "
                             f"(chm_id={p.get('chmeetings_id')}): {e}")

        logger.info(f"{mode}Badge generation complete — rendered={rendered}, "
                    f"skipped={skipped}, errors={errors}")
        return errors == 0

    # ── Data fetching ──────────────────────────────────────────────────────────

    def _fetch_approved_participants(
        self, *, church_code: Optional[str], chm_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        if chm_id:
            matches = self.wp.get_participants({"chmeetings_id": chm_id}) or []
            return [p for p in matches if self._is_approved(p)]

        params_base: Dict[str, Any] = {"approval_status": "approved"}
        collected: List[Dict[str, Any]] = []
        page = 1
        while True:
            params = {**params_base, "page": page, "per_page": _PER_PAGE}
            batch = self.wp.get_participants(params) or []
            if not batch:
                break
            # Server-side filter is best-effort; re-check client-side so a lenient
            # endpoint can't leak non-approved athletes into the run.
            collected.extend(p for p in batch if self._is_approved(p))
            if len(batch) < _PER_PAGE:
                break
            page += 1
            if page > _PAGE_LIMIT:
                logger.warning(f"Reached page limit ({_PAGE_LIMIT}); stopping participant fetch.")
                break

        if church_code:
            wanted = church_code.strip().upper()
            collected = [p for p in collected if (p.get("church_code") or "").strip().upper() == wanted]
        return collected

    def _enrich(self, participant: Dict[str, Any]) -> None:
        """Add the church display name (and ChMeetings names if WP lacks them)."""
        code = (participant.get("church_code") or "").strip().upper()
        if code and "church_name" not in participant:
            names = self._church_name_map()
            if code in names:
                participant["church_name"] = names[code]

    def _fetch_photo_bytes(self, participant: Dict[str, Any]) -> Optional[bytes]:
        """Resolve the photo URL (ChMeetings first, then WordPress) and download it.

        Logs which source was used: ``chm_photo``, ``wp_fallback``, or ``initials``
        (initials is logged here as ``None`` and the caller logs "initials" when
        this method returns ``None``).
        """
        chm_id = str(participant.get("chmeetings_id") or "")
        photo_url = None
        photo_source = None
        if chm_id:
            person = self.chm.get_person(chm_id)
            if person:
                chm_photo = person.get("photo")
                if chm_photo and str(chm_photo).startswith(("http://", "https://")):
                    photo_url = chm_photo
                    photo_source = "chm_photo"
                # Backfill names from ChMeetings when WordPress didn't carry them.
                for key in ("first_name", "last_name"):
                    if not participant.get(key) and person.get(key):
                        participant[key] = person[key]
        if not photo_url:
            wp_url = participant.get("photo_url")
            if wp_url and str(wp_url).startswith(("http://", "https://")):
                photo_url = wp_url
                photo_source = "wp_fallback"
        if not photo_url:
            logger.info(
                f"Photo source=initials for chm_id={chm_id} "
                f"(no usable URL from ChMeetings or WordPress)"
            )
            return None
        try:
            resp = requests.get(photo_url, timeout=(5, 20))
            resp.raise_for_status()
            logger.info(
                f"Photo source={photo_source} for chm_id={chm_id} ({photo_url})"
            )
            return resp.content
        except requests.RequestException as e:
            logger.warning(
                f"Could not download photo for chm_id={chm_id} ({photo_url}): {e} "
                f"— falling back to initials"
            )
            return None

    def _church_name_map(self) -> Dict[str, str]:
        if self._church_names is None:
            self._church_names = {}
            try:
                for c in self.wp.get_churches() or []:
                    code = (c.get("church_code") or "").strip().upper()
                    name = (c.get("church_name") or "").strip()
                    if code and name:
                        self._church_names[code] = name
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Could not load church names: {e}")
        return self._church_names

    @staticmethod
    def _is_approved(participant: Dict[str, Any]) -> bool:
        return str(participant.get("approval_status") or "").strip().lower() in APPROVED_STATUSES

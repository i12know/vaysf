# badges/runner.py
"""
BadgeRunner orchestrates athlete-badge generation and optional hosting.

Pipeline per participant:
  1. Fetch approved participants from WordPress (canonical source for name,
     church, sport, approval state).
  2. Resolve the profile photo from the ChMeetings person record (``photo``),
     falling back to the WordPress ``photo_url``; if neither is usable the
     generator draws an initials placeholder.
  3. Render the PNG locally via BadgeGenerator.
  4. Optionally upload the PNG to WordPress uploads for public hosting.
  5. Optionally write the hosted badge URL back to a dedicated ChMeetings
     one-line text custom field.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
from loguru import logger
from PIL import Image
from tqdm import tqdm

from badges.generator import BadgeGenerator
from badges.uploader import WordPressBadgeUploader
from config import CHECK_BOXES, CHM_FIELDS, SF_CHECKLIST_OPTIONS, SF_FIELD_IDS, Config

# Approval statuses that count as "approved" for badge eligibility.
APPROVED_STATUSES = {"approved"}

_PAGE_LIMIT = 50          # safety cap on pagination loops
_PER_PAGE = 100


class BadgeRunner:
    """Drives badge generation against live (or mocked) connectors."""

    def __init__(
        self,
        chm_connector,
        wp_connector,
        generator: Optional[BadgeGenerator] = None,
        badge_uploader: Optional[WordPressBadgeUploader] = None,
    ) -> None:
        self.chm = chm_connector
        self.wp = wp_connector
        self.generator = generator or BadgeGenerator()
        self.badge_uploader = badge_uploader
        self._church_names: Optional[Dict[str, str]] = None
        self._badge_url_field: Optional[Tuple[int, str]] = None

    # ── Public entry point ─────────────────────────────────────────────────────

    def run(
        self,
        *,
        church_code: Optional[str] = None,
        chm_id: Optional[str] = None,
        dry_run: bool = False,
        force: bool = False,
        upload: bool = False,
        write_chmeetings_badge_url: bool = False,
    ) -> bool:
        """Generate badges for approved athletes.

        Args:
            church_code: Limit to a single church (by code).
            chm_id: Limit to a single ChMeetings person ID.
            dry_run: List who would be rendered; write nothing, fetch no photos.
            force: Re-render even when a current PNG already exists.
            upload: Upload each generated PNG to WordPress after local render.
            write_chmeetings_badge_url: Store the hosted badge URL in the
                ChMeetings Sports Fest Badge URL text field. Requires upload.

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
        if write_chmeetings_badge_url and not upload:
            logger.error("--write-chmeetings-badge-url requires --upload so ChMeetings receives a hosted URL.")
            return False
        if write_chmeetings_badge_url and not dry_run:
            try:
                self._badge_url_field_definition()
            except ValueError as exc:
                logger.error(f"Badge URL write-back configuration error: {exc}")
                return False

        logger.info(f"{len(participants)} approved athlete(s) to process "
                    f"(output: {self.generator.output_dir})")

        uploader = None if dry_run or not upload else (
            self.badge_uploader or WordPressBadgeUploader(self.wp)
        )
        rendered = skipped = uploaded = chm_updated = errors = 0
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
                if upload:
                    logger.info(f"[DRY RUN] Would upload badge filename={self.generator.filename_for(p)}")
                if write_chmeetings_badge_url:
                    logger.info(
                        f"[DRY RUN] Would write hosted badge URL to ChMeetings "
                        f"field {CHM_FIELDS['BADGE_URL']!r} for chm_id={p.get('chmeetings_id')}"
                    )
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
                if uploader is not None:
                    upload_result = uploader.upload_badge(out_path)
                    uploaded += 1
                    if write_chmeetings_badge_url:
                        self._write_badge_url_to_chmeetings(p, upload_result.url)
                        chm_updated += 1
                logger.debug(f"Badge ready for {name}: {out_path.name}")
            except Exception as e:  # noqa: BLE001 - one bad record shouldn't abort the batch
                errors += 1
                logger.error(f"Failed to process badge for {name} "
                             f"(chm_id={p.get('chmeetings_id')}): {e}")

        logger.info(f"{mode}Badge generation complete — rendered={rendered}, "
                    f"skipped={skipped}, uploaded={uploaded}, errors={errors}")
        if write_chmeetings_badge_url:
            logger.info(f"{mode}ChMeetings badge URL profiles updated={chm_updated}")
        return errors == 0

    # ── Data fetching ──────────────────────────────────────────────────────────

    def _badge_url_field_definition(self) -> Tuple[int, str]:
        """Return the ChMeetings field_id/type for the badge URL text field."""
        if self._badge_url_field is not None:
            return self._badge_url_field

        configured_id = int(SF_FIELD_IDS.get("BADGE_URL") or 0)
        expected_name = CHM_FIELDS["BADGE_URL"]
        if configured_id:
            self._badge_url_field = (configured_id, "text")
            return self._badge_url_field

        fields = self.chm.get_member_fields() or []
        for field in fields:
            if str(field.get("field_name") or "").strip() != expected_name:
                continue
            field_id = int(field.get("field_id") or field.get("id") or 0)
            field_type = str(field.get("field_type") or "text").strip() or "text"
            if not field_id:
                break
            if field_type != "text":
                raise ValueError(
                    f"ChMeetings field {expected_name!r} must be a one-line Text field; "
                    f"found field_type={field_type!r}."
                )
            self._badge_url_field = (field_id, field_type)
            logger.info(
                f"Discovered ChMeetings badge URL field '{expected_name}' "
                f"field_id={field_id}."
            )
            return self._badge_url_field

        raise ValueError(
            f"Create a one-line Text custom profile field named {expected_name!r} "
            "or set SF_FIELD_IDS['BADGE_URL'] after running the ChMeetings field inspector."
        )

    def _write_badge_url_to_chmeetings(self, participant: Dict[str, Any], badge_url: str) -> None:
        """Write the hosted badge URL to the person's ChMeetings profile."""
        chm_id = str(participant.get("chmeetings_id") or "").strip()
        badge_url = str(badge_url or "").strip()
        if not chm_id:
            raise ValueError("Cannot write badge URL without chmeetings_id.")
        if not badge_url.startswith(("http://", "https://")):
            raise ValueError("Badge URL write-back requires an http(s) URL.")

        person = self.chm.get_person(chm_id)
        if not person:
            raise ValueError(f"ChMeetings person {chm_id} was not found.")

        field_id, field_type = self._badge_url_field_definition()
        additional_fields = self._merged_badge_url_fields(
            person.get("additional_fields") or [],
            field_id=field_id,
            field_type=field_type,
            badge_url=badge_url,
        )
        first_name = str(person.get("first_name") or participant.get("first_name") or "").strip()
        last_name = str(person.get("last_name") or participant.get("last_name") or "").strip()
        if not first_name or not last_name:
            raise ValueError(f"Cannot update ChMeetings person {chm_id} without first and last name.")

        ok = self.chm.update_person(
            chm_id,
            first_name,
            last_name,
            additional_fields,
            extra_person_data=person,
        )
        if not ok:
            raise ValueError(f"ChMeetings badge URL update failed for person {chm_id}.")
        logger.info(f"Badge URL written to ChMeetings chm_id={chm_id}")

    @staticmethod
    def _merged_badge_url_fields(
        current_fields: Any,
        *,
        field_id: int,
        field_type: str,
        badge_url: str,
    ) -> List[Dict[str, Any]]:
        """Preserve existing custom fields while replacing/adding badge URL."""
        badge_field = {
            "field_id": field_id,
            "field_type": field_type,
            "value": badge_url,
        }
        if not isinstance(current_fields, list):
            return [badge_field]

        merged: List[Dict[str, Any]] = []
        replaced = False
        for field in current_fields:
            if not isinstance(field, dict):
                continue
            copied = dict(field)
            if int(copied.get("field_id") or copied.get("id") or 0) == field_id:
                copied.update(badge_field)
                replaced = True
            merged.append(copied)
        if not replaced:
            merged.append(badge_field)
        return merged

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
        """Try ChMeetings, then WordPress, then use the initials fallback."""
        chm_id = str(participant.get("chmeetings_id") or "")
        candidates: List[tuple[str, str]] = []

        if chm_id:
            person = self.chm.get_person(chm_id)
            if person:
                chm_photo = person.get("photo")
                if chm_photo and str(chm_photo).startswith(("http://", "https://")):
                    candidates.append(("chm_photo", str(chm_photo)))
                # Backfill names from ChMeetings when WordPress didn't carry them.
                for key in ("first_name", "last_name"):
                    if not participant.get(key) and person.get(key):
                        participant[key] = person[key]
                participant["consent_status"] = self._person_has_consent(person)
                age_at_event = self._age_at_event(person.get("birth_date"))
                participant["age_at_event"] = age_at_event
                participant["minor_status"] = (
                    age_at_event is not None and age_at_event < 18
                )

        wp_url = participant.get("photo_url")
        if wp_url and str(wp_url).startswith(("http://", "https://")):
            wp_url_text = str(wp_url)
            if all(url != wp_url_text for _, url in candidates):
                candidates.append(("wp_fallback", wp_url_text))

        for source, photo_url in candidates:
            try:
                response = requests.get(photo_url, timeout=(5, 20))
                response.raise_for_status()
                photo_bytes = response.content
                with Image.open(io.BytesIO(photo_bytes)) as image:
                    image.verify()
                logger.info(
                    f"Photo source={source} status=downloaded chm_id={chm_id}"
                )
                return photo_bytes
            except (requests.RequestException, OSError, ValueError) as exc:
                logger.warning(
                    f"Photo source={source} status=failed chm_id={chm_id} "
                    f"error_type={type(exc).__name__}"
                )

        logger.info(
            f"Photo source=initials status=selected chm_id={chm_id}"
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

    @staticmethod
    def _person_has_consent(person: Dict[str, Any]) -> bool:
        consent_label = CHECK_BOXES["2-CONSENT"]
        consent_option_ids = {
            option_id
            for option_id, label in SF_CHECKLIST_OPTIONS.items()
            if label == consent_label
        }
        fields = person.get("additional_fields") or []
        if isinstance(fields, dict):
            checklist = fields.get(CHM_FIELDS["COMPLETION_CHECKLIST"], "")
            selected_ids = fields.get("selected_option_ids") or []
            return (
                consent_label in str(checklist)
                or any(option_id in consent_option_ids for option_id in selected_ids)
            )
        else:
            for field in fields:
                if not isinstance(field, dict):
                    continue
                if field.get("field_name") == CHM_FIELDS["COMPLETION_CHECKLIST"]:
                    checklist = field.get("value") or ""
                    selected_ids = field.get("selected_option_ids") or []
                    return (
                        consent_label in str(checklist)
                        or any(option_id in consent_option_ids for option_id in selected_ids)
                    )
        return False

    @staticmethod
    def _age_at_event(birthdate_str: Optional[str]) -> Optional[int]:
        """Return age on SPORTS_FEST_DATE using the church-export calculation."""
        text = str(birthdate_str or "").strip().split("T", 1)[0].split(" ", 1)[0]
        if not text:
            return None
        try:
            birth_date = datetime.strptime(text, "%Y-%m-%d").date()
            event_date = datetime.strptime(Config.SPORTS_FEST_DATE, "%Y-%m-%d").date()
        except ValueError:
            logger.warning(
                f"Invalid birthdate format encountered: '{birthdate_str}' for badge age calculation."
            )
            return None
        return event_date.year - birth_date.year - (
            (event_date.month, event_date.day) < (birth_date.month, birth_date.day)
        )

"""Warning-only duplicate tripwire for printed and exported outputs.

#312, docs/CANONICAL_IDENTITY_RFC.md §4.5. Scoresheets, badges and the
church-team export each print whatever identities they are handed. When two
of those rows look like one human under two ChMeetings IDs, this module says
so in the log — a smoke alarm for duplicates that have no alias entry yet.

It never filters, reorders or edits a row: paper must match data. The cure
is an operator-confirmed alias (``find-duplicates`` then ``apply-aliases``),
never anything done here.

"Looks like one human" is decided by the shared scoring, not a rule of this
module's own: two rows in the same group whose match basis, per
``identity_scoring.score_identity_match`` with ``duplicate_name_key`` names,
contains both ``name`` and ``birthdate``. That is the lowest-scoring pair
``find-duplicates`` calls strong, so every warning here is a pair that
command would propose. Twins — same birthdate, different names — do not
match.
"""

from collections import defaultdict
from itertools import combinations
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from loguru import logger

from sync.duplicate_finder import duplicate_name_key
from sync.identity_scoring import identity_from_wp_participant, safe_str, score_identity_match
from sync.person_aliases import AliasMap, load_person_aliases_for_reader, resolve_chm_id

# (group, lower ChMeetings ID, higher ChMeetings ID)
DuplicatePair = Tuple[str, str, str]

_SAME_PERSON_BASIS = frozenset({"name", "birthdate"})


def tripwire_person(
    chm_id: Any, first_name: Any, last_name: Any, birthdate: Any, group: Any
) -> Dict[str, Any]:
    """One row as the tripwire sees it. ``group`` is the team or church it is printed under."""
    return {
        "chm_id": chm_id,
        "first_name": first_name,
        "last_name": last_name,
        "birthdate": birthdate,
        "group": group,
    }


def _clean_id(value: Any) -> str:
    # A workbook cell read back as a number: 3633885.0 is the ID 3633885.
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return safe_str(value)


def _id_order(chm_id: str) -> Tuple[int, str]:
    return (int(chm_id), chm_id) if chm_id.isdigit() else (-1, chm_id)


def find_likely_duplicates(people: Iterable[Mapping[str, Any]]) -> List[DuplicatePair]:
    """Pairs in one group with the same name key and birthdate, under two ChMeetings IDs.

    Pure: reads the rows it is given and returns ID pairs. Rows without a
    ChMeetings ID are ignored — an alias entry could not name them.
    """
    by_group_and_name: Dict[Tuple[str, str], Dict[str, Dict[str, str]]] = defaultdict(dict)
    for person in people:
        chm_id = _clean_id(person.get("chm_id"))
        if not chm_id:
            continue
        identity = identity_from_wp_participant(
            {
                "chmeetings_id": chm_id,
                "first_name": person.get("first_name"),
                "last_name": person.get("last_name"),
                "birthdate": person.get("birthdate"),
            },
            name_key=duplicate_name_key,
        )
        if identity["name_norm"]:
            # The same ID listed twice in a group is one record, not a duplicate identity.
            group = safe_str(person.get("group"))
            by_group_and_name[(group, identity["name_norm"])].setdefault(chm_id, identity)

    pairs: List[DuplicatePair] = []
    for (group, _), identities in by_group_and_name.items():
        for left_id, right_id in combinations(sorted(identities, key=_id_order), 2):
            _, _, basis = score_identity_match(identities[left_id], identities[right_id])
            if _SAME_PERSON_BASIS <= set(basis):
                pairs.append((group, left_id, right_id))
    return sorted(pairs, key=lambda pair: (pair[0], _id_order(pair[1]), _id_order(pair[2])))


def warn_on_likely_duplicates(
    people: Iterable[Mapping[str, Any]],
    *,
    context: str,
    aliases: Optional[AliasMap] = None,
) -> List[DuplicatePair]:
    """Log a WARNING for each likely duplicate pair; return the pairs warned about.

    ``context`` names the output being produced, for the log line. Pairs the
    alias map already resolves to one person are skipped: the operator has
    decided those. The map is read only when there is a pair to check.

    This is a tripwire on the way to a printer. It must not be the reason a
    scoresheet or badge run fails, so any error in the check itself is logged
    and swallowed, and the caller's rows are never touched.
    """
    try:
        people = list(people)
        pairs = find_likely_duplicates(people)
        if not pairs:
            if people and not any(safe_str(person.get("birthdate")) for person in people):
                logger.info(
                    f"[VAY SM] Duplicate check skipped for {context}: none of the "
                    f"{len(people)} row(s) carries a birthdate."
                )
            return []

        if aliases is None:
            aliases = load_person_aliases_for_reader(f"the duplicate check for {context}")

        warned: List[DuplicatePair] = []
        for group, left_id, right_id in pairs:
            if resolve_chm_id(left_id, aliases) == resolve_chm_id(right_id, aliases):
                continue
            where = f"{context}, {group}" if group else context
            logger.warning(
                f"[VAY SM] Possible duplicate person in {where}: ChMeetings IDs {left_id} "
                f"and {right_id} have the same name and birthdate. Both rows were kept; "
                "the output was not changed. Run 'python main.py find-duplicates' to "
                "review the pair."
            )
            warned.append((group, left_id, right_id))
        return warned
    except Exception as exc:  # noqa: BLE001 - see docstring: never fail the print run
        logger.warning(
            f"[VAY SM] Duplicate check for {context} could not run ({exc!r}); "
            "the output was not affected."
        )
        return []

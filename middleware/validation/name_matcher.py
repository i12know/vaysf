import re
import unicodedata


_PAREN_CONTENT_RE = re.compile(r"\([^)]*\)")
_NON_WORD_RE = re.compile(r"[^\w\s]+", re.UNICODE)


def normalized_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(name or "").strip())
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(without_marks.casefold().split())


def token_matches(query_token: str, candidate_token: str) -> bool:
    if query_token == candidate_token:
        return True
    return len(query_token) >= 2 and candidate_token.startswith(query_token)


def _clean_tokens(name_key: str, *, keep_parenthetical: bool) -> list[str]:
    text = normalized_name(name_key)
    if not keep_parenthetical:
        text = _PAREN_CONTENT_RE.sub(" ", text)
    text = _NON_WORD_RE.sub(" ", text)
    return [token for token in text.split() if token]


def _token_prefix_match(query_tokens: list[str], candidate_tokens: list[str]) -> bool:
    if not query_tokens or not candidate_tokens:
        return False

    return all(
        any(token_matches(query_token, candidate_token) for candidate_token in candidate_tokens)
        for query_token in query_tokens
    )


def _initial_tolerant_match(query_tokens: list[str], candidate_tokens: list[str]) -> bool:
    if not query_tokens or not candidate_tokens:
        return False

    saw_initial = False
    saw_non_initial = False
    for query_token in query_tokens:
        matched = False
        for candidate_token in candidate_tokens:
            if query_token == candidate_token:
                matched = True
                if len(query_token) >= 2:
                    saw_non_initial = True
                break
            if len(query_token) == 1 and candidate_token.startswith(query_token):
                matched = True
                saw_initial = True
                break
            if len(query_token) >= 2 and candidate_token.startswith(query_token):
                matched = True
                saw_non_initial = True
                break
        if not matched:
            return False

    return saw_initial and saw_non_initial


def resolvable_name_match(query_name_key: str, candidate_name_key: str) -> bool:
    query_base_tokens = _clean_tokens(query_name_key, keep_parenthetical=False)
    candidate_base_tokens = _clean_tokens(candidate_name_key, keep_parenthetical=False)
    if not query_base_tokens or not candidate_base_tokens:
        return False

    if query_base_tokens == candidate_base_tokens:
        return True

    if len(query_base_tokens) > 1 and sorted(query_base_tokens) == sorted(candidate_base_tokens):
        return True

    if "".join(query_base_tokens) == "".join(candidate_base_tokens):
        return True

    return _initial_tolerant_match(query_base_tokens, candidate_base_tokens)


def likely_name_match(query_name_key: str, candidate_name_key: str) -> bool:
    query_all_tokens = _clean_tokens(query_name_key, keep_parenthetical=True)
    candidate_all_tokens = _clean_tokens(candidate_name_key, keep_parenthetical=True)
    if _token_prefix_match(query_all_tokens, candidate_all_tokens):
        return True

    query_base_tokens = _clean_tokens(query_name_key, keep_parenthetical=False)
    candidate_base_tokens = _clean_tokens(candidate_name_key, keep_parenthetical=False)
    if not query_base_tokens or not candidate_base_tokens:
        return False

    return resolvable_name_match(query_name_key, candidate_name_key)

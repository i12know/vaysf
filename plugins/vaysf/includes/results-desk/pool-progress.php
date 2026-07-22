<?php
/**
 * File: includes/results-desk/pool-progress.php
 * Description: Pool progress, standings, ranking, and advancement review helpers.
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

/**
 * Add or update one team in a provisional pool ranking map.
 *
 * @param array<string,array<string,mixed>> $teams Ranking map, by team key
 * @param string $key Team key
 * @param string $label Team label
 * @return void
 */
function vaysf_results_desk_ensure_pool_team(&$teams, $key, $label = '') {
    $key = trim((string) $key);
    if ($key === '') {
        return;
    }

    if (empty($teams[$key])) {
        $teams[$key] = array(
            'team_key' => $key,
            'label' => trim((string) $label) !== '' ? trim((string) $label) : $key,
            'played' => 0,
            'wins' => 0,
            'losses' => 0,
            'ties' => 0,
            'for' => 0,
            'against' => 0,
            'diff' => 0,
            'notes' => array(),
        );
    } elseif (trim((string) $label) !== '') {
        $teams[$key]['label'] = trim((string) $label);
    }
}

/**
 * Return schedule team slots present on a row.
 *
 * @param array<string,mixed> $row Schedule/result row
 * @return array<int,array{slot:string,key:string,label:string}>
 */
function vaysf_results_desk_pool_team_slots($row) {
    $slots = array();
    foreach (array('a', 'b', 'c') as $slot) {
        $key = trim((string) ($row["team_{$slot}_key"] ?? ''));
        if ($key === '') {
            continue;
        }

        $label = trim((string) ($row["team_{$slot}_label"] ?? ''));
        $slots[] = array(
            'slot' => $slot,
            'key' => $key,
            'label' => $label !== '' ? $label : $key,
        );
    }

    return $slots;
}

/**
 * Check whether an event uses Bible Challenge advancement rules.
 *
 * @param string $event Schedule event name
 * @return bool
 */
function vaysf_results_desk_is_bible_challenge_event($event) {
    return strcasecmp(trim((string) $event), 'Bible Challenge - Mixed Team') === 0;
}

/**
 * Check whether an event supports the operator-driven two-team QF assignment
 * helper on Results Desk.
 *
 * @param string $event Schedule event name
 * @return bool
 */
function vaysf_results_desk_is_team_qf_assignment_event($event) {
    $event = trim((string) $event);
    return stripos($event, 'Basketball') !== false || stripos($event, 'Volleyball') !== false;
}

/**
 * Return the ranking-rule note for a pool/prelim event.
 *
 * @param string $event Schedule event name
 * @return string
 */
function vaysf_results_desk_pool_ranking_rule_note($event) {
    $event = trim((string) $event);
    if (vaysf_results_desk_is_bible_challenge_event($event)) {
        return __('Rule: Bible Challenge ranks by accumulated preliminary score. The top 9 advance; a tie at the 9th/10th cutoff requires coordinator review.', 'vaysf');
    }

    if (
        stripos($event, 'Basketball') !== false
        || stripos($event, 'Volleyball') !== false
        || stripos($event, 'Soccer') !== false
    ) {
        return __('Rule: Team-sport pools rank by wins, then fewer losses, then point differential, then head-to-head when teams remain fully tied. Unresolved cycles require coordinator review.', 'vaysf');
    }

    return '';
}

/**
 * Check whether a schedule row includes the selected church.
 *
 * @param array<string,mixed> $row Schedule/result row
 * @param string $church Uppercase church code filter
 * @return bool
 */
function vaysf_results_desk_pool_row_matches_church($row, $church) {
    $church = strtoupper(trim((string) $church));
    if ($church === '') {
        return true;
    }

    foreach (array('a', 'b', 'c') as $slot) {
        foreach (array("team_{$slot}_church_code", "team_{$slot}_key", "team_{$slot}_label") as $field) {
            if (!empty($row[$field]) && vaysf_extract_church_code_from_team_value($row[$field]) === $church) {
                return true;
            }
        }
    }

    return false;
}

/**
 * Add a note to a ranking row without duplication.
 *
 * @param array<string,mixed> $team Ranking row
 * @param string $note Note text
 * @return void
 */
function vaysf_results_desk_add_pool_team_note(&$team, $note) {
    $note = trim((string) $note);
    if ($note === '') {
        return;
    }

    if (!in_array($note, $team['notes'], true)) {
        $team['notes'][] = $note;
    }
}

/**
 * Build score totals by team key for a result payload.
 *
 * @param array<string,mixed> $payload Decoded score_json
 * @param array<int,array{slot:string,key:string,label:string}> $slots Schedule slots
 * @return array<string,int>
 */
function vaysf_results_desk_pool_score_by_team($payload, $slots) {
    $scores = array();
    foreach ($slots as $slot) {
        $field = 'team_' . $slot['slot'] . '_score';
        if (array_key_exists($field, $payload) && is_numeric($payload[$field])) {
            $scores[$slot['key']] = (int) $payload[$field];
        }
    }

    return $scores;
}

/**
 * Apply one scored game to a provisional pool ranking map.
 *
 * @param array<string,array<string,mixed>> $teams Ranking map, by team key
 * @param array<string,string> $flags Pool-level flags
 * @param array<string,mixed> $row Schedule/result row
 * @param array<string,string> $head_to_head Pair-key ("keyA|keyB", sorted) =>
 *        winner team key or 'tie', accumulated for genuine 2-team games only
 *        (Issue #207 â€” feeds head-to-head tiebreak resolution)
 * @return void
 */
function vaysf_results_desk_apply_pool_result(&$teams, &$flags, $row, &$head_to_head = array()) {
    $is_bible_challenge = vaysf_results_desk_is_bible_challenge_event($row['event'] ?? '');
    $slots = vaysf_results_desk_pool_team_slots($row);
    foreach ($slots as $slot) {
        vaysf_results_desk_ensure_pool_team($teams, $slot['key'], $slot['label']);
    }

    $score_json = trim((string) ($row['score_json'] ?? ''));
    if ($score_json === '') {
        $flags['missing_results'] = __('Missing score payloads remain.', 'vaysf');
        return;
    }

    $payload = vaysf_results_desk_decode_json_array($score_json);
    if (!$payload) {
        $flags['invalid_payload'] = __('At least one score payload could not be read.', 'vaysf');
        return;
    }

    $scores = vaysf_results_desk_pool_score_by_team($payload, $slots);
    if (!$scores) {
        $flags['unsupported_payload'] = __('At least one score payload has no ranking-friendly score fields.', 'vaysf');
        return;
    }

    $winner_keys = vaysf_results_desk_decode_json_array($row['winner_keys_json'] ?? '');
    $winner_keys = array_values(array_filter(array_map('strval', $winner_keys)));
    $winner_lookup = array_fill_keys($winner_keys, true);
    $is_tie = !empty($payload['is_tie']) || count($winner_keys) > 1 || !empty($payload['split_match']);

    if (!empty($payload['split_match'])) {
        $flags['split_match'] = __('At least one volleyball match was recorded as a split/tie.', 'vaysf');
    }
    if ($is_tie && !$is_bible_challenge) {
        $flags['tie'] = __('At least one result is tied or has multiple winners; review tiebreak rules manually.', 'vaysf');
    }

    foreach ($slots as $slot) {
        $key = $slot['key'];
        if (!isset($scores[$key])) {
            vaysf_results_desk_add_pool_team_note($teams[$key], __('Score missing', 'vaysf'));
            continue;
        }

        $teams[$key]['played']++;
        $teams[$key]['for'] += (int) $scores[$key];
        foreach ($scores as $opponent_key => $opponent_score) {
            if ($opponent_key !== $key) {
                $teams[$key]['against'] += (int) $opponent_score;
            }
        }
        $teams[$key]['diff'] = $teams[$key]['for'] - $teams[$key]['against'];

        if (!$is_bible_challenge) {
            if ($is_tie) {
                if (!$winner_keys || isset($winner_lookup[$key])) {
                    $teams[$key]['ties']++;
                } else {
                    $teams[$key]['losses']++;
                }
            } elseif (isset($winner_lookup[$key])) {
                $teams[$key]['wins']++;
            } else {
                $teams[$key]['losses']++;
            }
        }
    }

    // Head-to-head is only meaningful for a genuine 2-team game with both
    // scores present â€” a 3-team game (e.g. Bible Challenge) has no single
    // well-defined opponent, so it is intentionally excluded rather than
    // approximated (Issue #207).
    if (!$is_bible_challenge && count($slots) === 2) {
        $slot_a = $slots[0]['key'];
        $slot_b = $slots[1]['key'];
        if (isset($scores[$slot_a]) && isset($scores[$slot_b])) {
            $pair = array($slot_a, $slot_b);
            sort($pair);
            $pair_key = implode('|', $pair);
            if ($is_tie) {
                $head_to_head[$pair_key] = 'tie';
            } elseif (isset($winner_lookup[$slot_a])) {
                $head_to_head[$pair_key] = $slot_a;
            } elseif (isset($winner_lookup[$slot_b])) {
                $head_to_head[$pair_key] = $slot_b;
            }
        }
    }
}

/**
 * Sort Bible Challenge provisional rankings.
 *
 * Bible Challenge advances the top 9 teams by the cumulative score from all
 * preliminary rows. Win/loss/head-to-head signals are intentionally ignored.
 *
 * @param array<string,array<string,mixed>> $teams Ranking map
 * @return array<int,array<string,mixed>>
 */
function vaysf_results_desk_sort_bible_challenge_rankings($teams) {
    $rankings = array_values($teams);
    usort($rankings, function ($a, $b) {
        $a_for = isset($a['for']) ? (int) $a['for'] : 0;
        $b_for = isset($b['for']) ? (int) $b['for'] : 0;
        if ($a_for !== $b_for) {
            return $a_for > $b_for ? -1 : 1;
        }

        return strcasecmp((string) ($a['label'] ?? ''), (string) ($b['label'] ?? ''));
    });

    $cutoff_score = null;
    if (count($rankings) > 9 && isset($rankings[8]['for'])) {
        $cutoff_score = (int) $rankings[8]['for'];
        if ((int) ($rankings[9]['for'] ?? PHP_INT_MIN) !== $cutoff_score) {
            $cutoff_score = null;
        }
    }

    foreach ($rankings as $index => $team) {
        $rankings[$index]['rank'] = $index + 1;
        $rankings[$index]['ranking_basis'] = 'total_score';
        $rankings[$index]['advances'] = $index < 9;
        $rankings[$index]['needs_manual_tiebreak'] = false;
        if ($cutoff_score !== null && (int) ($team['for'] ?? 0) === $cutoff_score) {
            $rankings[$index]['needs_manual_tiebreak'] = true;
            vaysf_results_desk_add_pool_team_note(
                $rankings[$index],
                __('Tied at the Bible Challenge top-9 advancement cutoff; decide manually.', 'vaysf')
            );
        }
    }

    return $rankings;
}

/**
 * Sort provisional pool rankings.
 *
 * Ranking order (VAY SM convention confirmed for the 2026 weekend 1â†’2
 * transition â€” Issue #207): win/loss record, then point differential, then
 * head-to-head result among teams still fully tied. A group that
 * head-to-head cannot fully order (e.g. a round-robin cycle where every
 * team in the group beat exactly one other team in it) is flagged
 * needs_manual_tiebreak rather than resolved by alphabetical guesswork â€”
 * wrong output here means the wrong team advances. Alphabetical order is
 * used only as a stable display order within a flagged group, never as if
 * it had settled the ranking.
 *
 * @param array<string,array<string,mixed>> $teams Ranking map
 * @param array<string,string> $head_to_head Pair-key ("keyA|keyB", sorted)
 *        => winner team key or 'tie', from vaysf_results_desk_apply_pool_result()
 * @param string $event Schedule event name
 * @return array<int,array<string,mixed>>
 */
function vaysf_results_desk_sort_pool_rankings($teams, $head_to_head = array(), $event = '') {
    if (vaysf_results_desk_is_bible_challenge_event($event)) {
        return vaysf_results_desk_sort_bible_challenge_rankings($teams);
    }

    $rankings = array_values($teams);
    usort($rankings, function ($a, $b) {
        $a_wins = isset($a['wins']) ? (int) $a['wins'] : 0;
        $b_wins = isset($b['wins']) ? (int) $b['wins'] : 0;
        if ($a_wins !== $b_wins) {
            return $a_wins > $b_wins ? -1 : 1;
        }
        $a_losses = isset($a['losses']) ? (int) $a['losses'] : 0;
        $b_losses = isset($b['losses']) ? (int) $b['losses'] : 0;
        if ($a_losses !== $b_losses) {
            return $a_losses < $b_losses ? -1 : 1;
        }
        $a_diff = isset($a['diff']) ? (int) $a['diff'] : 0;
        $b_diff = isset($b['diff']) ? (int) $b['diff'] : 0;
        if ($a_diff !== $b_diff) {
            return $a_diff > $b_diff ? -1 : 1;
        }

        return strcasecmp((string) ($a['label'] ?? ''), (string) ($b['label'] ?? ''));
    });

    // Group teams still fully tied on wins/losses/diff after the primary
    // sort and try to break each group using head-to-head results among
    // just that group.
    $i = 0;
    $n = count($rankings);
    while ($i < $n) {
        $j = $i;
        while (
            $j + 1 < $n
            && (int) $rankings[$j + 1]['wins'] === (int) $rankings[$i]['wins']
            && (int) $rankings[$j + 1]['losses'] === (int) $rankings[$i]['losses']
            && (int) $rankings[$j + 1]['diff'] === (int) $rankings[$i]['diff']
        ) {
            $j++;
        }

        if ($j > $i) {
            $group_keys = array_map(
                function ($t) {
                    return $t['team_key'];
                },
                array_slice($rankings, $i, $j - $i + 1)
            );
            $ordered = vaysf_resolve_pool_head_to_head_group($group_keys, $head_to_head);
            if ($ordered === null) {
                foreach (array_slice($rankings, $i, $j - $i + 1) as $offset => $team) {
                    $rankings[$i + $offset]['needs_manual_tiebreak'] = true;
                    vaysf_results_desk_add_pool_team_note(
                        $rankings[$i + $offset],
                        __('Tied â€” head-to-head could not resolve order; decide manually.', 'vaysf')
                    );
                }
            } else {
                $by_key = array();
                foreach (array_slice($rankings, $i, $j - $i + 1) as $team) {
                    $by_key[$team['team_key']] = $team;
                }
                foreach ($ordered as $offset => $team_key) {
                    $rankings[$i + $offset] = $by_key[$team_key];
                }
            }
        }

        $i = $j + 1;
    }

    foreach ($rankings as $index => $team) {
        $rankings[$index]['rank'] = $index + 1;
        if (!isset($rankings[$index]['needs_manual_tiebreak'])) {
            $rankings[$index]['needs_manual_tiebreak'] = false;
        }
    }

    return $rankings;
}

/**
 * Order a group of fully-tied teams using head-to-head results among just
 * that group. Returns null (unresolved) rather than a partial/best-guess
 * order when the group's results do not produce a strict ranking â€” e.g. a
 * round-robin cycle where every team beat exactly one other team in the
 * group. Callers must treat null as "a human must decide," not as an error.
 *
 * @param array<int,string> $group_keys Team keys in the tied group
 * @param array<string,string> $head_to_head Pair-key => winner key or 'tie'
 * @return array<int,string>|null Ordered team keys, or null if unresolved
 */
function vaysf_resolve_pool_head_to_head_group($group_keys, $head_to_head) {
    $sub_wins = array_fill_keys($group_keys, 0);
    $decided_pairs = 0;
    $total_pairs = 0;

    foreach ($group_keys as $a_index => $team_a) {
        foreach ($group_keys as $b_index => $team_b) {
            if ($b_index <= $a_index) {
                continue;
            }
            $total_pairs++;
            $pair = array($team_a, $team_b);
            sort($pair);
            $pair_key = implode('|', $pair);
            if (!isset($head_to_head[$pair_key]) || $head_to_head[$pair_key] === 'tie') {
                continue;
            }
            $sub_wins[$head_to_head[$pair_key]]++;
            $decided_pairs++;
        }
    }

    // Require every pair in the group to have actually played and produced
    // a clear winner before trusting a sub-ranking from it.
    if ($decided_pairs < $total_pairs) {
        return null;
    }

    $ordered = $group_keys;
    usort($ordered, function ($a, $b) use ($sub_wins) {
        return $sub_wins[$b] <=> $sub_wins[$a];
    });

    // Confirm the head-to-head sub-standings themselves produced a strict
    // order (no remaining tie within the group after sub-wins).
    $sub_win_counts = array_map(
        function ($key) use ($sub_wins) {
            return $sub_wins[$key];
        },
        $ordered
    );
    if (count(array_unique($sub_win_counts)) !== count($sub_win_counts)) {
        return null;
    }

    return $ordered;
}

/**
 * Sentinel pool_id under which the event-wide (cross-pool) QF seeding
 * confirmation is stored in `sf_pool_advancement`, alongside real per-pool
 * ids like "P1" (Issue #329). Reuses that table's whole read/staleness
 * machinery (vaysf_get_pool_advancement(), vaysf_pool_advancement_is_stale())
 * rather than introducing a parallel table for the confirmed snapshot.
 *
 * @return string
 */
function vaysf_results_desk_event_seeding_pool_id() {
    return 'ALL';
}

/**
 * Fetch pool progress and provisional rankings for Results Desk review.
 *
 * @param array<string,mixed> $filters Sanitized filters
 * @param int $limit Maximum pool groups
 * @return array<int,array<string,mixed>>
 */
function vaysf_get_results_desk_pool_progress_rows($filters = array(), $limit = 50) {
    global $wpdb;

    $schedule_version = vaysf_get_current_published_schedule_version();
    if ($schedule_version === null) {
        return array();
    }

    $filters = vaysf_sanitize_results_desk_filters($filters);
    $limit = max(1, min(absint($limit), 200));
    $table_schedules = vaysf_get_table_name('schedules');
    $table_results = vaysf_get_table_name('results');

    $where = array(
        's.schedule_version = %d',
        's.published_at IS NOT NULL',
        "COALESCE(s.game_status, '') <> 'cancelled'",
        "LOWER(COALESCE(s.stage, '')) IN ('pool', 'prelim', 'preliminary')",
    );
    $args = array($schedule_version);
    vaysf_results_desk_add_event_filter($where, $args, $filters['event']);

    $sql = "SELECT s.*, r.result_id, r.score_json, r.winner_keys_json, r.public_status,
            r.current_revision, r.updated_at AS result_updated_at
        FROM $table_schedules s
        LEFT JOIN $table_results r ON r.schedule_id = s.schedule_id
        WHERE " . implode(' AND ', $where) . "
        ORDER BY s.event, s.stage, s.pool_id, s.scheduled_time IS NULL, s.scheduled_time, s.game_key";

    $rows = $wpdb->get_results($wpdb->prepare($sql, $args), ARRAY_A);
    if (!is_array($rows)) {
        return array();
    }

    $pools = array();
    $pool_teams = array();
    $pool_head_to_head = array();
    foreach ($rows as $row) {
        $pool_id = trim((string) ($row['pool_id'] ?? ''));
        $pool_display_id = $pool_id !== '' ? $pool_id : 'P1';
        $key = implode('|', array(
            (string) ($row['event'] ?? ''),
            (string) ($row['stage'] ?? ''),
            $pool_display_id,
        ));

        if (empty($pools[$key])) {
            $pools[$key] = array(
                'event' => (string) ($row['event'] ?? ''),
                'stage' => (string) ($row['stage'] ?? ''),
                'pool_id' => $pool_display_id,
                'schedule_version' => absint($schedule_version),
                'synthetic_pool' => $pool_id === '',
                'game_count' => 0,
                'reported_count' => 0,
                'missing_count' => 0,
                'last_updated_at' => '',
                'rankings' => array(),
                'flags' => array(),
                'matches_church_filter' => false,
            );
            $pool_teams[$key] = array();
            $pool_head_to_head[$key] = array();
        }

        $pools[$key]['game_count']++;
        $has_score = trim((string) ($row['score_json'] ?? '')) !== '';
        if ($has_score) {
            $pools[$key]['reported_count']++;
        } else {
            $pools[$key]['missing_count']++;
        }

        $updated_at = trim((string) ($row['result_updated_at'] ?? '')) ?: trim((string) ($row['updated_at'] ?? ''));
        if ($updated_at !== '' && $updated_at > $pools[$key]['last_updated_at']) {
            $pools[$key]['last_updated_at'] = $updated_at;
        }
        if (vaysf_results_desk_pool_row_matches_church($row, $filters['church'])) {
            $pools[$key]['matches_church_filter'] = true;
        }

        vaysf_results_desk_apply_pool_result($pool_teams[$key], $pools[$key]['flags'], $row, $pool_head_to_head[$key]);
    }

    foreach ($pools as $key => $pool) {
        if ($filters['church'] !== '' && empty($pool['matches_church_filter'])) {
            unset($pools[$key], $pool_teams[$key], $pool_head_to_head[$key]);
            continue;
        }

        $pools[$key]['complete'] = ((int) $pool['game_count'] > 0 && (int) $pool['missing_count'] === 0);
        $is_bible_challenge = vaysf_results_desk_is_bible_challenge_event($pool['event'] ?? '');
        $pools[$key]['rankings'] = vaysf_results_desk_sort_pool_rankings($pool_teams[$key] ?? array(), $pool_head_to_head[$key] ?? array(), $pool['event'] ?? '');
        $pools[$key]['needs_manual_tiebreak'] = false;
        foreach ($pools[$key]['rankings'] as $ranked_team) {
            if (!empty($ranked_team['needs_manual_tiebreak'])) {
                $pools[$key]['needs_manual_tiebreak'] = true;
                break;
            }
        }
        if ($pools[$key]['needs_manual_tiebreak']) {
            $pools[$key]['flags']['unresolved_tiebreak'] = $is_bible_challenge
                ? __('A tie exists at the Bible Challenge top-9 cumulative-score cutoff; decide the advancing team manually before confirming advancement.', 'vaysf')
                : __('A tie could not be resolved by head-to-head results; decide the order manually before confirming advancement.', 'vaysf');
        }
        if (!$pools[$key]['complete']) {
            $pools[$key]['flags']['incomplete'] = __('Pool is still incomplete; ranking is provisional.', 'vaysf');
        }
    }

    $pool_rows = array_values($pools);
    usort($pool_rows, function ($a, $b) {
        if (!empty($a['complete']) !== !empty($b['complete'])) {
            return !empty($a['complete']) ? -1 : 1;
        }
        $a_progress = (int) ($a['reported_count'] ?? 0) / max(1, (int) ($a['game_count'] ?? 1));
        $b_progress = (int) ($b['reported_count'] ?? 0) / max(1, (int) ($b['game_count'] ?? 1));
        if ($a_progress !== $b_progress) {
            return $a_progress > $b_progress ? -1 : 1;
        }
        return strcmp(
            implode('|', array($a['event'] ?? '', $a['stage'] ?? '', $a['pool_id'] ?? '')),
            implode('|', array($b['event'] ?? '', $b['stage'] ?? '', $b['pool_id'] ?? ''))
        );
    });

    return array_slice($pool_rows, 0, $limit);
}

/**
 * Find one pool's progress/rankings row (Issue #207).
 *
 * Thin wrapper over vaysf_get_results_desk_pool_progress_rows() â€” reuses
 * the same rankings pipeline the Results Desk review section already
 * displays, rather than recomputing standings a second way.
 *
 * @param string $event
 * @param string $pool_id
 * @return array<string,mixed>|null
 */
function vaysf_get_pool_progress_row($event, $pool_id) {
    $event = sanitize_text_field($event);
    $pool_id = sanitize_text_field($pool_id);
    if ($event === '' || $pool_id === '') {
        return null;
    }

    $pools = vaysf_get_results_desk_pool_progress_rows(array('event' => $event, 'limit' => 200), 200);
    foreach ($pools as $pool) {
        if ((string) ($pool['event'] ?? '') === $event && (string) ($pool['pool_id'] ?? '') === $pool_id) {
            return $pool;
        }
    }

    return null;
}

/**
 * Fetch the current advancement confirmation for a pool, if any (Issue #207).
 *
 * @param string $event
 * @param string $pool_id
 * @return array<string,mixed>|null
 */
function vaysf_get_pool_advancement($event, $pool_id, $schedule_version = null) {
    global $wpdb;
    $event = sanitize_text_field($event);
    $pool_id = sanitize_text_field($pool_id);
    if ($schedule_version === null) {
        $schedule_version = vaysf_get_current_published_schedule_version();
    }
    $schedule_version = absint($schedule_version);
    if ($event === '' || $pool_id === '' || !$schedule_version) {
        return null;
    }

    $table = vaysf_get_table_name('pool_advancement');
    $row = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT * FROM $table WHERE schedule_version = %d AND event = %s AND pool_id = %s",
            $schedule_version,
            $event,
            $pool_id
        ),
        ARRAY_A
    );
    return is_array($row) ? $row : null;
}

/**
 * Normalize ranking rows before comparing a saved confirmation snapshot to
 * the current computed standings.
 *
 * @param array<int,array<string,mixed>> $rankings Ranking rows
 * @return array<int,array<string,mixed>>
 */
function vaysf_normalize_advancement_rankings_snapshot($rankings) {
    $normalized = array();
    foreach ((array) $rankings as $team) {
        if (!is_array($team)) {
            continue;
        }
        $normalized[] = array(
            'rank' => (int) ($team['rank'] ?? 0),
            'team_key' => (string) ($team['team_key'] ?? ''),
            'for' => (int) ($team['for'] ?? 0),
            'against' => (int) ($team['against'] ?? 0),
            'diff' => (int) ($team['diff'] ?? 0),
            'wins' => (int) ($team['wins'] ?? 0),
            'losses' => (int) ($team['losses'] ?? 0),
            'ties' => (int) ($team['ties'] ?? 0),
            'ranking_basis' => (string) ($team['ranking_basis'] ?? ''),
            'advances' => !empty($team['advances']),
            'needs_manual_tiebreak' => !empty($team['needs_manual_tiebreak']),
        );
    }

    return $normalized;
}

/**
 * Check whether a pool's confirmed advancement is stale â€” i.e. at least one
 * of the results it was confirmed against has since been corrected (its
 * current_revision has moved past what was recorded at confirmation time).
 *
 * @param string $event
 * @param string $pool_id
 * @return bool True when confirmed but now stale; false when not confirmed
 *              or still current
 */
function vaysf_pool_advancement_is_stale($event, $pool_id, $schedule_version = null, $current_rankings = null) {
    global $wpdb;

    $advancement = vaysf_get_pool_advancement($event, $pool_id, $schedule_version);
    if ($advancement === null) {
        return false;
    }

    $based_on = json_decode((string) $advancement['based_on_revisions_json'], true);
    if (!is_array($based_on) || empty($based_on)) {
        return false;
    }

    $table_results = vaysf_get_table_name('results');
    foreach ($based_on as $result_id => $revision_at_confirmation) {
        $current = $wpdb->get_var(
            $wpdb->prepare("SELECT current_revision FROM $table_results WHERE result_id = %d", absint($result_id))
        );
        if ($current === null) {
            // The contributing result row is gone entirely â€” treat as stale.
            return true;
        }
        if ((int) $current !== (int) $revision_at_confirmation) {
            return true;
        }
    }

    $saved_rankings = json_decode((string) ($advancement['standings_snapshot_json'] ?? ''), true);
    if (is_array($saved_rankings)) {
        if ($current_rankings === null) {
            // vaysf_get_pool_progress_row() only knows real per-pool ids
            // (e.g. "P1") â€” it has no concept of the cross-pool "ALL"
            // sentinel (Issue #329), so it always returns null for it,
            // which would make an "ALL" confirmation compare against an
            // empty current_rankings and read as stale immediately, even
            // moments after confirming with nothing changed.
            if ($pool_id === vaysf_results_desk_event_seeding_pool_id()) {
                $seeding = vaysf_results_desk_get_event_seeding_rankings($event, $schedule_version);
                $current_rankings = $seeding['rankings'] ?? array();
            } else {
                $pool = vaysf_get_pool_progress_row($event, $pool_id);
                $current_rankings = is_array($pool) ? ($pool['rankings'] ?? array()) : array();
            }
        }
        if (
            vaysf_normalize_advancement_rankings_snapshot($saved_rankings)
            !== vaysf_normalize_advancement_rankings_snapshot($current_rankings)
        ) {
            return true;
        }
    }

    return false;
}

/**
 * Confirm advancement for a pool (Issue #207): reads the same pool-progress
 * rankings the Results Desk review section displays
 * (vaysf_get_results_desk_pool_progress_rows()), refuses to confirm if the
 * pool is incomplete, requires a note when the pool still has an unresolved
 * tie, and upserts the
 * sf_pool_advancement record with a standings snapshot and the result
 * revisions it was based on (so a later correction can be detected as
 * staleness via vaysf_pool_advancement_is_stale()).
 *
 * Deliberately does NOT auto-populate Semifinal/Final schedule rows â€” which
 * pool's top teams feed which bracket slot is a tournament-structure
 * decision with no existing data model in this schema, and guessing it
 * under time pressure is a worse risk than the manual step it replaces.
 * This function replaces the error-prone arithmetic (who actually ranks
 * where); a human still places confirmed teams into next-round schedule
 * rows via the existing schedule editor, now reading numbers they can
 * trust instead of computing standings by hand.
 *
 * @param int $user_id WordPress user id confirming
 * @param string $event
 * @param string $pool_id
 * @param string $review_note Optional operator note; required for unresolved ties
 * @return array<int,array<string,mixed>>|WP_Error Standings snapshot on success
 */
function vaysf_confirm_pool_advancement($user_id, $event, $pool_id, $review_note = '') {
    global $wpdb;

    $user_id = absint($user_id);
    $event = sanitize_text_field($event);
    $pool_id = sanitize_text_field($pool_id);
    $review_note = sanitize_textarea_field($review_note);
    if (!$user_id || $event === '' || $pool_id === '') {
        return new WP_Error('vaysf_advancement_missing_context', __('Advancement confirmation is missing the user, event, or pool.', 'vaysf'));
    }

    $schedule_version = vaysf_get_current_published_schedule_version();
    if ($schedule_version === null) {
        return new WP_Error('vaysf_advancement_no_schedule', __('No published schedule is available for advancement confirmation.', 'vaysf'));
    }
    $schedule_version = absint($schedule_version);

    $pool = vaysf_get_pool_progress_row($event, $pool_id);
    if ($pool === null || empty($pool['rankings'])) {
        return new WP_Error('vaysf_advancement_no_results', __('No reported results found for this pool.', 'vaysf'));
    }
    if (empty($pool['complete'])) {
        return new WP_Error('vaysf_advancement_incomplete', __('Not every pool game has a reported result yet.', 'vaysf'));
    }
    if (!empty($pool['needs_manual_tiebreak']) && $review_note === '') {
        return new WP_Error('vaysf_advancement_tiebreak_note_required', __('This pool still has an unresolved tie. Add a review note before confirming it for the next-page tiebreak review.', 'vaysf'));
    }

    // Record which result rows (by revision number) this confirmation was
    // based on, so a later correction can be detected as staleness.
    $table_schedules = vaysf_get_table_name('schedules');
    $table_results = vaysf_get_table_name('results');
    $pool_where = !empty($pool['synthetic_pool'])
        ? "(s.pool_id IS NULL OR s.pool_id = '')"
        : 's.pool_id = %s';
    $result_args = array($schedule_version, $event);
    if (empty($pool['synthetic_pool'])) {
        $result_args[] = $pool_id;
    }
    $result_rows = $wpdb->get_results(
        $wpdb->prepare(
            "SELECT r.result_id, r.current_revision
                FROM $table_schedules s
                INNER JOIN $table_results r ON r.schedule_id = s.schedule_id
                WHERE s.schedule_version = %d
                  AND s.published_at IS NOT NULL
                  AND s.event = %s
                  AND $pool_where
                  AND LOWER(COALESCE(s.stage, '')) IN ('pool', 'prelim', 'preliminary')
                  AND COALESCE(s.game_status, '') <> 'cancelled'",
            $result_args
        ),
        ARRAY_A
    );
    $based_on_revisions = array();
    foreach ((array) $result_rows as $row) {
        $based_on_revisions[(int) $row['result_id']] = (int) $row['current_revision'];
    }

    $now = current_time('mysql');
    $snapshot_json = wp_json_encode($pool['rankings']);
    $revisions_json = wp_json_encode($based_on_revisions);
    if ($snapshot_json === false || $revisions_json === false) {
        return new WP_Error('vaysf_advancement_json_failed', __('Could not encode the standings snapshot.', 'vaysf'));
    }

    $table_advancement = vaysf_get_table_name('pool_advancement');
    $existing = vaysf_get_pool_advancement($event, $pool_id, $schedule_version);

    if ($existing) {
        $updated = $wpdb->update(
            $table_advancement,
            array(
                'confirmed_by_user_id' => $user_id,
                'schedule_version' => $schedule_version,
                'confirmed_at' => $now,
                'standings_snapshot_json' => $snapshot_json,
                'based_on_revisions_json' => $revisions_json,
                'review_note' => $review_note,
                'updated_at' => $now,
            ),
            array('advancement_id' => absint($existing['advancement_id'])),
            array('%d', '%d', '%s', '%s', '%s', '%s', '%s'),
            array('%d')
        );
        if ($updated === false) {
            return new WP_Error('vaysf_advancement_update_failed', __('Could not update the advancement confirmation.', 'vaysf'));
        }
    } else {
        $created = $wpdb->insert(
            $table_advancement,
            array(
                'event' => $event,
                'pool_id' => $pool_id,
                'schedule_version' => $schedule_version,
                'confirmed_by_user_id' => $user_id,
                'confirmed_at' => $now,
                'standings_snapshot_json' => $snapshot_json,
                'based_on_revisions_json' => $revisions_json,
                'review_note' => $review_note,
                'created_at' => $now,
                'updated_at' => $now,
            ),
            array('%s', '%s', '%d', '%d', '%s', '%s', '%s', '%s', '%s', '%s')
        );
        if ($created === false) {
            return new WP_Error('vaysf_advancement_create_failed', __('Could not create the advancement confirmation.', 'vaysf'));
        }
    }

    return $pool['rankings'];
}

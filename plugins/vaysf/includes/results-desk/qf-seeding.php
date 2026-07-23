<?php
/**
 * File: includes/results-desk/qf-seeding.php
 * Description: Basketball/Volleyball cross-pool QF seeding and playoff schedule writes.
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

/**
 * Classify an event's official 2026 QF seeding rule set (Issue #329). Returns
 * null for events with no cross-pool seeding rule (Bible Challenge has its
 * own single-pool cumulative-score rule; other events have none yet).
 *
 * @param string $event Schedule event name
 * @return string|null 'basketball' or 'volleyball'
 */
function vaysf_results_desk_seeding_sport_type($event) {
    $event = trim((string) $event);
    if (stripos($event, 'Basketball') !== false) {
        return 'basketball';
    }
    if (stripos($event, 'Volleyball') !== false) {
        return 'volleyball';
    }
    return null;
}

/**
 * Fetch every preliminary/pool schedule+result row for an event, across all
 * of its pools (unlike vaysf_get_results_desk_pool_progress_rows(), which
 * groups by pool). This is the raw input to the cross-pool seeding ranking —
 * never filtered by the operator's church toolbar filter, since seeding must
 * reflect the true full event, not whatever the UI happens to be showing.
 *
 * @param string $event Schedule event name
 * @param int $schedule_version Published schedule version
 * @return array<int,array<string,mixed>>
 */
function vaysf_results_desk_get_event_prelim_rows($event, $schedule_version) {
    global $wpdb;

    $event = sanitize_text_field($event);
    $schedule_version = absint($schedule_version);
    if ($event === '' || !$schedule_version) {
        return array();
    }

    $table_schedules = vaysf_get_table_name('schedules');
    $table_results = vaysf_get_table_name('results');
    $rows = $wpdb->get_results(
        $wpdb->prepare(
            "SELECT s.*, r.result_id, r.score_json, r.winner_keys_json, r.public_status, r.current_revision
                FROM $table_schedules s
                LEFT JOIN $table_results r ON r.schedule_id = s.schedule_id
                WHERE s.schedule_version = %d
                  AND s.published_at IS NOT NULL
                  AND s.event = %s
                  AND COALESCE(s.game_status, '') <> 'cancelled'
                  AND LOWER(COALESCE(s.stage, '')) IN ('pool', 'prelim', 'preliminary')
                ORDER BY s.pool_id, s.scheduled_time IS NULL, s.scheduled_time, s.game_key",
            $schedule_version,
            $event
        ),
        ARRAY_A
    );

    return is_array($rows) ? $rows : array();
}

/**
 * Extract the raw per-set point totals for a two-team volleyball schedule
 * row's score payload, in schedule team_a/team_b order (not sorted-pair
 * order — callers that need the sorted-pair sign convention must flip it
 * themselves, the same way vaysf_results_desk_apply_pool_result() does for
 * its head-to-head map).
 *
 * @param array<string,mixed> $payload Decoded score_json
 * @return array{0:int,1:int}|null [team_a total points, team_b total points], or null if not set-shaped
 */
function vaysf_results_desk_volleyball_match_point_totals($payload) {
    if (empty($payload['sets']) || !is_array($payload['sets'])) {
        return null;
    }

    $team_a_points = 0;
    $team_b_points = 0;
    foreach ($payload['sets'] as $set) {
        if (!is_array($set) || !isset($set['team_a_score'], $set['team_b_score'])) {
            continue;
        }
        $team_a_points += (int) $set['team_a_score'];
        $team_b_points += (int) $set['team_b_score'];
    }

    return array($team_a_points, $team_b_points);
}

/**
 * Build the score map used by event-wide QF seeding.
 *
 * Volleyball result payloads store team_a_score/team_b_score as sets won for
 * display, but the manager's 2026 ranking artifact uses rally points for
 * playoff point differential. Basketball keeps using the existing score
 * fields, with its 40-point cap applied by the caller.
 *
 * @param array<string,mixed> $payload Decoded score_json
 * @param array<int,array{slot:string,key:string,label:string}> $slots Schedule slots
 * @param string $sport_type 'basketball' or 'volleyball'
 * @return array<string,int>
 */
function vaysf_results_desk_seeding_score_by_team($payload, $slots, $sport_type) {
    if ($sport_type === 'volleyball' && count($slots) >= 2) {
        $totals = vaysf_results_desk_volleyball_match_point_totals($payload);
        if ($totals !== null) {
            return array(
                $slots[0]['key'] => $totals[0],
                $slots[1]['key'] => $totals[1],
            );
        }
    }

    return vaysf_results_desk_pool_score_by_team($payload, $slots);
}

/**
 * Count volleyball W-L using the manager worksheet's rally-game convention.
 *
 * The public result stores match winners in winner_keys_json, but the 2026
 * manager ranking sheet counts each 25-point rally game as one W/L unit.
 *
 * @param array<string,mixed> $payload Decoded score_json
 * @return array<string,array<string,int>> Slot letter => wins/losses/played
 */
function vaysf_results_desk_volleyball_set_record_by_slot($payload) {
    $record = array(
        'a' => array('wins' => 0, 'losses' => 0, 'played' => 0),
        'b' => array('wins' => 0, 'losses' => 0, 'played' => 0),
    );

    if (empty($payload['sets']) || !is_array($payload['sets'])) {
        return $record;
    }

    foreach ($payload['sets'] as $set) {
        if (!is_array($set) || !isset($set['team_a_score'], $set['team_b_score'])) {
            continue;
        }

        $team_a_score = (int) $set['team_a_score'];
        $team_b_score = (int) $set['team_b_score'];
        if ($team_a_score === $team_b_score) {
            continue;
        }

        $record['a']['played']++;
        $record['b']['played']++;
        if ($team_a_score > $team_b_score) {
            $record['a']['wins']++;
            $record['b']['losses']++;
        } else {
            $record['b']['wins']++;
            $record['a']['losses']++;
        }
    }

    return $record;
}

/**
 * Infer Basketball preliminary bye wins from an uneven pool schedule.
 *
 * Matthew's 2026 Basketball worksheet uses total opponent wins for Difficulty
 * of Schedule. If an opponent received an official bye in preliminary play,
 * that bye strengthens the opponent for DoS math, but it is not displayed as
 * an extra played match in that team's own QF standing.
 *
 * @param array<string,array<string,int>> $scheduled_by_pool Team scheduled counts per pool
 * @return array<string,int> Bye wins by team key
 */
function vaysf_results_desk_infer_basketball_bye_wins($scheduled_by_pool) {
    $bye_wins_by_team = array();

    foreach ($scheduled_by_pool as $pool_counts) {
        if (!is_array($pool_counts) || empty($pool_counts)) {
            continue;
        }

        $target_games = max(array_map('absint', array_values($pool_counts)));
        if ($target_games <= 0) {
            continue;
        }

        foreach ($pool_counts as $team_key => $scheduled_count) {
            $team_key = (string) $team_key;
            $bye_wins = $target_games - absint($scheduled_count);
            if ($bye_wins <= 0) {
                continue;
            }

            $bye_wins_by_team[$team_key] = (int) ($bye_wins_by_team[$team_key] ?? 0) + $bye_wins;
        }
    }

    return $bye_wins_by_team;
}

/**
 * Accumulate cross-pool W-L/points/opponent stats for one event's teams from
 * its preliminary rows (Issue #329 §3.1–3.3/3.4 ranking basis). Parallel to,
 * but deliberately separate from, vaysf_results_desk_apply_pool_result():
 * that function is proven and shared by the per-pool "Pools Progress For
 * Review" display, which stays on its own existing tie-break order per the
 * issue's non-goals — this function needs additional per-game data (capped
 * point differential, opponent identity for difficulty-of-schedule, the
 * single-match point differential for Volleyball §3.4.1.1) that function
 * does not expose, and mixing those concerns into the proven per-pool path
 * risked regressing it.
 *
 * @param array<int,array<string,mixed>> $rows From vaysf_results_desk_get_event_prelim_rows()
 * @param string $sport_type 'basketball' or 'volleyball'
 * @return array{0:array<string,array<string,mixed>>,1:array<string,string>,2:array<string,int>,3:array<string,bool>} [teams_by_key, head_to_head, vb_match_point_diff, pool_complete_by_id]
 */
function vaysf_results_desk_accumulate_event_seeding_stats($rows, $sport_type) {
    $teams = array();
    $head_to_head = array();
    $vb_match_point_diff = array();
    $pool_game_counts = array();
    $pool_missing_counts = array();
    $scheduled_by_pool = array();
    $opponents_played = array();

    foreach ($rows as $row) {
        $slots = vaysf_results_desk_pool_team_slots($row);
        if (count($slots) !== 2) {
            continue; // Basketball/Volleyball are always 2-team; skip anything malformed defensively.
        }

        $pool_id = trim((string) ($row['pool_id'] ?? '')) ?: 'P1';
        $pool_game_counts[$pool_id] = ($pool_game_counts[$pool_id] ?? 0) + 1;

        foreach ($slots as $slot) {
            vaysf_results_desk_ensure_pool_team($teams, $slot['key'], $slot['label']);
            $scheduled_by_pool[$pool_id][$slot['key']] = ($scheduled_by_pool[$pool_id][$slot['key']] ?? 0) + 1;
        }

        $score_json = trim((string) ($row['score_json'] ?? ''));
        if ($score_json === '') {
            $pool_missing_counts[$pool_id] = ($pool_missing_counts[$pool_id] ?? 0) + 1;
            continue;
        }
        $payload = vaysf_results_desk_decode_json_array($score_json);
        $scores = vaysf_results_desk_seeding_score_by_team($payload, $slots, $sport_type);
        if (!$payload || !$scores) {
            $pool_missing_counts[$pool_id] = ($pool_missing_counts[$pool_id] ?? 0) + 1;
            continue;
        }

        $slot_a = $slots[0]['key'];
        $slot_b = $slots[1]['key'];
        $opponents_played[$slot_a][] = $slot_b;
        $opponents_played[$slot_b][] = $slot_a;

        $winner_keys = vaysf_results_desk_decode_json_array($row['winner_keys_json'] ?? '');
        $winner_keys = array_values(array_filter(array_map('strval', $winner_keys)));
        $winner_lookup = array_fill_keys($winner_keys, true);
        $is_tie = !empty($payload['is_tie']) || count($winner_keys) > 1 || !empty($payload['split_match']);
        $volleyball_set_record = $sport_type === 'volleyball'
            ? vaysf_results_desk_volleyball_set_record_by_slot($payload)
            : array();

        foreach ($slots as $slot) {
            $key = $slot['key'];
            if (!isset($scores[$key])) {
                continue;
            }
            $slot_letter = (string) ($slot['slot'] ?? '');
            $set_record = $volleyball_set_record[$slot_letter] ?? null;
            $played_units = is_array($set_record) && (int) ($set_record['played'] ?? 0) > 0
                ? (int) $set_record['played']
                : 1;
            $teams[$key]['played'] += $played_units;
            $teams[$key]['for'] += (int) $scores[$key];
            $opponent_key = ($key === $slot_a) ? $slot_b : $slot_a;
            $opponent_score = (int) ($scores[$opponent_key] ?? 0);
            $teams[$key]['against'] += $opponent_score;
            $game_diff = (int) $scores[$key] - $opponent_score;
            if ($sport_type === 'basketball') {
                $game_diff = max(-40, min(40, $game_diff));
            }
            $teams[$key]['capped_diff'] = ($teams[$key]['capped_diff'] ?? 0) + $game_diff;
            $teams[$key]['diff'] = $teams[$key]['for'] - $teams[$key]['against'];

            if ($sport_type === 'volleyball' && is_array($set_record) && (int) ($set_record['played'] ?? 0) > 0) {
                $teams[$key]['wins'] += (int) ($set_record['wins'] ?? 0);
                $teams[$key]['losses'] += (int) ($set_record['losses'] ?? 0);
            } elseif ($is_tie) {
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

        // Volleyball §3.4.1.1: when a preliminary match itself ends in a 1-1
        // set split (recorded as split_match), the tie-break of last resort
        // before difficulty-of-schedule is that single match's own point
        // differential — captured here in sorted-pair sign convention.
        if ($sport_type === 'volleyball' && !empty($payload['split_match'])) {
            $totals = vaysf_results_desk_volleyball_match_point_totals($payload);
            if ($totals !== null) {
                list($team_a_points, $team_b_points) = $totals;
                $raw_diff = $team_a_points - $team_b_points; // team_a here = this row's team_a_key
                $row_team_a_key = trim((string) ($row['team_a_key'] ?? ''));
                $vb_match_point_diff[$pair_key] = ($row_team_a_key === $pair[0]) ? $raw_diff : -$raw_diff;
            }
        }
    }

    $pool_complete_by_id = array();
    foreach ($pool_game_counts as $pool_id => $count) {
        $pool_complete_by_id[$pool_id] = ($count > 0) && empty($pool_missing_counts[$pool_id]);
    }

    $basketball_bye_wins_by_team = $sport_type === 'basketball'
        ? vaysf_results_desk_infer_basketball_bye_wins($scheduled_by_pool)
        : array();

    // Difficulty of schedule requires final W-L for every team, which the
    // pass above just finished computing, hence the separate second pass here.
    // Basketball DoS is total opponent wins, with inferred bye wins counted
    // for the opponent only. Volleyball DoS is average opponent win percentage.
    foreach ($teams as $key => $team) {
        $sos = 0;
        $opponent_count = 0;
        foreach (($opponents_played[$key] ?? array()) as $opponent_key) {
            $opponent = $teams[$opponent_key] ?? null;
            if ($opponent) {
                if ($sport_type === 'volleyball') {
                    $opponent_games = (int) $opponent['wins'] + (int) $opponent['losses'] + (int) ($opponent['ties'] ?? 0);
                    if ($opponent_games > 0) {
                        $sos += (((int) $opponent['wins']) + (0.5 * (int) ($opponent['ties'] ?? 0))) / $opponent_games;
                        $opponent_count++;
                    }
                } else {
                    $sos += (int) $opponent['wins'] + (int) ($basketball_bye_wins_by_team[$opponent_key] ?? 0);
                }
            }
        }
        $teams[$key]['sos'] = $sport_type === 'volleyball' && $opponent_count > 0
            ? round($sos / $opponent_count, 6)
            : $sos;
    }

    return array($teams, $head_to_head, $vb_match_point_diff, $pool_complete_by_id);
}

/**
 * Fetch recorded coin-toss flips for an event/schedule_version as a
 * pair-key => winner_key decision map, in the same sorted-pair convention as
 * the head-to-head map (Issue #329). Includes every flip ever recorded for
 * this event/version — the log is permanent and never pruned, so a
 * re-confirm after a later score correction still honors earlier flips
 * rather than asking the coordinator to re-flip unchanged ties.
 *
 * @param string $event Schedule event name
 * @param int $schedule_version Published schedule version
 * @return array<string,string> pair_key => winner team_key
 */
function vaysf_get_coin_toss_decisions($event, $schedule_version) {
    global $wpdb;

    $event = sanitize_text_field($event);
    $schedule_version = absint($schedule_version);
    if ($event === '' || !$schedule_version) {
        return array();
    }

    $table = vaysf_get_table_name('coin_toss_flip');
    $rows = $wpdb->get_results(
        $wpdb->prepare(
            "SELECT team_a_key, team_b_key, winner_key FROM $table WHERE schedule_version = %d AND event = %s ORDER BY flip_id",
            $schedule_version,
            $event
        ),
        ARRAY_A
    );
    if (!is_array($rows)) {
        return array();
    }

    $decisions = array();
    foreach ($rows as $row) {
        $pair = array((string) $row['team_a_key'], (string) $row['team_b_key']);
        sort($pair);
        $decisions[implode('|', $pair)] = (string) $row['winner_key'];
    }

    return $decisions;
}

/**
 * Build the effective pairwise head-to-head map for QF seeding. Volleyball
 * split matches are upgraded to the winner of that match's rally-point
 * differential, matching the manager's 2026 worksheet notes.
 *
 * @param array<string,string> $head_to_head pair_key => winner key or 'tie'
 * @param array<string,int> $vb_match_point_diff pair_key => single-match point diff
 * @param bool $is_volleyball Whether the current event is Volleyball
 * @return array<string,string>
 */
function vaysf_results_desk_effective_head_to_head($head_to_head, $vb_match_point_diff, $is_volleyball) {
    $effective_head_to_head = $head_to_head;
    if ($is_volleyball) {
        foreach ($vb_match_point_diff as $pair_key => $point_diff) {
            if (($effective_head_to_head[$pair_key] ?? null) === 'tie' && $point_diff !== 0) {
                $pair = explode('|', $pair_key);
                $effective_head_to_head[$pair_key] = $point_diff > 0 ? $pair[0] : $pair[1];
            }
        }
    }

    return $effective_head_to_head;
}

/**
 * Compare two teams within an equal W-L seeding group.
 *
 * Volleyball keeps the manager's pairwise application of the 2026 handbook:
 * direct head-to-head when present, then difficulty of schedule, then total
 * rally-point differential, then coin toss. Basketball follows the coordinator
 * revision: difficulty of schedule, capped point differential, fewer points
 * allowed, head-to-head, then coin toss.
 *
 * @param array<string,mixed> $a First team row
 * @param array<string,mixed> $b Second team row
 * @param array<string,string> $effective_head_to_head pair_key => winner key or 'tie'
 * @param array<string,string> $coin_toss_decisions pair_key => winner key
 * @param string $diff_field 'capped_diff' (Basketball) or 'diff' (Volleyball)
 * @param string $sport_type 'basketball' or 'volleyball'
 * @return int -1 when $a ranks higher, 1 when $b ranks higher, 0 when unresolved
 */
function vaysf_results_desk_compare_seeding_pair($a, $b, $effective_head_to_head, $coin_toss_decisions, $diff_field, $sport_type = 'volleyball') {
    $key_a = (string) ($a['team_key'] ?? '');
    $key_b = (string) ($b['team_key'] ?? '');
    if ($key_a === '' || $key_b === '' || $key_a === $key_b) {
        return 0;
    }

    $pair = array($key_a, $key_b);
    sort($pair);
    $pair_key = implode('|', $pair);

    $a_sos = (float) ($a['sos'] ?? 0);
    $b_sos = (float) ($b['sos'] ?? 0);
    $a_diff = (float) ($a[$diff_field] ?? 0);
    $b_diff = (float) ($b[$diff_field] ?? 0);

    if ($sport_type === 'basketball') {
        if (abs($a_sos - $b_sos) > 0.000001) {
            return $a_sos > $b_sos ? -1 : 1;
        }

        if (abs($a_diff - $b_diff) > 0.000001) {
            return $a_diff > $b_diff ? -1 : 1;
        }

        $a_against = (float) ($a['against'] ?? 0);
        $b_against = (float) ($b['against'] ?? 0);
        if (abs($a_against - $b_against) > 0.000001) {
            return $a_against < $b_against ? -1 : 1;
        }

        if (!empty($effective_head_to_head[$pair_key]) && $effective_head_to_head[$pair_key] !== 'tie') {
            return $effective_head_to_head[$pair_key] === $key_a ? -1 : 1;
        }

        if (!empty($coin_toss_decisions[$pair_key])) {
            return $coin_toss_decisions[$pair_key] === $key_a ? -1 : 1;
        }

        return 0;
    }

    if (!empty($effective_head_to_head[$pair_key]) && $effective_head_to_head[$pair_key] !== 'tie') {
        return $effective_head_to_head[$pair_key] === $key_a ? -1 : 1;
    }

    if (abs($a_sos - $b_sos) > 0.000001) {
        return $a_sos > $b_sos ? -1 : 1;
    }

    if (abs($a_diff - $b_diff) > 0.000001) {
        return $a_diff > $b_diff ? -1 : 1;
    }

    if (!empty($coin_toss_decisions[$pair_key])) {
        return $coin_toss_decisions[$pair_key] === $key_a ? -1 : 1;
    }

    return 0;
}

/**
 * Resolve one still-tied W-L group through the sport-specific 2026 QF
 * seeding tiebreak chain.
 *
 * @param array<int,array<string,mixed>> $group Team rows, already tied on wins/losses
 * @param array<string,string> $head_to_head pair_key => winner key or 'tie'
 * @param array<string,int> $vb_match_point_diff pair_key => single-match point diff (Volleyball only)
 * @param array<string,string> $coin_toss_decisions pair_key => winner key, from recorded flips
 * @param bool $is_volleyball
 * @param string $diff_field 'capped_diff' (Basketball) or 'diff' (Volleyball)
 * @param string $sport_type 'basketball' or 'volleyball'
 * @return array{ordered:array<int,array<string,mixed>>,unresolved_groups:array<int,array<int,string>>}
 */
function vaysf_results_desk_resolve_seeding_group($group, $head_to_head, $vb_match_point_diff, $coin_toss_decisions, $is_volleyball, $diff_field, $sport_type = 'volleyball') {
    if (count($group) <= 1) {
        return array('ordered' => $group, 'unresolved_groups' => array());
    }

    $manager_head_to_head = vaysf_results_desk_effective_head_to_head($head_to_head, $vb_match_point_diff, $is_volleyball);
    $manager_sorted = $group;
    usort($manager_sorted, function ($a, $b) use ($manager_head_to_head, $coin_toss_decisions, $diff_field, $sport_type) {
        $result = vaysf_results_desk_compare_seeding_pair($a, $b, $manager_head_to_head, $coin_toss_decisions, $diff_field, $sport_type);
        if ($result !== 0) {
            return $result;
        }

        return strcasecmp((string) ($a['label'] ?? ''), (string) ($b['label'] ?? ''));
    });

    $unresolved_keys = array();
    foreach ($manager_sorted as $a_index => $team_a) {
        foreach ($manager_sorted as $b_index => $team_b) {
            if ($b_index <= $a_index) {
                continue;
            }
            if (vaysf_results_desk_compare_seeding_pair($team_a, $team_b, $manager_head_to_head, $coin_toss_decisions, $diff_field, $sport_type) === 0) {
                $unresolved_keys[(string) $team_a['team_key']] = true;
                $unresolved_keys[(string) $team_b['team_key']] = true;
            }
        }
    }

    return array(
        'ordered' => $manager_sorted,
        'unresolved_groups' => empty($unresolved_keys) ? array() : array(array_keys($unresolved_keys)),
    );
}

/**
 * Shared numeric cascade step for vaysf_results_desk_resolve_seeding_group():
 * sort the group by one numeric field (descending), re-group whatever
 * remains exactly tied on it, and recurse into the next step for each
 * resulting sub-group. $next_step is 'point_diff' (after difficulty of
 * schedule) or 'coin_toss' (after point differential, the final step).
 *
 * @param array<int,array<string,mixed>> $group
 * @param string $field Numeric field to sort by, descending
 * @param array<string,string> $head_to_head
 * @param array<string,int> $vb_match_point_diff
 * @param array<string,string> $coin_toss_decisions
 * @param bool $is_volleyball
 * @param string $diff_field
 * @param string $next_step 'point_diff'|'coin_toss'
 * @return array{ordered:array<int,array<string,mixed>>,unresolved_groups:array<int,array<int,string>>}
 */
function vaysf_results_desk_resolve_seeding_group_numeric($group, $field, $head_to_head, $vb_match_point_diff, $coin_toss_decisions, $is_volleyball, $diff_field, $next_step) {
    $sorted = $group;
    usort($sorted, function ($a, $b) use ($field) {
        $a_val = (int) ($a[$field] ?? 0);
        $b_val = (int) ($b[$field] ?? 0);
        if ($a_val !== $b_val) {
            return $a_val > $b_val ? -1 : 1;
        }
        return strcasecmp((string) ($a['label'] ?? ''), (string) ($b['label'] ?? ''));
    });

    $ordered = array();
    $unresolved_groups = array();
    $i = 0;
    $n = count($sorted);
    while ($i < $n) {
        $j = $i;
        while ($j + 1 < $n && (int) $sorted[$j + 1][$field] === (int) $sorted[$i][$field]) {
            $j++;
        }
        $sub_group = array_slice($sorted, $i, $j - $i + 1);

        if (count($sub_group) === 1) {
            $ordered[] = $sub_group[0];
        } elseif ($next_step === 'point_diff') {
            $result = vaysf_results_desk_resolve_seeding_group_numeric(
                $sub_group,
                $diff_field,
                $head_to_head,
                $vb_match_point_diff,
                $coin_toss_decisions,
                $is_volleyball,
                $diff_field,
                'coin_toss'
            );
            $ordered = array_merge($ordered, $result['ordered']);
            $unresolved_groups = array_merge($unresolved_groups, $result['unresolved_groups']);
        } else {
            // Final step: coin toss. A fully-decided coin-toss group (every
            // pair flipped) resolves like head-to-head; anything still
            // missing a flip is reported as unresolved for the UI to offer a
            // flip on, rather than guessed.
            $sub_keys = array_map(function ($t) {
                return $t['team_key'];
            }, $sub_group);
            $by_key = array_combine($sub_keys, $sub_group);
            $coin_order = vaysf_resolve_pool_head_to_head_group($sub_keys, $coin_toss_decisions);
            if ($coin_order !== null) {
                foreach ($coin_order as $key) {
                    $ordered[] = $by_key[$key];
                }
            } else {
                foreach ($sub_group as $team) {
                    $ordered[] = $team;
                }
                $unresolved_groups[] = $sub_keys;
            }
        }

        $i = $j + 1;
    }

    return array('ordered' => $ordered, 'unresolved_groups' => $unresolved_groups);
}

/**
 * Compute the confirmed-ready cross-pool QF seeding ranking for one
 * Basketball/Volleyball event (Issue #329, official 2026 rules): W-L record,
 * then the sport-specific tie chain. Basketball uses the coordinator's
 * revised DoS -> capped point differential -> points allowed -> head-to-head
 * order; Volleyball uses the Loc/manager Volleyball method.
 *
 * @param string $event Schedule event name
 * @param int $schedule_version Published schedule version
 * @return array<string,mixed> {sport_type, complete, pools_complete, rankings, fully_resolved, unresolved_groups, qf_fully_resolved, qf_unresolved_groups}
 */
function vaysf_results_desk_get_event_seeding_rankings($event, $schedule_version) {
    $sport_type = vaysf_results_desk_seeding_sport_type($event);
    $rows = vaysf_results_desk_get_event_prelim_rows($event, $schedule_version);

    list($teams, $head_to_head, $vb_match_point_diff, $pools_complete) = vaysf_results_desk_accumulate_event_seeding_stats($rows, $sport_type);

    $complete = !empty($pools_complete) && !in_array(false, array_values($pools_complete), true);
    $coin_toss_decisions = vaysf_get_coin_toss_decisions($event, $schedule_version);
    $diff_field = $sport_type === 'basketball' ? 'capped_diff' : 'diff';
    $is_volleyball = $sport_type === 'volleyball';

    $rankings = array_values($teams);
    usort($rankings, function ($a, $b) {
        $a_wins = (int) ($a['wins'] ?? 0);
        $b_wins = (int) ($b['wins'] ?? 0);
        if ($a_wins !== $b_wins) {
            return $a_wins > $b_wins ? -1 : 1;
        }
        $a_losses = (int) ($a['losses'] ?? 0);
        $b_losses = (int) ($b['losses'] ?? 0);
        if ($a_losses !== $b_losses) {
            return $a_losses < $b_losses ? -1 : 1;
        }
        return strcasecmp((string) ($a['label'] ?? ''), (string) ($b['label'] ?? ''));
    });

    $groups = array();
    $i = 0;
    $n = count($rankings);
    while ($i < $n) {
        $j = $i;
        while (
            $j + 1 < $n
            && (int) $rankings[$j + 1]['wins'] === (int) $rankings[$i]['wins']
            && (int) $rankings[$j + 1]['losses'] === (int) $rankings[$i]['losses']
        ) {
            $j++;
        }
        $groups[] = array_slice($rankings, $i, $j - $i + 1);
        $i = $j + 1;
    }

    $ordered = array();
    $unresolved_groups = array();
    foreach ($groups as $group) {
        $result = vaysf_results_desk_resolve_seeding_group($group, $head_to_head, $vb_match_point_diff, $coin_toss_decisions, $is_volleyball, $diff_field, $sport_type);
        $ordered = array_merge($ordered, $result['ordered']);
        $unresolved_groups = array_merge($unresolved_groups, $result['unresolved_groups']);
    }

    $unresolved_keys = array();
    foreach ($unresolved_groups as $group_keys) {
        foreach ($group_keys as $key) {
            $unresolved_keys[$key] = true;
        }
    }
    foreach ($ordered as $index => $team) {
        $ordered[$index]['rank'] = $index + 1;
        $ordered[$index]['seed'] = $index + 1;
        $ordered[$index]['advances'] = ($index < 8) && empty($unresolved_keys[$team['team_key']]);
        $ordered[$index]['needs_coin_toss'] = !empty($unresolved_keys[$team['team_key']]);
    }

    $qf_seed_keys = array();
    foreach ($ordered as $index => $team) {
        if ($index >= 8) {
            break;
        }
        $qf_seed_keys[$team['team_key']] = true;
    }

    $qf_unresolved_groups = array();
    foreach ($unresolved_groups as $group_keys) {
        foreach ($group_keys as $key) {
            if (!empty($qf_seed_keys[$key])) {
                $qf_unresolved_groups[] = $group_keys;
                break;
            }
        }
    }

    return array(
        'sport_type' => $sport_type,
        'complete' => $complete,
        'pools_complete' => $pools_complete,
        'rankings' => $ordered,
        'fully_resolved' => empty($unresolved_groups),
        'unresolved_groups' => $unresolved_groups,
        'qf_fully_resolved' => empty($qf_unresolved_groups),
        'qf_unresolved_groups' => $qf_unresolved_groups,
    );
}


function vaysf_confirm_event_qf_seeding($user_id, $event, $schedule_version = null) {
    global $wpdb;

    $user_id = absint($user_id);
    $event = sanitize_text_field($event);
    if (!$user_id || $event === '') {
        return new WP_Error('vaysf_qf_seeding_missing_context', __('QF seeding confirmation is missing the user or event.', 'vaysf'));
    }
    if (!vaysf_results_desk_seeding_sport_type($event)) {
        return new WP_Error('vaysf_qf_seeding_wrong_event', __('This action only applies to Basketball and Volleyball.', 'vaysf'));
    }

    if ($schedule_version === null) {
        $schedule_version = vaysf_get_current_published_schedule_version();
    }
    if ($schedule_version === null) {
        return new WP_Error('vaysf_qf_seeding_no_schedule', __('No published schedule is available for QF seeding confirmation.', 'vaysf'));
    }
    $schedule_version = absint($schedule_version);

    $seeding = vaysf_results_desk_get_event_seeding_rankings($event, $schedule_version);
    if (empty($seeding['rankings'])) {
        return new WP_Error('vaysf_qf_seeding_no_results', __('No reported preliminary results found for this event.', 'vaysf'));
    }
    if (empty($seeding['complete'])) {
        return new WP_Error('vaysf_qf_seeding_incomplete', __('Every pool for this event must be fully reported before confirming QF seeding.', 'vaysf'));
    }
    if (empty($seeding['qf_fully_resolved'])) {
        $pending = array();
        foreach ($seeding['qf_unresolved_groups'] as $group) {
            $pending[] = implode(' vs ', $group);
        }
        return new WP_Error(
            'vaysf_qf_seeding_needs_coin_toss',
            sprintf(
                /* translators: %s: list of still-tied team groups */
                __('These teams are still tied after every deterministic tie-break and need a coin toss before confirming: %s.', 'vaysf'),
                implode('; ', $pending)
            )
        );
    }

    $pool_id = vaysf_results_desk_event_seeding_pool_id();

    // Record which result rows (by revision number) this confirmation was
    // based on, across every pool of the event, so a later correction
    // anywhere in the event is detected as staleness (vaysf_pool_advancement_is_stale()).
    $table_schedules = vaysf_get_table_name('schedules');
    $table_results = vaysf_get_table_name('results');
    $result_rows = $wpdb->get_results(
        $wpdb->prepare(
            "SELECT r.result_id, r.current_revision
                FROM $table_schedules s
                INNER JOIN $table_results r ON r.schedule_id = s.schedule_id
                WHERE s.schedule_version = %d
                  AND s.published_at IS NOT NULL
                  AND s.event = %s
                  AND LOWER(COALESCE(s.stage, '')) IN ('pool', 'prelim', 'preliminary')
                  AND COALESCE(s.game_status, '') <> 'cancelled'",
            $schedule_version,
            $event
        ),
        ARRAY_A
    );
    $based_on_revisions = array();
    foreach ((array) $result_rows as $row) {
        $based_on_revisions[(int) $row['result_id']] = (int) $row['current_revision'];
    }

    $now = current_time('mysql');
    $snapshot_json = wp_json_encode($seeding['rankings']);
    $revisions_json = wp_json_encode($based_on_revisions);
    if ($snapshot_json === false || $revisions_json === false) {
        return new WP_Error('vaysf_qf_seeding_json_failed', __('Could not encode the QF seeding snapshot.', 'vaysf'));
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
                'review_note' => '',
                'updated_at' => $now,
            ),
            array('advancement_id' => absint($existing['advancement_id'])),
            array('%d', '%d', '%s', '%s', '%s', '%s', '%s'),
            array('%d')
        );
        if ($updated === false) {
            return new WP_Error('vaysf_qf_seeding_update_failed', __('Could not update the QF seeding confirmation.', 'vaysf'));
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
                'review_note' => '',
                'created_at' => $now,
                'updated_at' => $now,
            ),
            array('%s', '%s', '%d', '%d', '%s', '%s', '%s', '%s', '%s', '%s')
        );
        if ($created === false) {
            return new WP_Error('vaysf_qf_seeding_create_failed', __('Could not create the QF seeding confirmation.', 'vaysf'));
        }
    }

    return $seeding['rankings'];
}

/**
 * Record one server-performed coin-toss flip between two still-tied teams
 * (Issue #329, answer to "who performs the flip": the coordinator names who
 * calls and what they call, but the server generates the result so no human
 * — coordinator or team — can influence the fairness of the flip itself).
 * Refuses to re-flip a pair that already has a recorded decision, since the
 * log is permanent (vaysf_get_coin_toss_decisions() never expires or prunes
 * it) — a stale seeding snapshot is re-derived from the same flips, not
 * re-flipped.
 *
 * @param int $user_id
 * @param string $event
 * @param int $schedule_version
 * @param string $team_a_key
 * @param string $team_a_label
 * @param string $team_b_key
 * @param string $team_b_label
 * @param string $call_by_key Must be $team_a_key or $team_b_key
 * @param string $call 'heads' or 'tails'
 * @return array<string,string>|WP_Error
 */
function vaysf_record_coin_toss_flip($user_id, $event, $schedule_version, $team_a_key, $team_a_label, $team_b_key, $team_b_label, $call_by_key, $call) {
    global $wpdb;

    $user_id = absint($user_id);
    $event = sanitize_text_field($event);
    $schedule_version = absint($schedule_version);
    $team_a_key = sanitize_text_field($team_a_key);
    $team_a_label = sanitize_text_field($team_a_label);
    $team_b_key = sanitize_text_field($team_b_key);
    $team_b_label = sanitize_text_field($team_b_label);
    $call_by_key = sanitize_text_field($call_by_key);
    $call = strtolower(sanitize_text_field($call));

    if (!$user_id || $event === '' || !$schedule_version || $team_a_key === '' || $team_b_key === '' || $team_a_key === $team_b_key) {
        return new WP_Error('vaysf_coin_toss_missing_context', __('Coin toss is missing required team information.', 'vaysf'));
    }
    if (!in_array($call_by_key, array($team_a_key, $team_b_key), true)) {
        return new WP_Error('vaysf_coin_toss_bad_caller', __('The calling team must be one of the two tied teams.', 'vaysf'));
    }
    if (!in_array($call, array('heads', 'tails'), true)) {
        return new WP_Error('vaysf_coin_toss_bad_call', __('Choose heads or tails.', 'vaysf'));
    }

    $pair = array($team_a_key, $team_b_key);
    sort($pair);
    $existing_decisions = vaysf_get_coin_toss_decisions($event, $schedule_version);
    if (isset($existing_decisions[implode('|', $pair)])) {
        return new WP_Error('vaysf_coin_toss_already_flipped', __('This pair already has a recorded coin-toss decision.', 'vaysf'));
    }

    $result = ((int) wp_rand(0, 1) === 0) ? 'heads' : 'tails';
    $other_key = ($call_by_key === $team_a_key) ? $team_b_key : $team_a_key;
    $winner_key = ($result === $call) ? $call_by_key : $other_key;
    $winner_label = ($winner_key === $team_a_key) ? $team_a_label : $team_b_label;

    $table = vaysf_get_table_name('coin_toss_flip');
    $inserted = $wpdb->insert(
        $table,
        array(
            'schedule_version' => $schedule_version,
            'event' => $event,
            'team_a_key' => $team_a_key,
            'team_b_key' => $team_b_key,
            'call_by_key' => $call_by_key,
            'call_side' => $call,
            'result' => $result,
            'winner_key' => $winner_key,
            'flipped_by_user_id' => $user_id,
            'created_at' => current_time('mysql'),
        ),
        array('%d', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%d', '%s')
    );
    if ($inserted === false) {
        return new WP_Error('vaysf_coin_toss_insert_failed', __('Could not record the coin toss.', 'vaysf'));
    }

    return array(
        'result' => $result,
        'call' => $call,
        'call_by_key' => $call_by_key,
        'winner_key' => $winner_key,
        'winner_label' => $winner_label,
    );
}

/**
 * Return a compact dropdown label for a confirmed team-sport candidate.
 *
 * @param array<string,mixed> $team Candidate team model
 * @return string
 */
function vaysf_results_desk_team_qf_option_label($team) {
    $seed = absint($team['seed'] ?? 0);
    $label = trim((string) ($team['label'] ?? $team['team_key'] ?? ''));
    if ($label === '') {
        return __('TBD', 'vaysf');
    }

    return $seed > 0 ? sprintf(__('#%1$d %2$s', 'vaysf'), $seed, $label) : $label;
}

/**
 * Fixed BB/VB game_key prefix per event (Issue #329). Must stay in sync with
 * middleware/config.py's SPORT_TYPE table and
 * middleware/scheduling/approved_games.py's PREFIX_BY_EVENT map — PHP and the
 * Python middleware do not share this mapping across the language boundary.
 *
 * @param string $event Schedule event name
 * @return string 'BBM'/'VBM'/'VBW', or '' if unrecognized
 */
function vaysf_results_desk_team_qf_event_prefix($event) {
    $map = array(
        'Basketball - Men Team' => 'BBM',
        'Volleyball - Men Team' => 'VBM',
        'Volleyball - Women Team' => 'VBW',
    );
    return $map[trim((string) $event)] ?? '';
}

/**
 * Fixed 8-team QF bracket seeding (Issue #329): QF-1 => seeds [1,8], etc.
 * Standard seeding that keeps seed 1 and seed 2 on opposite bracket halves
 * until the Final, since QF-1/QF-2 feed Semi-1 and QF-3/QF-4 feed Semi-2
 * (vaysf_get_playoff_advancement_targets()'s existing ceil(N/2) mapping).
 * This is only a starting arrangement — freely reorderable by the
 * coordinator via the dropdown UI before Apply, the same as every other
 * Results Desk Apply flow, so it does not need to be "the" correct bracket
 * theory, only a reasonable default.
 *
 * @return array<int,array<int,int>> QF number (1-4) => [seed, seed]
 */
function vaysf_results_desk_team_qf_bracket_seed_pairs() {
    return array(
        1 => array(1, 8),
        2 => array(4, 5),
        3 => array(3, 6),
        4 => array(2, 7),
    );
}

/**
 * Gather the confirmed cross-pool QF-seeding Top 8 for one BB/VB event
 * (Issue #329) from the event-wide "ALL" confirmation written by
 * vaysf_confirm_event_qf_seeding() — mirrors
 * vaysf_results_desk_get_bible_challenge_confirmed_teams()'s pattern of
 * reading one already-confirmed snapshot rather than recomputing anything
 * here, so the preview and the Apply handler always agree with what was
 * actually confirmed.
 *
 * @param array<int,array<string,mixed>> $reviews Confirmed pool reviews (from vaysf_results_desk_get_confirmed_pool_reviews())
 * @return array{0:array<string,array<string,mixed>>,1:array<int,string>,2:bool} [teams_by_key, warnings, has_stale_review]
 */
function vaysf_results_desk_get_team_qf_candidate_teams($reviews) {
    $warnings = array();
    $teams_by_key = array();
    $has_stale_review = false;

    $seeding_pool_id = vaysf_results_desk_event_seeding_pool_id();
    $seeding_review = null;
    foreach ($reviews as $review) {
        if ((string) ($review['pool_id'] ?? '') === $seeding_pool_id) {
            $seeding_review = $review;
            break;
        }
    }

    if (!$seeding_review) {
        $warnings[] = __('QF seeding has not been confirmed yet for this event. Use "Confirm All Pools for QF Seeding" once every pool is fully reported.', 'vaysf');
        return array($teams_by_key, $warnings, false);
    }

    if (!empty($seeding_review['stale'])) {
        $has_stale_review = true;
        $warnings[] = __('The confirmed QF seeding is stale — a preliminary result changed since it was confirmed. Re-confirm QF seeding before applying QF rows.', 'vaysf');
    }

    $standings = isset($seeding_review['standings']) && is_array($seeding_review['standings']) ? $seeding_review['standings'] : array();
    foreach ($standings as $team) {
        if (!is_array($team) || empty($team['advances'])) {
            continue;
        }
        $key = trim((string) ($team['team_key'] ?? ''));
        if ($key === '') {
            continue;
        }
        $teams_by_key[$key] = array(
            'team_key' => $key,
            'label' => vaysf_results_desk_preview_team_label($team),
            'seed' => absint($team['seed'] ?? 0),
        );
    }

    if (count($teams_by_key) < 8) {
        $warnings[] = sprintf(
            /* translators: %d: confirmed QF-advancing team count */
            __('Only %d confirmed QF-advancing teams are available; expected 8.', 'vaysf'),
            count($teams_by_key)
        );
    }

    return array($teams_by_key, array_values(array_unique($warnings)), $has_stale_review);
}

/**
 * Build the default QF-1..4 arrangement purely from the fixed bracket-seed
 * template (vaysf_results_desk_team_qf_bracket_seed_pairs()) — the same
 * "always the fresh template, never whatever happens to be in the schedule
 * row" rule vaysf_results_desk_build_bible_challenge_preview() already
 * follows for BC.
 *
 * An earlier version of this function preferred an existing schedule row's
 * current team_a/b_key over the template when that team was still a valid
 * Top 8 confirmed candidate, intending to preserve an operator's prior
 * Apply on revisit. That produced a real bug found live on 2026-07-22
 * staging: a row whose slot A no longer matched any confirmed team (e.g.
 * after re-seeding dropped that team) would fall back to the template for
 * slot A while slot B — still independently "valid" — kept its stale
 * existing value, landing the *same* team in both slots of one QF row
 * whenever the template's slot-A pick for that row happened to already be
 * sitting in the row's slot B from an earlier, differently-seeded bracket.
 * A once-per-row check can't catch that; only a global "already used
 * elsewhere in this arrangement" check could, and by that point the
 * simpler, already-proven BC pattern is the safer choice. An operator who
 * wants to keep a specific arrangement uses the reorder dropdowns
 * (session-only, GET-based) exactly as with BC — the default itself no
 * longer tries to guess it from stale row data.
 *
 * @param string $prefix Event's game_key prefix ('BBM'/'VBM'/'VBW')
 * @param array<string,array<string,mixed>> $teams_by_key Confirmed Top 8, keyed by team_key
 * @return array<string,array<int,string>> game_key => [team_a_key, team_b_key]
 */
function vaysf_results_desk_default_team_qf_arrangement($prefix, $teams_by_key) {
    $by_seed = array();
    foreach ($teams_by_key as $key => $team) {
        $seed = (int) ($team['seed'] ?? 0);
        if ($seed > 0) {
            $by_seed[$seed] = $key;
        }
    }

    $arrangement = array();
    foreach (vaysf_results_desk_team_qf_bracket_seed_pairs() as $qf_number => $seeds) {
        $game_key = $prefix . '-QF-' . $qf_number;
        $arrangement[$game_key] = array(
            $by_seed[$seeds[0]] ?? '',
            $by_seed[$seeds[1]] ?? '',
        );
    }

    return $arrangement;
}

/**
 * Validate a submitted QF-1..4 arrangement against the confirmed Top 8.
 *
 * @param array<string,array<int,string>> $submitted Submitted arrangement
 * @param string $prefix Event's game_key prefix
 * @param array<string,array<string,mixed>> $teams_by_key Confirmed Top 8
 * @return array<string,array<int,string>>|WP_Error
 */
function vaysf_results_desk_validate_team_qf_arrangement($submitted, $prefix, $teams_by_key) {
    $arrangement = array();
    $seen = array();

    foreach (array_keys(vaysf_results_desk_team_qf_bracket_seed_pairs()) as $qf_number) {
        $game_key = $prefix . '-QF-' . $qf_number;
        $picks = isset($submitted[$game_key]) && is_array($submitted[$game_key])
            ? array_values(array_map('sanitize_text_field', $submitted[$game_key]))
            : array();
        if (count($picks) !== 2) {
            return new WP_Error('vaysf_team_qf_apply_invalid', __('Every QF row needs exactly two selected teams.', 'vaysf'));
        }
        foreach ($picks as $pick) {
            if ($pick === '' || !isset($teams_by_key[$pick])) {
                return new WP_Error('vaysf_team_qf_apply_invalid', __('The submitted QF matchup includes a team that is not in the confirmed QF-seeding list.', 'vaysf'));
            }
            if (isset($seen[$pick])) {
                return new WP_Error('vaysf_team_qf_apply_duplicate', __('The same team cannot be assigned to more than one QF slot.', 'vaysf'));
            }
            $seen[$pick] = true;
        }
        $arrangement[$game_key] = $picks;
    }

    return $arrangement;
}

/**
 * Upsert a single BB/VB prewired playoff placeholder row.
 *
 * @param string $event Schedule event name
 * @param int $schedule_version Current schedule version
 * @param string $game_key Target game key
 * @param string $stage Target stage label
 * @param string $team_a_key Placeholder for slot A
 * @param string $team_a_label Placeholder label for slot A
 * @param string $team_b_key Placeholder for slot B
 * @param string $team_b_label Placeholder label for slot B
 * @param string $team_c_key Optional placeholder for slot C
 * @param string $team_c_label Optional placeholder label for slot C
 * @return array<string,mixed>|WP_Error
 */
function vaysf_prewire_team_playoff_row($event, $schedule_version, $game_key, $stage, $team_a_key, $team_a_label, $team_b_key, $team_b_label, $team_c_key = '', $team_c_label = '') {
    global $wpdb;

    $table_schedules = vaysf_get_table_name('schedules');
    $existing = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT * FROM $table_schedules WHERE game_key = %s AND schedule_version = %d",
            $game_key,
            $schedule_version
        ),
        ARRAY_A
    );

    if (!$existing) {
        $other_version = $wpdb->get_row(
            $wpdb->prepare(
                "SELECT schedule_id, schedule_version FROM $table_schedules WHERE game_key = %s LIMIT 1",
                $game_key
            ),
            ARRAY_A
        );
        if ($other_version) {
            return new WP_Error(
                'vaysf_team_playoff_prewire_version_mismatch',
                sprintf(
                    /* translators: 1: game key, 2: existing schedule version, 3: submitted schedule version */
                    __('Schedule row %1$s already exists on schedule version %2$d, not submitted version %3$d. Refresh Results Desk and try again before applying.', 'vaysf'),
                    $game_key,
                    absint($other_version['schedule_version'] ?? 0),
                    $schedule_version
                )
            );
        }
    }

    if ($existing) {
        if (vaysf_schedule_row_has_protected_result($existing)) {
            return array('game_key' => $game_key, 'action' => 'skipped_protected');
        }
    }

    $team_ids = array_values(array_filter(array($team_a_key, $team_b_key, $team_c_key), 'strlen'));
    $team_ids_json = wp_json_encode($team_ids);
    if ($team_ids_json === false) {
        return new WP_Error('vaysf_team_playoff_prewire_json_error', __('Could not encode playoff placeholder team ids.', 'vaysf'));
    }

    $data = array(
        'event' => $event,
        'stage' => $stage,
        'schedule_version' => $schedule_version,
        'team_a_key' => $team_a_key,
        'team_a_label' => $team_a_label,
        'team_a_church_code' => '',
        'team_b_key' => $team_b_key,
        'team_b_label' => $team_b_label,
        'team_b_church_code' => '',
        'team_c_key' => $team_c_key,
        'team_c_label' => $team_c_label,
        'team_c_church_code' => '',
        'team_ids_json' => $team_ids_json,
        'published_at' => current_time('mysql'),
        'updated_at' => current_time('mysql'),
    );
    $formats = array('%s', '%s', '%d', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s');

    if ($existing) {
        $updated = $wpdb->update(
            $table_schedules,
            $data,
            array(
                'schedule_id' => absint($existing['schedule_id']),
                'schedule_version' => $schedule_version,
            ),
            $formats,
            array('%d', '%d')
        );
        if ($updated === false) {
            return new WP_Error('vaysf_team_playoff_prewire_update_failed', sprintf(__('Failed to prewire schedule row %s.', 'vaysf'), $game_key));
        }

        return array('game_key' => $game_key, 'action' => 'prewired');
    }

    $data['game_key'] = $game_key;
    $data['game_status'] = 'scheduled';
    $data['created_at'] = current_time('mysql');
    $created = $wpdb->insert(
        $table_schedules,
        $data,
        array_merge($formats, array('%s', '%s', '%s'))
    );
    if ($created === false) {
        return new WP_Error('vaysf_team_playoff_prewire_create_failed', sprintf(__('Failed to create schedule row %s.', 'vaysf'), $game_key));
    }

    return array('game_key' => $game_key, 'action' => 'created', 'schedule_id' => absint($wpdb->insert_id));
}

/**
 * Prewire BB/VB Semifinal, Final, and 3rd-Place rows after QF assignment
 * (Issue #329: the 3rd-place match is always on the schedule). Unlike the
 * pre-#329 version, this no longer discovers which QF numbers exist —
 * vaysf_apply_team_qf_playoff_preview() always creates QF-1..4 itself first,
 * from the fixed bracket template, so there is no longer a "some QF rows
 * missing" failure mode here to guard against.
 *
 * @param string $event Schedule event name
 * @param int $schedule_version Current schedule version
 * @param string $prefix Event's game_key prefix ('BBM'/'VBM'/'VBW')
 * @return array<int,array<string,mixed>>|WP_Error
 */
function vaysf_prewire_team_playoff_bracket_rows($event, $schedule_version, $prefix) {
    $targets = array(
        array(
            'game_key' => $prefix . '-Semi-1',
            'stage' => 'Semifinal',
            'team_a_key' => 'WIN-' . $prefix . '-QF-1',
            'team_a_label' => 'Winner of ' . $prefix . '-QF-1',
            'team_b_key' => 'WIN-' . $prefix . '-QF-2',
            'team_b_label' => 'Winner of ' . $prefix . '-QF-2',
        ),
        array(
            'game_key' => $prefix . '-Semi-2',
            'stage' => 'Semifinal',
            'team_a_key' => 'WIN-' . $prefix . '-QF-3',
            'team_a_label' => 'Winner of ' . $prefix . '-QF-3',
            'team_b_key' => 'WIN-' . $prefix . '-QF-4',
            'team_b_label' => 'Winner of ' . $prefix . '-QF-4',
        ),
        array(
            'game_key' => $prefix . '-Final',
            'stage' => 'Final',
            'team_a_key' => 'WIN-' . $prefix . '-Semi-1',
            'team_a_label' => 'Winner of ' . $prefix . '-Semi-1',
            'team_b_key' => 'WIN-' . $prefix . '-Semi-2',
            'team_b_label' => 'Winner of ' . $prefix . '-Semi-2',
        ),
        array(
            'game_key' => $prefix . '-3rd-Place',
            'stage' => '3rd Place',
            'team_a_key' => 'LOSE-' . $prefix . '-Semi-1',
            'team_a_label' => 'Loser of ' . $prefix . '-Semi-1',
            'team_b_key' => 'LOSE-' . $prefix . '-Semi-2',
            'team_b_label' => 'Loser of ' . $prefix . '-Semi-2',
        ),
    );

    $results = array();
    foreach ($targets as $target) {
        $result = vaysf_prewire_team_playoff_row(
            $event,
            $schedule_version,
            $target['game_key'],
            $target['stage'],
            $target['team_a_key'],
            $target['team_a_label'],
            $target['team_b_key'],
            $target['team_b_label']
        );
        if (is_wp_error($result)) {
            return $result;
        }
        $results[] = $result;
    }

    return $results;
}
/**
 * Write a confirmed QF-1..4 matchup into Basketball/Volleyball schedule
 * rows, creating them from the fixed bracket template if missing (mirroring
 * vaysf_apply_bible_challenge_playoff_preview()'s create-if-missing
 * pattern), then prewire Semifinal/Final/3rd-Place. The whole operation runs
 * inside one DB transaction: previously (pre-#329) the QF team writes could
 * commit even when downstream prewiring failed, leaving the database
 * changed while the operator saw a bare error — found during 2026-07-21
 * staging testing. Since QF-1..4 are now always created here rather than
 * depended on as pre-existing, that specific failure mode is also
 * structurally gone, but the transaction stays as a second line of defense
 * against any other partial failure (e.g. a DB error mid-loop).
 *
 * @param string $event
 * @param int $schedule_version
 * @param array<string,array<int,string>> $arrangement game_key => 2 team_keys
 * @return array<int,array<string,mixed>>|WP_Error Per-row outcomes on success
 */
function vaysf_apply_team_qf_playoff_preview($event, $schedule_version, $arrangement) {
    global $wpdb;

    $event = sanitize_text_field($event);
    $schedule_version = absint($schedule_version);
    if ($event === '' || !$schedule_version) {
        return new WP_Error('vaysf_team_qf_apply_missing_context', __('Missing event or schedule version.', 'vaysf'));
    }
    if (!vaysf_results_desk_is_team_qf_assignment_event($event)) {
        return new WP_Error('vaysf_team_qf_apply_wrong_event', __('This action only applies to Basketball and Volleyball QF rows.', 'vaysf'));
    }
    $prefix = vaysf_results_desk_team_qf_event_prefix($event);
    if ($prefix === '') {
        return new WP_Error('vaysf_team_qf_apply_no_prefix', __('This event has no configured QF game-key prefix.', 'vaysf'));
    }

    $reviews = vaysf_results_desk_get_confirmed_pool_reviews($event, $schedule_version);
    $candidate_result = vaysf_results_desk_get_team_qf_candidate_teams($reviews);
    $teams_by_key = $candidate_result[0] ?? array();
    $has_stale_review = !empty($candidate_result[2]);
    if ($has_stale_review) {
        return new WP_Error('vaysf_team_qf_apply_stale_review', __('The confirmed QF seeding is stale. Re-confirm QF seeding before applying QF rows.', 'vaysf'));
    }
    if (count($teams_by_key) !== 8) {
        return new WP_Error('vaysf_team_qf_apply_incomplete', __('QF seeding has not been confirmed with exactly 8 teams for this event; nothing was applied.', 'vaysf'));
    }

    $validated = vaysf_results_desk_validate_team_qf_arrangement($arrangement, $prefix, $teams_by_key);
    if (is_wp_error($validated)) {
        return $validated;
    }

    $table_schedules = vaysf_get_table_name('schedules');
    $field_formats = array(
        'event' => '%s', 'stage' => '%s', 'schedule_version' => '%d',
        'team_a_key' => '%s', 'team_a_label' => '%s', 'team_a_church_code' => '%s',
        'team_b_key' => '%s', 'team_b_label' => '%s', 'team_b_church_code' => '%s',
        'team_c_key' => '%s', 'team_c_label' => '%s', 'team_c_church_code' => '%s',
        'team_ids_json' => '%s', 'published_at' => '%s', 'updated_at' => '%s',
        'game_key' => '%s', 'game_status' => '%s', 'created_at' => '%s',
    );

    $wpdb->query('START TRANSACTION');
    $results = array();

    foreach (array_keys(vaysf_results_desk_team_qf_bracket_seed_pairs()) as $qf_number) {
        $game_key = $prefix . '-QF-' . $qf_number;
        $picks = $validated[$game_key];
        $team_a = $teams_by_key[$picks[0]];
        $team_b = $teams_by_key[$picks[1]];

        $existing = $wpdb->get_row(
            $wpdb->prepare(
                "SELECT * FROM $table_schedules WHERE game_key = %s AND schedule_version = %d",
                $game_key,
                $schedule_version
            ),
            ARRAY_A
        );

        if (!$existing) {
            $other_version = $wpdb->get_row(
                $wpdb->prepare(
                    "SELECT schedule_id, schedule_version FROM $table_schedules WHERE game_key = %s LIMIT 1",
                    $game_key
                ),
                ARRAY_A
            );
            if ($other_version) {
                $wpdb->query('ROLLBACK');
                return new WP_Error(
                    'vaysf_team_qf_apply_schedule_version_mismatch',
                    sprintf(
                        /* translators: 1: game key, 2: existing schedule version, 3: submitted schedule version */
                        __('Schedule row %1$s already exists on schedule version %2$d, not submitted version %3$d. Refresh Results Desk and try again before applying.', 'vaysf'),
                        $game_key,
                        absint($other_version['schedule_version'] ?? 0),
                        $schedule_version
                    )
                );
            }
        }
        if ($existing && vaysf_schedule_row_has_protected_result($existing)) {
            $results[] = array('game_key' => $game_key, 'action' => 'skipped_protected');
            continue;
        }

        $team_ids_json = wp_json_encode(array($team_a['team_key'], $team_b['team_key']));
        if ($team_ids_json === false) {
            $wpdb->query('ROLLBACK');
            return new WP_Error('vaysf_team_qf_apply_json_error', __('Could not encode QF team ids.', 'vaysf'));
        }

        $team_a_church = vaysf_extract_church_code_from_team_value($team_a['team_key']);
        if ($team_a_church === '') {
            $team_a_church = vaysf_extract_church_code_from_team_value($team_a['label']);
        }
        $team_b_church = vaysf_extract_church_code_from_team_value($team_b['team_key']);
        if ($team_b_church === '') {
            $team_b_church = vaysf_extract_church_code_from_team_value($team_b['label']);
        }

        $data = array(
            'event' => $event,
            'stage' => 'Quarterfinal',
            'schedule_version' => $schedule_version,
            'team_a_key' => $team_a['team_key'],
            'team_a_label' => $team_a['label'],
            'team_a_church_code' => $team_a_church,
            'team_b_key' => $team_b['team_key'],
            'team_b_label' => $team_b['label'],
            'team_b_church_code' => $team_b_church,
            'team_c_key' => '',
            'team_c_label' => '',
            'team_c_church_code' => '',
            'team_ids_json' => $team_ids_json,
            'published_at' => current_time('mysql'),
            'updated_at' => current_time('mysql'),
        );

        if ($existing) {
            $format = array_map(function ($field) use ($field_formats) {
                return $field_formats[$field] ?? '%s';
            }, array_keys($data));
            $updated = $wpdb->update(
                $table_schedules,
                $data,
                array(
                    'schedule_id' => absint($existing['schedule_id']),
                    'schedule_version' => $schedule_version,
                ),
                $format,
                array('%d', '%d')
            );
            if (false === $updated) {
                $wpdb->query('ROLLBACK');
                return new WP_Error('vaysf_team_qf_apply_db_error', sprintf(__('Failed to update schedule row %s.', 'vaysf'), $game_key));
            }
            $results[] = array('game_key' => $game_key, 'action' => 'updated', 'schedule_id' => absint($existing['schedule_id']));
        } else {
            $data['game_key'] = $game_key;
            $data['game_status'] = 'scheduled';
            $data['created_at'] = current_time('mysql');
            $format = array_map(function ($field) use ($field_formats) {
                return $field_formats[$field] ?? '%s';
            }, array_keys($data));
            $inserted = $wpdb->insert($table_schedules, $data, $format);
            if (false === $inserted) {
                $wpdb->query('ROLLBACK');
                return new WP_Error('vaysf_team_qf_apply_db_error', sprintf(__('Failed to create schedule row %s.', 'vaysf'), $game_key));
            }
            $results[] = array('game_key' => $game_key, 'action' => 'created', 'schedule_id' => absint($wpdb->insert_id));
        }
    }

    $prewired = vaysf_prewire_team_playoff_bracket_rows($event, $schedule_version, $prefix);
    if (is_wp_error($prewired)) {
        $wpdb->query('ROLLBACK');
        return $prewired;
    }
    foreach ($prewired as $row) {
        $results[] = $row;
    }

    $wpdb->query('COMMIT');

    return $results;
}

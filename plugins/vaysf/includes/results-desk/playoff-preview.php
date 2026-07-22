<?php
/**
 * File: includes/results-desk/playoff-preview.php
 * Description: Bible Challenge and team playoff preview builders.
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

/**
 * Check whether the Results Desk has a playoff-preview path for an event.
 *
 * @param string $event Schedule event name
 * @return bool
 */
function vaysf_results_desk_can_preview_playoff_event($event) {
    $event = trim((string) $event);
    if ($event === '') {
        return false;
    }

    return vaysf_results_desk_is_bible_challenge_event($event)
        || vaysf_results_desk_is_team_qf_assignment_event($event)
        || stripos($event, 'Soccer') !== false;
}

/**
 * Fetch confirmed pool review snapshots for an event.
 *
 * @param string $event Schedule event name
 * @param int $schedule_version Published schedule version
 * @return array<int,array<string,mixed>>
 */
function vaysf_results_desk_get_confirmed_pool_reviews($event, $schedule_version) {
    global $wpdb;

    $event = sanitize_text_field($event);
    $schedule_version = absint($schedule_version);
    if ($event === '' || !$schedule_version) {
        return array();
    }

    $table = vaysf_get_table_name('pool_advancement');
    $rows = $wpdb->get_results(
        $wpdb->prepare(
            "SELECT * FROM $table WHERE schedule_version = %d AND event = %s ORDER BY pool_id",
            $schedule_version,
            $event
        ),
        ARRAY_A
    );
    if (!is_array($rows)) {
        return array();
    }

    $reviews = array();
    foreach ($rows as $row) {
        $snapshot = json_decode((string) ($row['standings_snapshot_json'] ?? ''), true);
        if (!is_array($snapshot)) {
            $snapshot = array();
        }

        $pool_id = (string) ($row['pool_id'] ?? '');
        $reviews[] = array(
            'pool_id' => $pool_id,
            'confirmed_by_user_id' => absint($row['confirmed_by_user_id'] ?? 0),
            'confirmed_at' => (string) ($row['confirmed_at'] ?? ''),
            'review_note' => (string) ($row['review_note'] ?? ''),
            'standings' => $snapshot,
            'stale' => vaysf_pool_advancement_is_stale($event, $pool_id, $schedule_version),
        );
    }

    return $reviews;
}

/**
 * Fetch current playoff-ish schedule rows for an event, for the two
 * operator-facing Results Desk contexts (the Playoff/QF Preview panel and
 * the Apply handlers) — never the public schedule display, which has its
 * own query and must keep requiring `published_at IS NOT NULL`.
 *
 * Deliberately does NOT filter on `published_at`: an admin-created QF/Semi
 * row (via the Schedules editor) starts with `published_at` NULL — the
 * editor never sets it, only `publish-schedule` or an Apply handler does —
 * so requiring it here would make a freshly-created row invisible to the
 * very preview/Apply flow meant to publish it. The BC and team-QF Apply
 * handlers both stamp `published_at` on every write, so a row found here
 * unpublished becomes published the first time an operator applies to it.
 *
 * @param string $event Schedule event name
 * @param int $schedule_version Published schedule version
 * @return array<string,array<string,mixed>> Rows keyed by game_key
 */
function vaysf_results_desk_get_playoff_schedule_rows($event, $schedule_version) {
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
            "SELECT s.*, r.result_id, r.public_status, r.score_json, r.winner_keys_json
                FROM $table_schedules s
                LEFT JOIN $table_results r ON r.schedule_id = s.schedule_id
                WHERE s.schedule_version = %d
                  AND s.event = %s
                  AND COALESCE(s.game_status, '') <> 'cancelled'
                  AND LOWER(COALESCE(s.stage, '')) NOT IN ('pool', 'prelim', 'preliminary')
                ORDER BY s.scheduled_time IS NULL, s.scheduled_time, s.game_key",
            $schedule_version,
            $event
        ),
        ARRAY_A
    );
    if (!is_array($rows)) {
        return array();
    }

    $by_key = array();
    foreach ($rows as $row) {
        $game_key = (string) ($row['game_key'] ?? '');
        if ($game_key !== '') {
            $by_key[$game_key] = $row;
        }
    }

    return $by_key;
}

/**
 * Return a display label for one ranking/team snapshot row.
 *
 * @param array<string,mixed> $team Ranking row
 * @return string
 */
function vaysf_results_desk_preview_team_label($team) {
    $label = trim((string) ($team['label'] ?? ''));
    if ($label !== '') {
        return $label;
    }

    $key = trim((string) ($team['team_key'] ?? ''));
    return $key !== '' ? $key : __('TBD', 'vaysf');
}

/**
 * Return the Bible Challenge snake bracket shape parked for 2027 RFC #328.
 *
 * This remains documented in code so coordinators can revisit the balanced
 * option after Sports Fest, but it is not the 2026 live default.
 *
 * @return array<string,array<int,int>>
 */
function vaysf_results_desk_bible_challenge_snake_rfc_2027() {
    return array(
        'BC-Semi-1' => array(0, 5, 6),
        'BC-Semi-2' => array(1, 4, 7),
        'BC-Semi-3' => array(2, 3, 8),
    );
}

/**
 * Return the 2026 Bible Challenge semifinal default: maximum top-seed
 * protection, matching the coordinator artifact:
 *   Semi #1: seeds 4, 3, 5
 *   Semi #2: seeds 6, 2, 7
 *   Semi #3: seeds 8, 1, 9
 *
 * @return array<string,array<int,int>>
 */
function vaysf_results_desk_bible_challenge_seed_protection_groups() {
    return array(
        'BC-Semi-1' => array(3, 2, 4),
        'BC-Semi-2' => array(5, 1, 6),
        'BC-Semi-3' => array(7, 0, 8),
    );
}

/**
 * Resolve the confirmed Bible Challenge Top 9, keyed by team_key in seed
 * order (position 0 = seed 1). Shared by the preview builder and the Apply
 * handler so both always agree on which teams are actually eligible.
 *
 * @param array<int,array<string,mixed>> $reviews Confirmed pool reviews
 * @return array{0:array<string,array<string,mixed>>,1:array<int,string>} [teams_by_key, warnings]
 */
function vaysf_results_desk_get_bible_challenge_confirmed_teams($reviews) {
    $warnings = array();
    $source_review = null;
    foreach ($reviews as $review) {
        if ($source_review === null || empty($review['stale'])) {
            $source_review = $review;
        }
        if (empty($review['stale'])) {
            break;
        }
    }

    $top_teams = array();
    if ($source_review && !empty($source_review['standings']) && is_array($source_review['standings'])) {
        foreach ($source_review['standings'] as $team) {
            if (!is_array($team)) {
                continue;
            }
            if (!empty($team['advances'])) {
                $top_teams[] = $team;
            }
        }
        if (count($top_teams) < 9) {
            $top_teams = array_slice($source_review['standings'], 0, 9);
        }
    }

    if (!$source_review) {
        $warnings[] = __('Bible Challenge Top 9 has not been confirmed yet.', 'vaysf');
    } elseif (!empty($source_review['stale'])) {
        $warnings[] = __('The saved Bible Challenge Top 9 is stale; re-confirm before using this preview.', 'vaysf');
    }
    if (count($top_teams) < 9) {
        $warnings[] = __('Fewer than 9 confirmed advancing teams are available, so semifinal labels are incomplete.', 'vaysf');
    }

    $teams_by_key = array();
    foreach (array_slice($top_teams, 0, 9) as $position => $team) {
        $key = trim((string) ($team['team_key'] ?? ''));
        if ($key === '' || isset($teams_by_key[$key])) {
            continue;
        }
        $teams_by_key[$key] = array(
            'team_key' => $key,
            'label' => vaysf_results_desk_preview_team_label($team),
            'seed' => $position + 1,
        );
    }

    return array($teams_by_key, $warnings);
}

/**
 * Build Bible Challenge semifinal preview rows from confirmed Top 9,
 * honoring an optional operator-chosen `bc_seed` arrangement passed via GET
 * (session-only; never persisted). Falls back to the 2026 top-seed-protection
 * seeding
 * whenever the override is missing, incomplete, or not a valid permutation
 * of the confirmed nine.
 *
 * @param array<int,array<string,mixed>> $reviews Confirmed pool reviews
 * @param array<string,array<string,mixed>> $schedule_rows Existing playoff rows
 * @return array<string,mixed>
 */
function vaysf_results_desk_build_bible_challenge_preview($reviews, $schedule_rows) {
    list($teams_by_key, $warnings) = vaysf_results_desk_get_bible_challenge_confirmed_teams($reviews);
    $seed_groups = vaysf_results_desk_bible_challenge_seed_protection_groups();
    $can_customize = count($teams_by_key) === 9;
    $seed_order_keys = array_keys($teams_by_key);

    $default_arrangement = array();
    foreach ($seed_groups as $game_key => $positions) {
        $team_keys = array();
        foreach ($positions as $position) {
            $team_keys[] = $seed_order_keys[$position] ?? '';
        }
        $default_arrangement[$game_key] = $team_keys;
    }

    $arrangement = $default_arrangement;
    $custom_active = false;

    if ($can_customize && isset($_GET['bc_seed']) && is_array($_GET['bc_seed'])) {
        $submitted = wp_unslash($_GET['bc_seed']);
        $candidate = array();
        $seen = array();
        $valid = true;
        foreach (array_keys($seed_groups) as $game_key) {
            $picks = isset($submitted[$game_key]) && is_array($submitted[$game_key])
                ? array_map('sanitize_text_field', $submitted[$game_key])
                : array();
            if (count($picks) !== 3) {
                $valid = false;
                break;
            }
            foreach ($picks as $pick) {
                if ($pick === '' || !isset($teams_by_key[$pick]) || isset($seen[$pick])) {
                    $valid = false;
                    break 2;
                }
                $seen[$pick] = true;
            }
            $candidate[$game_key] = $picks;
        }
        if ($valid && count($seen) === 9) {
            $arrangement = $candidate;
            $custom_active = true;
        } else {
            $warnings[] = __('The custom semifinal arrangement in the link was incomplete or invalid, so the top-seed-protection default is shown instead.', 'vaysf');
        }
    }

    $rows = array();
    foreach ($arrangement as $game_key => $team_keys) {
        $teams = array();
        foreach ($team_keys as $team_key) {
            $team = $teams_by_key[$team_key] ?? null;
            $teams[] = array(
                'seed' => $team['seed'] ?? null,
                'label' => $team ? $team['label'] : sprintf(__('Seed TBD (%s)', 'vaysf'), $team_key),
                'team_key' => $team_key,
            );
        }
        $rows[] = array(
            'game_key' => $game_key,
            'stage' => __('Semifinal', 'vaysf'),
            'suggestion' => $teams,
            'schedule_row' => $schedule_rows[$game_key] ?? null,
            'note' => $custom_active
                ? __('Custom arrangement (this browser only); verify before applying.', 'vaysf')
                : __('Top-seed-protection preview from confirmed Top 9; verify before applying.', 'vaysf'),
        );
    }

    $rows[] = array(
        'game_key' => 'BC-Final',
        'stage' => __('Final', 'vaysf'),
        'suggestion' => array(
            array('seed' => null, 'label' => __('Winner of BC-Semi-1', 'vaysf'), 'team_key' => 'WIN-BC-Semi-1'),
            array('seed' => null, 'label' => __('Winner of BC-Semi-2', 'vaysf'), 'team_key' => 'WIN-BC-Semi-2'),
            array('seed' => null, 'label' => __('Winner of BC-Semi-3', 'vaysf'), 'team_key' => 'WIN-BC-Semi-3'),
        ),
        'schedule_row' => $schedule_rows['BC-Final'] ?? null,
        'note' => __('Final stays as winner placeholders until semifinal results are reported.', 'vaysf'),
    );

    return array(
        'mode' => 'bible_challenge',
        'reviews' => $reviews,
        'warnings' => $warnings,
        'rows' => $rows,
        'teams_by_key' => $teams_by_key,
        'arrangement' => $arrangement,
        'can_customize' => $can_customize,
        'custom_active' => $custom_active,
    );
}

/**
 * Build the Basketball/Volleyball QF/Semifinal/Final/3rd-Place preview,
 * always showing the full fixed 8-row bracket template once QF seeding is
 * confirmed — regardless of whether those schedule rows exist yet — the
 * same "preview from a known template, not from row discovery" pattern as
 * vaysf_results_desk_build_bible_challenge_preview() (Issue #329). Supports
 * an optional operator-chosen browser-local QF-1..4 assignment from GET
 * (`qf_seed[<game_key>][]`).
 *
 * @param string $event Schedule event name
 * @param array<int,array<string,mixed>> $reviews Confirmed pool reviews
 * @param array<string,array<string,mixed>> $schedule_rows Existing playoff rows
 * @return array<string,mixed>
 */
function vaysf_results_desk_build_team_qf_preview($event, $reviews, $schedule_rows) {
    list($teams_by_key, $warnings, $has_stale_review) = vaysf_results_desk_get_team_qf_candidate_teams($reviews);
    $prefix = vaysf_results_desk_team_qf_event_prefix($event);
    if ($prefix === '') {
        $warnings[] = __('This event has no configured QF game-key prefix.', 'vaysf');
    }

    $can_customize = $prefix !== '' && !$has_stale_review && count($teams_by_key) === 8;
    $arrangement = $can_customize
        ? vaysf_results_desk_default_team_qf_arrangement($prefix, $teams_by_key)
        : array();
    $custom_active = false;

    if ($can_customize && isset($_GET['qf_seed']) && is_array($_GET['qf_seed'])) {
        $submitted = wp_unslash($_GET['qf_seed']);
        $candidate = vaysf_results_desk_validate_team_qf_arrangement($submitted, $prefix, $teams_by_key);
        if (is_wp_error($candidate)) {
            $warnings[] = $candidate->get_error_message();
        } else {
            $arrangement = $candidate;
            $custom_active = true;
        }
    }

    $rows = array();
    foreach ($arrangement as $game_key => $team_keys) {
        $suggestions = array();
        foreach ($team_keys as $team_key) {
            $team = $teams_by_key[$team_key] ?? null;
            $suggestions[] = array(
                'seed' => $team['seed'] ?? null,
                'label' => $team ? vaysf_results_desk_team_qf_option_label($team) : __('TBD', 'vaysf'),
                'team_key' => $team_key,
            );
        }
        $rows[] = array(
            'game_key' => $game_key,
            'stage' => __('Quarterfinal', 'vaysf'),
            'suggestion' => $suggestions,
            'schedule_row' => $schedule_rows[$game_key] ?? null,
            'note' => $custom_active
                ? __('Custom QF assignment (this browser only); verify before applying.', 'vaysf')
                : __('Default QF assignment from confirmed seeding (1v8, 4v5, 3v6, 2v7); adjust before applying.', 'vaysf'),
        );
    }

    if ($prefix !== '') {
        $downstream = array(
            array(
                'game_key' => $prefix . '-Semi-1',
                'stage' => __('Semifinal', 'vaysf'),
                'suggestion' => array(
                    array('seed' => null, 'label' => sprintf(__('Winner of %s', 'vaysf'), $prefix . '-QF-1'), 'team_key' => ''),
                    array('seed' => null, 'label' => sprintf(__('Winner of %s', 'vaysf'), $prefix . '-QF-2'), 'team_key' => ''),
                ),
                'note' => __('Later playoff rows stay as winner placeholders until QF results are reported.', 'vaysf'),
            ),
            array(
                'game_key' => $prefix . '-Semi-2',
                'stage' => __('Semifinal', 'vaysf'),
                'suggestion' => array(
                    array('seed' => null, 'label' => sprintf(__('Winner of %s', 'vaysf'), $prefix . '-QF-3'), 'team_key' => ''),
                    array('seed' => null, 'label' => sprintf(__('Winner of %s', 'vaysf'), $prefix . '-QF-4'), 'team_key' => ''),
                ),
                'note' => __('Later playoff rows stay as winner placeholders until QF results are reported.', 'vaysf'),
            ),
            array(
                'game_key' => $prefix . '-Final',
                'stage' => __('Final', 'vaysf'),
                'suggestion' => array(
                    array('seed' => null, 'label' => sprintf(__('Winner of %s', 'vaysf'), $prefix . '-Semi-1'), 'team_key' => ''),
                    array('seed' => null, 'label' => sprintf(__('Winner of %s', 'vaysf'), $prefix . '-Semi-2'), 'team_key' => ''),
                ),
                'note' => __('Final stays as winner placeholders until semifinal results are reported.', 'vaysf'),
            ),
            array(
                'game_key' => $prefix . '-3rd-Place',
                'stage' => __('3rd Place', 'vaysf'),
                'suggestion' => array(
                    array('seed' => null, 'label' => sprintf(__('Loser of %s', 'vaysf'), $prefix . '-Semi-1'), 'team_key' => ''),
                    array('seed' => null, 'label' => sprintf(__('Loser of %s', 'vaysf'), $prefix . '-Semi-2'), 'team_key' => ''),
                ),
                'note' => __('3rd-place match stays as loser placeholders until semifinal results are reported.', 'vaysf'),
            ),
        );
        foreach ($downstream as $row) {
            $row['schedule_row'] = $schedule_rows[$row['game_key']] ?? null;
            $rows[] = $row;
        }
    }

    return array(
        'mode' => 'team_qf',
        'reviews' => $reviews,
        'warnings' => array_values(array_unique($warnings)),
        'rows' => $rows,
        'teams_by_key' => $teams_by_key,
        'prefix' => $prefix,
        'arrangement' => $arrangement,
        'can_customize' => $can_customize,
        'custom_active' => $custom_active,
    );
}

/**
 * Build the event-level playoff preview model for the Results Desk.
 *
 * @param array<string,mixed> $filters Results Desk filters
 * @return array<string,mixed>
 */
function vaysf_get_results_desk_playoff_preview($filters = array()) {
    $filters = vaysf_sanitize_results_desk_filters($filters);
    $event = trim((string) ($filters['event'] ?? ''));
    $schedule_version = vaysf_get_current_published_schedule_version();
    if ($schedule_version === null) {
        return array('status' => 'no_schedule');
    }
    if ($event === '') {
        return array('status' => 'select_event', 'schedule_version' => absint($schedule_version));
    }
    if (!vaysf_results_desk_can_preview_playoff_event($event)) {
        return array(
            'status' => 'unsupported',
            'event' => $event,
            'schedule_version' => absint($schedule_version),
        );
    }

    $reviews = vaysf_results_desk_get_confirmed_pool_reviews($event, $schedule_version);
    $schedule_rows = vaysf_results_desk_get_playoff_schedule_rows($event, $schedule_version);
    if (vaysf_results_desk_is_bible_challenge_event($event)) {
        $preview = vaysf_results_desk_build_bible_challenge_preview($reviews, $schedule_rows);
    } elseif (vaysf_results_desk_is_team_qf_assignment_event($event)) {
        $preview = vaysf_results_desk_build_team_qf_preview($event, $reviews, $schedule_rows);
    } else {
        $preview_rows = array();
        foreach ($schedule_rows as $game_key => $schedule_row) {
            $preview_rows[] = array(
                'game_key' => $game_key,
                'stage' => (string) ($schedule_row['stage'] ?? ''),
                'suggestion' => array(),
                'schedule_row' => $schedule_row,
                'note' => __('Matchup suggestion blocked until wildcard/seed rules are explicit.', 'vaysf'),
            );
        }
        $preview = array(
            'mode' => 'team_sport',
            'reviews' => $reviews,
            'warnings' => array(__('Team-sport QF/Semifinal labels are preview-only until wildcard and seed rules are confirmed.', 'vaysf')),
            'rows' => $preview_rows,
        );
    }

    $preview['status'] = 'ok';
    $preview['event'] = $event;
    $preview['schedule_version'] = absint($schedule_version);
    return $preview;
}

 * Write a chosen Bible Challenge semifinal matchup directly into the
 * BC-Semi-1/2/3 schedule rows for the given event/schedule_version.
 *
 * Re-validates the submitted arrangement against the server's own confirmed
 * Top 9 (never trusts client-supplied team labels) and mirrors the hardened
 * BB/VB apply guard: rows already reported, official, under_review, or with
 * an existing score payload are left untouched rather than overwritten.
 *
 * This deliberately bypasses the "publish-schedule is the only writer to
 * WordPress schedule rows" convention documented in docs/SCHEDULING.md, at
 * explicit operator request. Rows it creates or updates are left in
 * `game_status = 'scheduled'`, i.e. NOT protected — a later schedule publish
 * that targets the same game_keys can still silently overwrite what this
 * writes.
 *
 * @param string $event
 * @param int $schedule_version
 * @param array<string,array<int,string>> $arrangement game_key => 3 team_keys
 * @return array<int,array<string,mixed>>|WP_Error Per-row outcomes on success
 */
function vaysf_apply_bible_challenge_playoff_preview($event, $schedule_version, $arrangement) {
    global $wpdb;

    $event = sanitize_text_field($event);
    $schedule_version = absint($schedule_version);
    if ($event === '' || !$schedule_version) {
        return new WP_Error('vaysf_bc_apply_missing_context', __('Missing event or schedule version.', 'vaysf'));
    }
    if (!vaysf_results_desk_is_bible_challenge_event($event)) {
        return new WP_Error('vaysf_bc_apply_wrong_event', __('This action only applies to the Bible Challenge event.', 'vaysf'));
    }

    $reviews = vaysf_results_desk_get_confirmed_pool_reviews($event, $schedule_version);
    list($teams_by_key, ) = vaysf_results_desk_get_bible_challenge_confirmed_teams($reviews);
    if (count($teams_by_key) !== 9) {
        return new WP_Error('vaysf_bc_apply_incomplete', __('The confirmed Bible Challenge Top 9 is not currently complete; nothing was applied.', 'vaysf'));
    }

    $seed_groups = vaysf_results_desk_bible_challenge_seed_protection_groups();
    $seen = array();
    foreach (array_keys($seed_groups) as $game_key) {
        $picks = isset($arrangement[$game_key]) && is_array($arrangement[$game_key]) ? $arrangement[$game_key] : array();
        if (count($picks) !== 3) {
            return new WP_Error('vaysf_bc_apply_invalid', __('The submitted matchup is missing a team for one of the semifinals.', 'vaysf'));
        }
        foreach ($picks as $pick) {
            if (!isset($teams_by_key[$pick]) || isset($seen[$pick])) {
                return new WP_Error('vaysf_bc_apply_invalid', __('The submitted matchup does not match the currently confirmed Top 9 teams.', 'vaysf'));
            }
            $seen[$pick] = true;
        }
    }
    if (count($seen) !== 9) {
        return new WP_Error('vaysf_bc_apply_invalid', __('The submitted matchup does not use all nine confirmed teams exactly once.', 'vaysf'));
    }

    $table_schedules = vaysf_get_table_name('schedules');
    $field_formats = array(
        'event' => '%s', 'stage' => '%s', 'schedule_version' => '%d',
        'team_a_key' => '%s', 'team_a_label' => '%s', 'team_a_church_code' => '%s',
        'team_b_key' => '%s', 'team_b_label' => '%s', 'team_b_church_code' => '%s',
        'team_c_key' => '%s', 'team_c_label' => '%s', 'team_c_church_code' => '%s',
        'team_ids_json' => '%s',
        'published_at' => '%s', 'updated_at' => '%s',
        'game_key' => '%s', 'game_status' => '%s', 'created_at' => '%s',
    );
    $results = array();

    foreach ($seed_groups as $game_key => $positions) {
        $picks = $arrangement[$game_key];
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
                    "SELECT schedule_id, schedule_version, game_status FROM $table_schedules WHERE game_key = %s LIMIT 1",
                    $game_key
                ),
                ARRAY_A
            );
            if ($other_version) {
                return new WP_Error(
                    'vaysf_bc_apply_schedule_version_mismatch',
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

        $team_a = $teams_by_key[$picks[0]];
        $team_b = $teams_by_key[$picks[1]];
        $team_c = $teams_by_key[$picks[2]];
        $team_ids_json = wp_json_encode(array($team_a['team_key'], $team_b['team_key'], $team_c['team_key']));
        if ($team_ids_json === false) {
            return new WP_Error('vaysf_bc_apply_json_error', __('Could not encode Bible Challenge semifinal team ids.', 'vaysf'));
        }

        $data = array(
            'event' => $event,
            'stage' => 'Semifinal',
            'schedule_version' => $schedule_version,
            'team_a_key' => $team_a['team_key'],
            'team_a_label' => $team_a['label'],
            'team_a_church_code' => vaysf_extract_church_code_from_team_value($team_a['team_key']) ?: vaysf_extract_church_code_from_team_value($team_a['label']),
            'team_b_key' => $team_b['team_key'],
            'team_b_label' => $team_b['label'],
            'team_b_church_code' => vaysf_extract_church_code_from_team_value($team_b['team_key']) ?: vaysf_extract_church_code_from_team_value($team_b['label']),
            'team_c_key' => $team_c['team_key'],
            'team_c_label' => $team_c['label'],
            'team_c_church_code' => vaysf_extract_church_code_from_team_value($team_c['team_key']) ?: vaysf_extract_church_code_from_team_value($team_c['label']),
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
                return new WP_Error('vaysf_bc_apply_db_error', sprintf(__('Failed to update schedule row %s.', 'vaysf'), $game_key));
            }
            $results[] = array('game_key' => $game_key, 'action' => 'updated', 'schedule_id' => (int) $existing['schedule_id']);
        } else {
            $data['game_key'] = $game_key;
            $data['game_status'] = 'scheduled';
            $data['created_at'] = current_time('mysql');
            $format = array_map(function ($field) use ($field_formats) {
                return $field_formats[$field] ?? '%s';
            }, array_keys($data));
            $inserted = $wpdb->insert($table_schedules, $data, $format);
            if (false === $inserted) {
                return new WP_Error('vaysf_bc_apply_db_error', sprintf(__('Failed to create schedule row %s.', 'vaysf'), $game_key));
            }
            $results[] = array('game_key' => $game_key, 'action' => 'created', 'schedule_id' => (int) $wpdb->insert_id);
        }
    }

    $final = vaysf_prewire_team_playoff_row(
        $event,
        $schedule_version,
        'BC-Final',
        'Final',
        'WIN-BC-Semi-1',
        'Winner of BC-Semi-1',
        'WIN-BC-Semi-2',
        'Winner of BC-Semi-2',
        'WIN-BC-Semi-3',
        'Winner of BC-Semi-3'
    );
    if (is_wp_error($final)) {
        return $final;
    }
    $results[] = $final;

    return $results;
}


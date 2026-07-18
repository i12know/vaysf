<?php
/**
 * File: includes/public-display.php
 * Description: Spectator-facing live schedule/results/advancement helpers (Issue #206)
 * Version: 1.0.0
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

if (!defined('VAYSF_UPCOMING_ONLY_LOOKBACK_MINUTES')) {
    /**
     * Grace period, in minutes, applied when a visitor checks the public
     * "Upcoming games only" filter checkbox, so a delayed/running-late game
     * doesn't vanish from the "upcoming" view the moment its scheduled start
     * time passes (#303).
     */
    define('VAYSF_UPCOMING_ONLY_LOOKBACK_MINUTES', 60);
}

/**
 * Sanitize a public schedule/venue filter value.
 *
 * @param mixed $value Raw filter value
 * @return string Sanitized value, or '' when absent
 */
function vaysf_sanitize_public_filter($value) {
    if ($value === null) {
        return '';
    }
    return sanitize_text_field(wp_unslash($value));
}

/**
 * Sanitize a public day filter to a YYYY-MM-DD string.
 *
 * @param mixed $value Raw filter value
 * @return string Sanitized date, or '' when absent/invalid
 */
function vaysf_sanitize_public_day_filter($value) {
    $value = vaysf_sanitize_public_filter($value);
    if ($value === '' || !preg_match('/^\d{4}-\d{2}-\d{2}$/', $value)) {
        return '';
    }
    return $value;
}

/**
 * Sanitize a church code supplied by a shortcode or public API request.
 *
 * Church codes are stored in their canonical uppercase form at publication
 * time. Keeping that identity in dedicated schedule columns avoids relying on
 * opaque team keys or spectator-facing labels for church filtering.
 *
 * @param mixed $value Raw church code
 * @return string Uppercase church code, or '' when absent
 */
function vaysf_sanitize_public_church_filter($value) {
    return strtoupper(vaysf_sanitize_public_filter($value));
}

/**
 * Sanitize the "upcoming games only" checkbox submitted by the public filter form.
 *
 * The checkbox posts '1' when checked; any other value (including absence)
 * means unchecked.
 *
 * @param mixed $value Raw checkbox value
 * @return bool True when the checkbox was checked
 */
function vaysf_sanitize_public_upcoming_filter($value) {
    return vaysf_sanitize_public_filter($value) === '1';
}

/**
 * Sanitize an optional rolling schedule lookback in whole minutes.
 *
 * @param mixed $value Raw minute count
 * @return int|null Null when the parameter is omitted or invalid
 */
function vaysf_sanitize_public_lookback_minutes($value) {
    if ($value === null || $value === '') {
        return null;
    }

    if (!is_scalar($value)) {
        return null;
    }

    $value = trim((string) $value);
    if (!preg_match('/^\d+$/', $value)) {
        return null;
    }

    return (int) $value;
}

/**
 * Distinct scheduled dates (Y-m-d) from the currently published, non-cancelled schedule.
 *
 * @param int|null $schedule_version Optional version; defaults to current published version
 * @return array<int,string> Sorted distinct dates
 */
function vaysf_get_public_schedule_days($schedule_version = null) {
    global $wpdb;

    if ($schedule_version === null) {
        $schedule_version = vaysf_get_current_published_schedule_version();
    }
    if ($schedule_version === null) {
        return array();
    }

    $table_schedules = vaysf_get_table_name('schedules');
    $rows = $wpdb->get_results(
        $wpdb->prepare(
            "SELECT scheduled_time, scheduled_slot
            FROM $table_schedules
            WHERE schedule_version = %d
                AND published_at IS NOT NULL
                AND COALESCE(game_status, '') <> 'cancelled'",
            absint($schedule_version)
        ),
        ARRAY_A
    );
    if (!is_array($rows)) {
        return array();
    }

    $days = array();
    foreach ($rows as $row) {
        $competition_at = vaysf_get_schedule_competition_datetime($row);
        if ($competition_at instanceof DateTimeImmutable) {
            $days[$competition_at->format('Y-m-d')] = $competition_at->format('Y-m-d');
        }
    }

    sort($days, SORT_STRING);
    return array_values($days);
}

/**
 * Distinct venues/locations from the currently published, non-cancelled schedule.
 *
 * @param int|null $schedule_version Optional version; defaults to current published version
 * @return array<int,string> Sorted distinct venue labels
 */
function vaysf_get_public_schedule_venues($schedule_version = null) {
    global $wpdb;

    if ($schedule_version === null) {
        $schedule_version = vaysf_get_current_published_schedule_version();
    }
    if ($schedule_version === null) {
        return array();
    }

    $table_schedules = vaysf_get_table_name('schedules');
    $venues = $wpdb->get_col(
        $wpdb->prepare(
            "SELECT DISTINCT scheduled_location
            FROM $table_schedules
            WHERE schedule_version = %d
                AND scheduled_location IS NOT NULL
                AND scheduled_location <> ''
                AND published_at IS NOT NULL
                AND COALESCE(game_status, '') <> 'cancelled'
            ORDER BY scheduled_location",
            absint($schedule_version)
        )
    );

    return is_array($venues) ? array_values(array_filter(array_map('strval', $venues))) : array();
}

/**
 * Resolve one schedule-row team slot ('a', 'b', or 'c') to a church code,
 * falling back to the team key/label when the dedicated team_*_church_code
 * column is still empty (e.g. a schedule published before that column was
 * backfilled). Mirrors vaysf_schedule_church_signature()'s per-slot rule so
 * the public church filter/dropdown and the result-matching fallback in
 * score-entry.php stay consistent.
 *
 * @param array<string,mixed> $row Schedule row (or subset with team_* fields)
 * @param string $slot One of 'a', 'b', 'c'
 * @return string Church code, or '' when none could be resolved
 */
function vaysf_resolve_row_slot_church_code($row, $slot) {
    foreach (array("team_{$slot}_church_code", "team_{$slot}_key", "team_{$slot}_label") as $field) {
        if (!empty($row[$field])) {
            $church = vaysf_extract_church_code_from_team_value($row[$field]);
            if ($church !== '') {
                return $church;
            }
        }
    }

    return '';
}

/**
 * Check whether a schedule row's team_a/b/c slots include the given church code.
 *
 * @param array<string,mixed> $row Schedule row
 * @param string $church Uppercase church code to match
 * @return bool
 */
function vaysf_schedule_church_signature_contains($row, $church) {
    foreach (array('a', 'b', 'c') as $slot) {
        if (vaysf_resolve_row_slot_church_code($row, $slot) === $church) {
            return true;
        }
    }

    return false;
}

/**
 * Distinct church codes from the currently published, non-cancelled schedule.
 *
 * @param int|null $schedule_version Optional version; defaults to current published version
 * @return array<int,string> Sorted distinct church codes
 */
function vaysf_get_public_schedule_churches($schedule_version = null) {
    global $wpdb;

    if ($schedule_version === null) {
        $schedule_version = vaysf_get_current_published_schedule_version();
    }
    if ($schedule_version === null) {
        return array();
    }

    $table_schedules = vaysf_get_table_name('schedules');
    $rows = $wpdb->get_results(
        $wpdb->prepare(
            "SELECT team_a_key, team_a_label, team_a_church_code,
                team_b_key, team_b_label, team_b_church_code,
                team_c_key, team_c_label, team_c_church_code
            FROM $table_schedules
            WHERE schedule_version = %d
                AND published_at IS NOT NULL
                AND COALESCE(game_status, '') <> 'cancelled'",
            absint($schedule_version)
        ),
        ARRAY_A
    );

    if (!is_array($rows)) {
        return array();
    }

    $churches = array();
    foreach ($rows as $row) {
        foreach (array('a', 'b', 'c') as $slot) {
            $church = vaysf_resolve_row_slot_church_code($row, $slot);
            if ($church !== '') {
                $churches[$church] = $church;
            }
        }
    }

    sort($churches, SORT_STRING);
    return array_values($churches);
}

/**
 * Reduce a decoded score_json payload to the public headline numbers only.
 *
 * Every score form type (simple_score, three_team_score, volleyball_set_score)
 * stores its final tally in team_a_score/team_b_score(/team_c_score), so no
 * per-type branching is needed here. Anything else in the payload (notes,
 * per-set detail, submitter context) stays private.
 *
 * @param array<string,mixed> $score_payload Decoded score_json
 * @return array<string,mixed> Public-safe score summary
 */
function vaysf_format_public_score_summary($score_payload) {
    $summary = array(
        'team_a_score' => isset($score_payload['team_a_score']) ? (int) $score_payload['team_a_score'] : null,
        'team_b_score' => isset($score_payload['team_b_score']) ? (int) $score_payload['team_b_score'] : null,
        'team_c_score' => isset($score_payload['team_c_score']) ? (int) $score_payload['team_c_score'] : null,
        'is_tie' => !empty($score_payload['is_tie']),
    );

    if ($summary['team_c_score'] === null) {
        unset($summary['team_c_score']);
    }

    return $summary;
}

/**
 * Public display should treat a completed score payload as reported even when
 * an older/manual result row still has the default pending public_status.
 *
 * @param string $public_status Raw sf_results.public_status value
 * @param string $score_json Raw sf_results.score_json value
 * @return string Spectator-facing result status
 */
function vaysf_normalize_public_result_status($public_status, $score_json) {
    $public_status = trim((string) $public_status);
    if (($public_status === '' || $public_status === 'pending') && trim((string) $score_json) !== '') {
        return 'reported';
    }

    return $public_status;
}

/**
 * Shape one joined schedule+result row for public consumption.
 *
 * Excludes scoresheet file paths, coordinator/submitter identities, internal
 * notes, revision history, and dispute detail per the event-day results RFC
 * (docs/EVENT_DAY_RESULTS_WORKFLOW_RFC.md §14).
 *
 * @param array<string,mixed> $row Joined sf_schedules + sf_results row
 * @return array<string,mixed> Public-safe row
 */
function vaysf_format_public_schedule_row($row) {
    $score_json = isset($row['score_json']) ? (string) $row['score_json'] : '';
    $public_status = vaysf_normalize_public_result_status($row['public_status'] ?? '', $score_json);
    $score = null;

    if (in_array($public_status, array('reported', 'official', 'under_review'), true) && $score_json !== '') {
        $decoded = json_decode($score_json, true);
        if (is_array($decoded)) {
            $score = vaysf_format_public_score_summary($decoded);
        }
    }

    return array(
        'game_key' => isset($row['game_key']) ? (string) $row['game_key'] : '',
        'event' => isset($row['event']) ? (string) $row['event'] : '',
        'stage' => isset($row['stage']) ? (string) $row['stage'] : '',
        'pool_id' => isset($row['pool_id']) ? (string) $row['pool_id'] : '',
        'round_number' => isset($row['round_number']) ? (int) $row['round_number'] : null,
        'sub_event' => isset($row['sub_event']) ? (string) $row['sub_event'] : '',
        'team_a_label' => isset($row['team_a_label']) ? (string) $row['team_a_label'] : '',
        'team_b_label' => isset($row['team_b_label']) ? (string) $row['team_b_label'] : '',
        'team_c_label' => isset($row['team_c_label']) ? (string) $row['team_c_label'] : '',
        'scheduled_time' => isset($row['scheduled_time']) ? (string) $row['scheduled_time'] : '',
        'scheduled_slot' => isset($row['scheduled_slot']) ? (string) $row['scheduled_slot'] : '',
        'display_time' => vaysf_format_schedule_display_time($row['scheduled_time'] ?? '', $row['scheduled_slot'] ?? '', 'D g:i A'),
        'resource_id' => isset($row['resource_id']) ? (string) $row['resource_id'] : '',
        'scheduled_location' => vaysf_format_schedule_display_location($row['scheduled_location'] ?? '', $row['resource_id'] ?? ''),
        'game_status' => isset($row['game_status']) ? (string) $row['game_status'] : 'scheduled',
        'public_status' => $public_status,
        'score' => $score,
        'updated_at' => isset($row['updated_at']) ? (string) $row['updated_at'] : '',
    );
}

/**
 * Load the newest known result row for each requested game_key, regardless of
 * which historical schedule_id version it was attached to.
 *
 * This preserves live/public result status when a schedule is republished and
 * the current public schedule row no longer has the old schedule_id that the
 * score submission originally referenced.
 *
 * @param array<int,string> $game_keys Stable schedule game keys
 * @return array<string,array<string,mixed>> Latest result row keyed by game_key
 */
function vaysf_get_latest_results_by_game_key($game_keys) {
    global $wpdb;

    $game_keys = array_values(array_unique(array_filter(array_map('strval', (array) $game_keys))));
    if (empty($game_keys)) {
        return array();
    }

    $table_schedules = vaysf_get_table_name('schedules');
    $table_results = vaysf_get_table_name('results');

    $placeholders = implode(', ', array_fill(0, count($game_keys), '%s'));
    $sql = "SELECT s_hist.game_key, r.result_id, r.score_json, r.public_status, r.updated_at
        FROM $table_results r
        INNER JOIN $table_schedules s_hist ON s_hist.schedule_id = r.schedule_id
        WHERE s_hist.game_key IN ($placeholders)
            AND NOT EXISTS (
                SELECT 1
                FROM $table_results newer_r
                INNER JOIN $table_schedules newer_s ON newer_s.schedule_id = newer_r.schedule_id
                WHERE newer_s.game_key = s_hist.game_key
                    AND (
                        newer_r.updated_at > r.updated_at
                        OR (newer_r.updated_at = r.updated_at AND newer_r.result_id > r.result_id)
                    )
            )";

    $rows = $wpdb->get_results($wpdb->prepare($sql, $game_keys), ARRAY_A);
    if (!is_array($rows)) {
        return array();
    }

    $results_by_key = array();
    foreach ($rows as $row) {
        $game_key = isset($row['game_key']) ? (string) $row['game_key'] : '';
        if ($game_key === '') {
            continue;
        }
        $results_by_key[$game_key] = $row;
    }

    return $results_by_key;
}

/**
 * Recover result rows that were saved against the wrong/historical schedule_id
 * by matching the exact team keys stored inside score_json.
 *
 * @param array<int,array<string,mixed>> $schedule_rows Public schedule rows missing direct results
 * @return array<string,array<string,mixed>> Latest result row keyed by game_key
 */
function vaysf_get_latest_results_by_team_keys($schedule_rows) {
    global $wpdb;

    $expected_by_game_key = array();
    foreach ((array) $schedule_rows as $row) {
        $game_key = isset($row['game_key']) ? (string) $row['game_key'] : '';
        if ($game_key === '') {
            continue;
        }

        $team_keys = array();
        foreach (array('team_a_key', 'team_b_key', 'team_c_key') as $field) {
            if (!empty($row[$field])) {
                $team_keys[] = (string) $row[$field];
            }
        }
        sort($team_keys);

        if (!empty($team_keys)) {
            $expected_by_game_key[$game_key] = $team_keys;
        }
    }

    if (empty($expected_by_game_key)) {
        return array();
    }

    $table_results = vaysf_get_table_name('results');
    $candidate_rows = $wpdb->get_results(
        "SELECT result_id, score_json, public_status, updated_at
        FROM $table_results
        WHERE score_json IS NOT NULL AND score_json <> ''
        ORDER BY updated_at DESC, result_id DESC
        LIMIT 500",
        ARRAY_A
    );
    if (!is_array($candidate_rows)) {
        return array();
    }

    $results_by_key = array();
    foreach ($candidate_rows as $candidate) {
        $decoded = json_decode($candidate['score_json'] ?? '', true);
        if (!is_array($decoded)) {
            continue;
        }

        $candidate_keys = array();
        foreach (array('team_a_key', 'team_b_key', 'team_c_key') as $field) {
            if (!empty($decoded[$field])) {
                $candidate_keys[] = (string) $decoded[$field];
            }
        }
        sort($candidate_keys);

        if (empty($candidate_keys)) {
            continue;
        }

        foreach ($expected_by_game_key as $game_key => $expected_keys) {
            if (isset($results_by_key[$game_key])) {
                continue;
            }
            if ($candidate_keys === $expected_keys) {
                $results_by_key[$game_key] = $candidate;
            }
        }
    }

    return $results_by_key;
}

/**
 * Fetch the currently published, non-cancelled schedule joined with its
 * current result, filtered for public display.
 *
 * @param array<string,mixed> $filters Optional 'event', 'day' (Y-m-d), 'venue',
 *                                     'church', 'lookback_minutes', and
 *                                     'upcoming_only' ('1' to enable; takes
 *                                     precedence over 'lookback_minutes')
 * @return array<int,array<string,mixed>> Public-safe schedule rows
 */
function vaysf_get_public_schedule_rows($filters = array()) {
    global $wpdb;

    $schedule_version = vaysf_get_current_published_schedule_version();
    if ($schedule_version === null) {
        return array();
    }

    $table_schedules = vaysf_get_table_name('schedules');
    $table_results = vaysf_get_table_name('results');

    $where = array(
        's.schedule_version = %d',
        's.published_at IS NOT NULL',
        "COALESCE(s.game_status, '') <> 'cancelled'",
    );
    $args = array($schedule_version);

    $event = isset($filters['event']) ? vaysf_sanitize_public_filter($filters['event']) : '';
    if ($event !== '') {
        $where[] = 's.event = %s';
        $args[] = $event;
    }

    $day = isset($filters['day']) ? vaysf_sanitize_public_day_filter($filters['day']) : '';

    $venue = isset($filters['venue']) ? vaysf_sanitize_public_filter($filters['venue']) : '';
    if ($venue !== '') {
        $where[] = 's.scheduled_location = %s';
        $args[] = $venue;
    }

    $church = isset($filters['church']) ? vaysf_sanitize_public_church_filter($filters['church']) : '';

    // "Upcoming games only" (visitor checkbox, #303): a short grace period
    // back to today, capped at the end of today — not open-ended into future
    // days. Takes precedence over the embed-configured 'lookback_minutes',
    // which remains open-ended for admins who want that instead.
    $upcoming_only = isset($filters['upcoming_only']) && vaysf_sanitize_public_filter($filters['upcoming_only']) === '1';
    $competition_cutoff_start = null;
    $competition_cutoff_end = null;
    if ($upcoming_only) {
        $sports_fest_now = vaysf_get_sports_fest_now();
        $competition_cutoff_start = $sports_fest_now->modify('-' . VAYSF_UPCOMING_ONLY_LOOKBACK_MINUTES . ' minutes');
        $competition_cutoff_end = $sports_fest_now->setTime(23, 59, 59);
    } else {
        $lookback_minutes = isset($filters['lookback_minutes'])
            ? vaysf_sanitize_public_lookback_minutes($filters['lookback_minutes'])
            : null;
        if ($lookback_minutes !== null) {
            $competition_cutoff_start = vaysf_get_sports_fest_now()->modify('-' . $lookback_minutes . ' minutes');
        }
    }

    $where_clause = implode(' AND ', $where);
    $sql = "SELECT s.*, r.result_id, r.score_json, r.public_status, r.scan_status, r.updated_at AS result_updated_at
        FROM $table_schedules s
        LEFT JOIN $table_results r ON r.schedule_id = s.schedule_id
        WHERE $where_clause
        ORDER BY s.scheduled_time IS NULL, s.scheduled_time, s.schedule_id";

    $rows = $wpdb->get_results($wpdb->prepare($sql, $args), ARRAY_A);
    if (!is_array($rows)) {
        return array();
    }

    if ($church !== '') {
        $rows = array_values(array_filter($rows, function ($row) use ($church) {
            return vaysf_schedule_church_signature_contains($row, $church);
        }));
    }

    if ($day !== '' || $competition_cutoff_start instanceof DateTimeImmutable || $competition_cutoff_end instanceof DateTimeImmutable) {
        $rows = array_values(array_filter($rows, function ($row) use ($day, $competition_cutoff_start, $competition_cutoff_end) {
            $competition_at = vaysf_get_schedule_competition_datetime($row);
            if (!$competition_at instanceof DateTimeImmutable) {
                return false;
            }

            if ($day !== '' && $competition_at->format('Y-m-d') !== $day) {
                return false;
            }
            if ($competition_cutoff_start instanceof DateTimeImmutable && $competition_at < $competition_cutoff_start) {
                return false;
            }
            if ($competition_cutoff_end instanceof DateTimeImmutable && $competition_at > $competition_cutoff_end) {
                return false;
            }

            return true;
        }));
    }

    $missing_result_rows = array();
    foreach ($rows as $row) {
        $has_direct_score = trim((string) ($row['score_json'] ?? '')) !== '';
        if (!$has_direct_score && !empty($row['schedule_id'])) {
            $missing_result_rows[] = $row;
        }
    }
    $fallback_results = function_exists('vaysf_get_result_fallbacks_for_schedule_rows')
        ? vaysf_get_result_fallbacks_for_schedule_rows($missing_result_rows)
        : array();

    $public_rows = array();
    foreach ($rows as $row) {
        $schedule_id = !empty($row['schedule_id']) ? absint($row['schedule_id']) : 0;
        if (trim((string) ($row['score_json'] ?? '')) === '' && $schedule_id && !empty($fallback_results[$schedule_id])) {
            $fallback = $fallback_results[$schedule_id];
            $row['result_id'] = $fallback['result_id'] ?? '';
            $row['score_json'] = $fallback['score_json'] ?? '';
            $row['public_status'] = $fallback['public_status'] ?? '';
            $row['scan_status'] = $fallback['scan_status'] ?? '';
            $row['result_updated_at'] = $fallback['updated_at'] ?? '';
        }

        if (!empty($row['result_updated_at'])) {
            $row['updated_at'] = $row['result_updated_at'];
        }
        $public_rows[] = vaysf_format_public_schedule_row($row);
    }

    return $public_rows;
}

/**
 * Fetch confirmed semifinal/final advancement placeholders for public display.
 *
 * "Confirmed" here means an admin has populated at least one team slot on the
 * Semifinal/Final schedule row after deciding pool-play qualifiers (RFC §6.3)
 * — there is no separate advancement-confirmation flag in the current schema.
 *
 * @param array<string,string> $filters Optional 'event'
 * @return array<int,array<string,mixed>> Public-safe advancement rows
 */
function vaysf_get_public_advancement_rows($filters = array()) {
    global $wpdb;

    $schedule_version = vaysf_get_current_published_schedule_version();
    if ($schedule_version === null) {
        return array();
    }

    $table_schedules = vaysf_get_table_name('schedules');

    $where = array(
        'schedule_version = %d',
        'published_at IS NOT NULL',
        "COALESCE(game_status, '') <> 'cancelled'",
        "stage IN ('Semifinal', 'Final')",
        "(COALESCE(team_a_key, '') <> '' OR COALESCE(team_b_key, '') <> '' OR COALESCE(team_c_key, '') <> '')",
    );
    $args = array($schedule_version);

    $event = isset($filters['event']) ? vaysf_sanitize_public_filter($filters['event']) : '';
    if ($event !== '') {
        $where[] = 'event = %s';
        $args[] = $event;
    }

    $where_clause = implode(' AND ', $where);
    $sql = "SELECT *
        FROM $table_schedules
        WHERE $where_clause
        ORDER BY event, stage, scheduled_time IS NULL, scheduled_time, schedule_id";

    $rows = $wpdb->get_results($wpdb->prepare($sql, $args), ARRAY_A);
    if (!is_array($rows)) {
        return array();
    }

    $public_rows = array();
    foreach ($rows as $row) {
        $public_rows[] = array(
            'game_key' => isset($row['game_key']) ? (string) $row['game_key'] : '',
            'event' => isset($row['event']) ? (string) $row['event'] : '',
            'stage' => isset($row['stage']) ? (string) $row['stage'] : '',
            'team_a_label' => isset($row['team_a_label']) ? (string) $row['team_a_label'] : '',
            'team_b_label' => isset($row['team_b_label']) ? (string) $row['team_b_label'] : '',
            'team_c_label' => isset($row['team_c_label']) ? (string) $row['team_c_label'] : '',
            'scheduled_time' => isset($row['scheduled_time']) ? (string) $row['scheduled_time'] : '',
            'scheduled_location' => isset($row['scheduled_location']) ? (string) $row['scheduled_location'] : '',
            'game_status' => isset($row['game_status']) ? (string) $row['game_status'] : 'scheduled',
        );
    }

    return $public_rows;
}

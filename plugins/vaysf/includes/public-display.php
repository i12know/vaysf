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
    $days = $wpdb->get_col(
        $wpdb->prepare(
            "SELECT DISTINCT DATE(scheduled_time) AS game_day
            FROM $table_schedules
            WHERE schedule_version = %d
                AND scheduled_time IS NOT NULL
                AND published_at IS NOT NULL
                AND COALESCE(game_status, '') <> 'cancelled'
            ORDER BY game_day",
            absint($schedule_version)
        )
    );

    return is_array($days) ? array_values(array_filter(array_map('strval', $days))) : array();
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
    $public_status = isset($row['public_status']) ? (string) $row['public_status'] : '';
    $score = null;

    if (in_array($public_status, array('reported', 'official', 'under_review'), true) && !empty($row['score_json'])) {
        $decoded = json_decode($row['score_json'], true);
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
        'scheduled_location' => isset($row['scheduled_location']) ? (string) $row['scheduled_location'] : '',
        'game_status' => isset($row['game_status']) ? (string) $row['game_status'] : 'scheduled',
        'public_status' => $public_status,
        'score' => $score,
        'updated_at' => isset($row['updated_at']) ? (string) $row['updated_at'] : '',
    );
}

/**
 * Fetch the currently published, non-cancelled schedule joined with its
 * current result, filtered for public display.
 *
 * @param array<string,string> $filters Optional 'event', 'day' (Y-m-d), 'venue'
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
    if ($day !== '') {
        $where[] = 'DATE(s.scheduled_time) = %s';
        $args[] = $day;
    }

    $venue = isset($filters['venue']) ? vaysf_sanitize_public_filter($filters['venue']) : '';
    if ($venue !== '') {
        $where[] = 's.scheduled_location = %s';
        $args[] = $venue;
    }

    $where_clause = implode(' AND ', $where);
    $sql = "SELECT s.*, r.score_json, r.public_status, r.updated_at AS result_updated_at
        FROM $table_schedules s
        LEFT JOIN $table_results r ON r.schedule_id = s.schedule_id
        WHERE $where_clause
        ORDER BY s.scheduled_time IS NULL, s.scheduled_time, s.schedule_id";

    $rows = $wpdb->get_results($wpdb->prepare($sql, $args), ARRAY_A);
    if (!is_array($rows)) {
        return array();
    }

    $public_rows = array();
    foreach ($rows as $row) {
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

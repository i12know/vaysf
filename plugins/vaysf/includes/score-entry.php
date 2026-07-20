<?php
/**
 * File: includes/score-entry.php
 * Description: Coordinator score-entry helpers for VAYSF Integration
 * Version: 1.0.0
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}
if (!defined('VAYSF_AUTHORIZED_EVENTS_META_KEY')) {
    define('VAYSF_AUTHORIZED_EVENTS_META_KEY', 'vaysf_authorized_events');
}

/**
 * Get the latest published schedule version that still has active games.
 *
 * @return int|null Schedule version, or null when no published schedule exists
 */
function vaysf_get_current_published_schedule_version() {
    global $wpdb;

    $table_schedules = vaysf_get_table_name('schedules');
    $version = $wpdb->get_var(
        "SELECT MAX(schedule_version)
        FROM $table_schedules
        WHERE published_at IS NOT NULL
            AND COALESCE(game_status, '') <> 'cancelled'"
    );

    if ($version === null) {
        return null;
    }

    return absint($version);
}

/**
 * Get distinct events from the currently published, non-cancelled schedule.
 *
 * @param int|null $schedule_version Optional version; defaults to current published version
 * @return array<int,string> Event names as stored in sf_schedules.event
 */
function vaysf_get_published_schedule_events($schedule_version = null) {
    global $wpdb;

    if ($schedule_version === null) {
        $schedule_version = vaysf_get_current_published_schedule_version();
    }

    if ($schedule_version === null) {
        return array();
    }

    $table_schedules = vaysf_get_table_name('schedules');
    $events = $wpdb->get_col(
        $wpdb->prepare(
            "SELECT DISTINCT event
            FROM $table_schedules
            WHERE schedule_version = %d
                AND event IS NOT NULL
                AND event <> ''
                AND published_at IS NOT NULL
                AND COALESCE(game_status, '') <> 'cancelled'
            ORDER BY event",
            absint($schedule_version)
        )
    );

    if (!is_array($events)) {
        return array();
    }

    return array_values(array_filter(array_map('strval', $events)));
}

/**
 * Normalize event names for storage/comparison.
 *
 * @param mixed $events Event value or list of event values
 * @return array<int,string> Unique sanitized event names
 */
function vaysf_normalize_authorized_events($events) {
    if (!is_array($events)) {
        $events = ($events === null || $events === '') ? array() : array($events);
    }

    $normalized = array();
    foreach ($events as $event) {
        $event = sanitize_text_field(wp_unslash($event));
        if ($event === '') {
            continue;
        }
        $normalized[$event] = $event;
    }

    return array_values($normalized);
}

/**
 * Read a user's schedule-event authorization list.
 *
 * @param int $user_id WordPress user id
 * @return array<int,string> Authorized event names
 */
function vaysf_get_user_authorized_events($user_id) {
    $events = get_user_meta(absint($user_id), VAYSF_AUTHORIZED_EVENTS_META_KEY, true);
    return vaysf_normalize_authorized_events($events);
}

/**
 * Check whether a user should see all published score-entry events.
 *
 * @param int $user_id WordPress user id
 * @return bool True for WordPress admins and Sports Fest admin/manager roles
 */
function vaysf_user_has_all_score_entry_events($user_id) {
    $user_id = absint($user_id);
    if (!$user_id || !user_can($user_id, 'sf2025_submit_results')) {
        return false;
    }

    return user_can($user_id, 'manage_options')
        || user_can($user_id, 'sf2025_admin')
        || user_can($user_id, 'sf2025_write');
}

/**
 * Get the events a user may see on the score-entry dashboard.
 *
 * Coordinators are limited to user meta assignments. Administrators, Sports
 * Fest Admins, and Sports Fest Managers see all current published events.
 *
 * @param int $user_id WordPress user id
 * @return array<int,string> Event names
 */
function vaysf_get_user_score_entry_events($user_id) {
    $user_id = absint($user_id);
    if (!$user_id || !user_can($user_id, 'sf2025_submit_results')) {
        return array();
    }

    if (vaysf_user_has_all_score_entry_events($user_id)) {
        return vaysf_get_published_schedule_events();
    }

    return vaysf_get_user_authorized_events($user_id);
}

/**
 * Update a user's authorized events, constrained to the published schedule.
 *
 * @param int $user_id WordPress user id
 * @param mixed $events Selected event values
 * @return bool True when the authorization list was updated/deleted
 */
function vaysf_update_user_authorized_events($user_id, $events) {
    $user_id = absint($user_id);
    if (!$user_id) {
        return false;
    }

    $available_events = vaysf_get_published_schedule_events();
    if (!$available_events) {
        return false;
    }

    $available_lookup = array_fill_keys($available_events, true);
    $selected = array();
    foreach (vaysf_normalize_authorized_events($events) as $event) {
        if (isset($available_lookup[$event])) {
            $selected[] = $event;
        }
    }

    if (!$selected) {
        delete_user_meta($user_id, VAYSF_AUTHORIZED_EVENTS_META_KEY);
        return true;
    }

    update_user_meta($user_id, VAYSF_AUTHORIZED_EVENTS_META_KEY, array_values($selected));
    return true;
}

/**
 * Resolve a schedule row from an id, array, or object.
 *
 * @param mixed $schedule Schedule id or row
 * @return array<string,mixed>|null Schedule row
 */
function vaysf_resolve_schedule_row($schedule) {
    if (is_numeric($schedule)) {
        global $wpdb;

        $table_schedules = vaysf_get_table_name('schedules');
        $row = $wpdb->get_row(
            $wpdb->prepare(
                "SELECT * FROM $table_schedules WHERE schedule_id = %d",
                absint($schedule)
            ),
            ARRAY_A
        );

        return is_array($row) ? $row : null;
    }

    if (is_array($schedule)) {
        return $schedule;
    }

    if (is_object($schedule)) {
        return get_object_vars($schedule);
    }

    return null;
}

/**
 * Resolve a current published schedule row by stable game_key.
 *
 * Printed score-sheet QR codes use game_key rather than schedule_id because
 * schedule_id is a WordPress database row id and may change after republishing.
 *
 * @param string $game_key Stable schedule game key, e.g. BBM-01
 * @return array<string,mixed>|null Schedule row
 */
function vaysf_resolve_schedule_row_by_game_key($game_key) {
    global $wpdb;

    $game_key = sanitize_text_field($game_key);
    if ($game_key === '') {
        return null;
    }

    $current_version = vaysf_get_current_published_schedule_version();
    if ($current_version === null) {
        return null;
    }

    $table_schedules = vaysf_get_table_name('schedules');
    $row = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT * FROM $table_schedules
            WHERE game_key = %s
                AND schedule_version = %d
                AND published_at IS NOT NULL
                AND COALESCE(game_status, '') <> 'cancelled'
            LIMIT 1",
            $game_key,
            absint($current_version)
        ),
        ARRAY_A
    );

    return is_array($row) ? $row : null;
}

/**
 * Check whether a user may submit a result for a schedule row.
 *
 * @param int $user_id WordPress user id
 * @param mixed $schedule Schedule id, row array, or row object
 * @return bool True when the user has result capability and event authorization
 */
function vaysf_user_can_submit_schedule_result($user_id, $schedule) {
    $user_id = absint($user_id);
    if (!$user_id || !user_can($user_id, 'sf2025_submit_results')) {
        return false;
    }

    $schedule_row = vaysf_resolve_schedule_row($schedule);
    if (!$schedule_row) {
        return false;
    }

    $event = isset($schedule_row['event']) ? sanitize_text_field($schedule_row['event']) : '';
    if ($event === '') {
        return false;
    }

    $current_version = vaysf_get_current_published_schedule_version();
    if ($current_version === null) {
        return false;
    }

    $schedule_version = isset($schedule_row['schedule_version']) ? absint($schedule_row['schedule_version']) : null;
    if ($schedule_version !== $current_version) {
        return false;
    }

    $game_status = isset($schedule_row['game_status']) ? sanitize_text_field($schedule_row['game_status']) : '';
    if ($game_status === 'cancelled') {
        return false;
    }

    if (array_key_exists('published_at', $schedule_row) && empty($schedule_row['published_at'])) {
        return false;
    }

    if (vaysf_user_has_all_score_entry_events($user_id)) {
        return in_array($event, vaysf_get_published_schedule_events($current_version), true);
    }

    return in_array($event, vaysf_get_user_authorized_events($user_id), true);
}

/**
 * Format schedule teams consistently for front-end and admin displays.
 *
 * @param array<string,mixed>|object $row Schedule row
 * @return string Team/participant label
 */
function vaysf_format_schedule_teams($row) {
    if (is_object($row)) {
        $row = get_object_vars($row);
    }

    if (!is_array($row)) {
        return '';
    }

    $teams = array();
    foreach (array('team_a_label', 'team_b_label', 'team_c_label') as $field) {
        if (!empty($row[$field])) {
            $teams[] = $row[$field];
        }
    }

    return implode(' vs ', $teams);
}

/**
 * Extract a church code from a schedule/result team value when possible.
 *
 * Older score payloads used keys such as BBM::RPC while newer published
 * schedules may use solver slot ids such as BBM-P1-T1 plus dedicated
 * team_*_church_code columns. This helper lets event-day displays match the
 * same church matchup across those formats.
 *
 * @param mixed $value Raw team key, church code, or display label
 * @return string Uppercase church code-ish token, or ''
 */
function vaysf_extract_church_code_from_team_value($value) {
    $value = strtoupper(trim((string) $value));
    if ($value === '') {
        return '';
    }

    if (strpos($value, '::') !== false) {
        $parts = explode('::', $value);
        $value = trim((string) end($parts));
    }

    if (preg_match('/^[A-Z0-9]{2,16}$/', $value)) {
        return $value;
    }

    return '';
}

/**
 * Extract a sport/team family prefix such as BBM, VBM, VBW, SOC, or BC.
 *
 * @param mixed $value Raw team key
 * @return string Uppercase family token, or ''
 */
function vaysf_extract_team_family_from_value($value) {
    $value = strtoupper(trim((string) $value));
    if ($value === '') {
        return '';
    }

    if (preg_match('/^([A-Z0-9]+)::/', $value, $matches)) {
        return $matches[1];
    }
    if (preg_match('/^([A-Z0-9]+)-/', $value, $matches)) {
        return $matches[1];
    }

    return '';
}

/**
 * Normalize team-like identifiers into a sorted signature.
 *
 * @param array<int,mixed> $values Raw values
 * @return string Stable pipe-delimited signature
 */
function vaysf_build_team_signature($values) {
    $normalized = array();
    foreach ((array) $values as $value) {
        $value = strtoupper(trim((string) $value));
        if ($value !== '') {
            $normalized[$value] = $value;
        }
    }

    sort($normalized, SORT_STRING);
    return implode('|', array_values($normalized));
}

/**
 * Build an exact team-key signature from a schedule row.
 *
 * @param array<string,mixed> $row Schedule row
 * @return string
 */
function vaysf_schedule_team_key_signature($row) {
    $values = array();
    foreach (array('team_a_key', 'team_b_key', 'team_c_key') as $field) {
        if (!empty($row[$field])) {
            $values[] = $row[$field];
        }
    }

    return vaysf_build_team_signature($values);
}

/**
 * Build a team-family signature from a schedule row.
 *
 * @param array<string,mixed> $row Schedule row
 * @return string
 */
function vaysf_schedule_team_family_signature($row) {
    $values = array();
    foreach (array('team_a_key', 'team_b_key', 'team_c_key') as $field) {
        $family = !empty($row[$field]) ? vaysf_extract_team_family_from_value($row[$field]) : '';
        if ($family !== '') {
            $values[] = $family;
        }
    }

    return vaysf_build_team_signature($values);
}

/**
 * Build a church-code matchup signature from a schedule row.
 *
 * @param array<string,mixed> $row Schedule row
 * @return string
 */
function vaysf_schedule_church_signature($row) {
    $values = array();
    foreach (array('a', 'b', 'c') as $slot) {
        $church_field = "team_{$slot}_church_code";
        $key_field = "team_{$slot}_key";
        $label_field = "team_{$slot}_label";

        $church = '';
        if (!empty($row[$church_field])) {
            $church = vaysf_extract_church_code_from_team_value($row[$church_field]);
        }
        if ($church === '' && !empty($row[$key_field])) {
            $church = vaysf_extract_church_code_from_team_value($row[$key_field]);
        }
        if ($church === '' && !empty($row[$label_field])) {
            $church = vaysf_extract_church_code_from_team_value($row[$label_field]);
        }
        if ($church !== '') {
            $values[] = $church;
        }
    }

    return vaysf_build_team_signature($values);
}

/**
 * Build an exact team-key signature from a decoded score payload.
 *
 * @param array<string,mixed> $payload Decoded score_json
 * @return string
 */
function vaysf_score_payload_team_key_signature($payload) {
    $values = array();
    foreach (array('team_a_key', 'team_b_key', 'team_c_key') as $field) {
        if (!empty($payload[$field])) {
            $values[] = $payload[$field];
        }
    }

    return vaysf_build_team_signature($values);
}

/**
 * Build a team-family signature from a decoded score payload.
 *
 * @param array<string,mixed> $payload Decoded score_json
 * @return string
 */
function vaysf_score_payload_team_family_signature($payload) {
    $values = array();
    foreach (array('team_a_key', 'team_b_key', 'team_c_key') as $field) {
        $family = !empty($payload[$field]) ? vaysf_extract_team_family_from_value($payload[$field]) : '';
        if ($family !== '') {
            $values[] = $family;
        }
    }

    return vaysf_build_team_signature($values);
}

/**
 * Build a church-code matchup signature from a decoded score payload.
 *
 * @param array<string,mixed> $payload Decoded score_json
 * @return string
 */
function vaysf_score_payload_church_signature($payload) {
    $values = array();
    foreach (array('a', 'b', 'c') as $slot) {
        $church = '';
        $key_field = "team_{$slot}_key";
        $label_field = "team_{$slot}_label";

        if (!empty($payload[$key_field])) {
            $church = vaysf_extract_church_code_from_team_value($payload[$key_field]);
        }
        if ($church === '' && !empty($payload[$label_field])) {
            $church = vaysf_extract_church_code_from_team_value($payload[$label_field]);
        }
        if ($church !== '') {
            $values[] = $church;
        }
    }

    return vaysf_build_team_signature($values);
}

/**
 * Return a normalized public status for a result row across old/new schemas.
 *
 * @param array<string,mixed> $result Result row
 * @return string
 */
function vaysf_get_result_public_status_value($result) {
    if (!empty($result['public_status'])) {
        return (string) $result['public_status'];
    }
    if (!empty($result['result_status'])) {
        return (string) $result['result_status'];
    }

    return '';
}

/**
 * Events supported by the first simple score-entry slice.
 *
 * Racquet sports need sport-specific forms, so keep this intentionally narrow
 * until those workflows are implemented.
 *
 * @return array<int,string> Event names eligible for two-team numeric scoring
 */
function vaysf_simple_score_events() {
    return apply_filters(
        'vaysf_simple_score_events',
        array(
            'Basketball - Men Team',
            'Soccer - Coed Exhibition',
        )
    );
}

/**
 * Events supported by the first three-team score-entry slice.
 *
 * @return array<int,string> Event names eligible for three-team numeric scoring
 */
function vaysf_three_team_score_events() {
    return apply_filters(
        'vaysf_three_team_score_events',
        array(
            'Bible Challenge - Mixed Team',
        )
    );
}

/**
 * Events supported by volleyball set-based score entry.
 *
 * @return array<int,string> Event names eligible for volleyball set scoring
 */
function vaysf_volleyball_score_events() {
    return apply_filters(
        'vaysf_volleyball_score_events',
        array(
            'Volleyball - Men Team',
            'Volleyball - Women Team',
        )
    );
}

/**
 * Check whether a schedule row can use the simple two-team score form.
 *
 * @param mixed $schedule Schedule id, row array, or row object
 * @return bool True when the row is a supported two-team score game
 */
function vaysf_is_simple_score_schedule($schedule) {
    $schedule_row = vaysf_resolve_schedule_row($schedule);
    if (!$schedule_row) {
        return false;
    }

    $event = isset($schedule_row['event']) ? sanitize_text_field($schedule_row['event']) : '';
    if (!in_array($event, vaysf_simple_score_events(), true)) {
        return false;
    }

    return !empty($schedule_row['team_a_key'])
        && !empty($schedule_row['team_b_key'])
        && empty($schedule_row['team_c_key']);
}

/**
 * Check whether a schedule row can use the three-team score form.
 *
 * @param mixed $schedule Schedule id, row array, or row object
 * @return bool True when the row is a supported three-team score game
 */
function vaysf_is_three_team_score_schedule($schedule) {
    $schedule_row = vaysf_resolve_schedule_row($schedule);
    if (!$schedule_row) {
        return false;
    }

    $event = isset($schedule_row['event']) ? sanitize_text_field($schedule_row['event']) : '';
    if (!in_array($event, vaysf_three_team_score_events(), true)) {
        return false;
    }

    return !empty($schedule_row['team_a_key'])
        && !empty($schedule_row['team_b_key'])
        && !empty($schedule_row['team_c_key']);
}

/**
 * Check whether a schedule row can use the volleyball set score form.
 *
 * @param mixed $schedule Schedule id, row array, or row object
 * @return bool True when the row is a supported two-team volleyball game
 */
function vaysf_is_volleyball_score_schedule($schedule) {
    $schedule_row = vaysf_resolve_schedule_row($schedule);
    if (!$schedule_row) {
        return false;
    }

    $event = isset($schedule_row['event']) ? sanitize_text_field($schedule_row['event']) : '';
    if (!in_array($event, vaysf_volleyball_score_events(), true)) {
        return false;
    }

    return !empty($schedule_row['team_a_key'])
        && !empty($schedule_row['team_b_key'])
        && empty($schedule_row['team_c_key']);
}

/**
 * Check whether a volleyball schedule row may end as a split match.
 *
 * Sports Fest preliminary/pool volleyball matches may stop after two split
 * sets. Playoff-style rows should still require a deciding tiebreaker.
 *
 * @param mixed $schedule Schedule id, row array, or row object
 * @return bool True when a split/no-winner volleyball result is allowed
 */
function vaysf_volleyball_allows_split_match($schedule) {
    $schedule_row = vaysf_resolve_schedule_row($schedule);
    if (!$schedule_row || !vaysf_is_volleyball_score_schedule($schedule_row)) {
        return false;
    }

    $stage = isset($schedule_row['stage']) ? sanitize_text_field($schedule_row['stage']) : '';
    $stage_key = strtolower(trim($stage));
    if (in_array($stage_key, array('pool', 'prelim', 'preliminary'), true)) {
        return true;
    }

    $game_key = isset($schedule_row['game_key']) ? sanitize_text_field($schedule_row['game_key']) : '';
    return (bool) preg_match('/^VB[MW]-\d+$/', $game_key);
}

/**
 * Events supported by the final-placement score form (Issue #209).
 *
 * Track & Field and Tug-of-War are all-church individual/mixed placement
 * events, not team-vs-team matchups — their schedule rows carry no
 * team_a_key/team_b_key (RFC §9.5). Placements are chosen fresh from the
 * published church list at submission time rather than pre-populated from
 * the schedule row.
 *
 * @return array<int,string> Event names eligible for placement entry
 */
function vaysf_placement_score_events() {
    return apply_filters(
        'vaysf_placement_score_events',
        array(
            'Track & Field',
            'Tug-of-war',
        )
    );
}

/**
 * Check whether a schedule row can use the final-placement score form.
 *
 * @param mixed $schedule Schedule id, row array, or row object
 * @return bool True when the row is a supported placement event
 */
function vaysf_is_placement_score_schedule($schedule) {
    $schedule_row = vaysf_resolve_schedule_row($schedule);
    if (!$schedule_row) {
        return false;
    }

    $event = isset($schedule_row['event']) ? sanitize_text_field($schedule_row['event']) : '';
    return in_array($event, vaysf_placement_score_events(), true);
}

/**
 * Check whether a schedule row currently has any coordinator score form.
 *
 * @param mixed $schedule Schedule id, row array, or row object
 * @return bool True when a supported score-entry form exists
 */
function vaysf_is_supported_score_schedule($schedule) {
    return vaysf_is_simple_score_schedule($schedule)
        || vaysf_is_three_team_score_schedule($schedule)
        || vaysf_is_volleyball_score_schedule($schedule)
        || vaysf_is_placement_score_schedule($schedule);
}

/**
 * Read the current result row for a schedule row.
 *
 * @param int $schedule_id Schedule row id
 * @return array<string,mixed>|null Result row
 */
function vaysf_get_result_for_schedule($schedule_id) {
    global $wpdb;

    $schedule_id = absint($schedule_id);
    if (!$schedule_id) {
        return null;
    }

    $table_results = vaysf_get_table_name('results');
    $result = $wpdb->get_row(
        $wpdb->prepare("SELECT * FROM $table_results WHERE schedule_id = %d", $schedule_id),
        ARRAY_A
    );

    if (is_array($result) && trim((string) ($result['score_json'] ?? '')) !== '') {
        return $result;
    }

    $schedule = vaysf_resolve_schedule_row($schedule_id);
    if (!$schedule) {
        return is_array($result) ? $result : null;
    }

    $fallbacks = vaysf_get_result_fallbacks_for_schedule_rows(array($schedule));
    if (!empty($fallbacks[$schedule_id])) {
        return $fallbacks[$schedule_id];
    }

    return is_array($result) ? $result : null;
}

/**
 * Match historical/orphaned result rows back to current published schedules.
 *
 * @param array<int,array<string,mixed>> $schedule_rows Current schedule rows
 * @return array<int,array<string,mixed>> Result rows keyed by current schedule_id
 */
function vaysf_get_result_fallbacks_for_schedule_rows($schedule_rows) {
    global $wpdb;

    $expected = array();
    foreach ((array) $schedule_rows as $row) {
        if (!is_array($row) || empty($row['schedule_id'])) {
            continue;
        }

        $schedule_id = absint($row['schedule_id']);
        $expected[$schedule_id] = array(
            'schedule_id' => $schedule_id,
            'game_key' => isset($row['game_key']) ? (string) $row['game_key'] : '',
            'event' => isset($row['event']) ? (string) $row['event'] : '',
            'team_key_signature' => vaysf_schedule_team_key_signature($row),
            'team_family_signature' => vaysf_schedule_team_family_signature($row),
            'church_signature' => vaysf_schedule_church_signature($row),
        );
    }

    if (!$expected) {
        return array();
    }

    $table_results = vaysf_get_table_name('results');
    $table_schedules = vaysf_get_table_name('schedules');
    $candidate_rows = $wpdb->get_results(
        "SELECT r.*, s_hist.game_key AS historical_game_key, s_hist.event AS historical_event,
            s_hist.team_a_key AS historical_team_a_key,
            s_hist.team_a_label AS historical_team_a_label,
            s_hist.team_b_key AS historical_team_b_key,
            s_hist.team_b_label AS historical_team_b_label,
            s_hist.team_c_key AS historical_team_c_key,
            s_hist.team_c_label AS historical_team_c_label,
            s_hist.team_a_church_code AS historical_team_a_church_code,
            s_hist.team_b_church_code AS historical_team_b_church_code,
            s_hist.team_c_church_code AS historical_team_c_church_code
        FROM $table_results r
        LEFT JOIN $table_schedules s_hist ON s_hist.schedule_id = r.schedule_id
        WHERE r.score_json IS NOT NULL AND r.score_json <> ''
        ORDER BY r.updated_at DESC, r.result_id DESC
        LIMIT 1000",
        ARRAY_A
    );
    if (!is_array($candidate_rows)) {
        return array();
    }

    $matches = array();
    foreach ($candidate_rows as $candidate) {
        $decoded = json_decode($candidate['score_json'] ?? '', true);
        if (!is_array($decoded)) {
            $decoded = array();
        }

        $candidate_team_signature = vaysf_score_payload_team_key_signature($decoded);
        $candidate_family_signature = vaysf_score_payload_team_family_signature($decoded);
        $candidate_church_signature = vaysf_score_payload_church_signature($decoded);

        if ($candidate_church_signature === '') {
            $candidate_church_signature = vaysf_schedule_church_signature(array(
                'team_a_key' => $candidate['historical_team_a_key'] ?? '',
                'team_a_label' => $candidate['historical_team_a_label'] ?? '',
                'team_a_church_code' => $candidate['historical_team_a_church_code'] ?? '',
                'team_b_key' => $candidate['historical_team_b_key'] ?? '',
                'team_b_label' => $candidate['historical_team_b_label'] ?? '',
                'team_b_church_code' => $candidate['historical_team_b_church_code'] ?? '',
                'team_c_key' => $candidate['historical_team_c_key'] ?? '',
                'team_c_label' => $candidate['historical_team_c_label'] ?? '',
                'team_c_church_code' => $candidate['historical_team_c_church_code'] ?? '',
            ));
        }

        foreach ($expected as $schedule_id => $row_expectation) {
            if (isset($matches[$schedule_id])) {
                continue;
            }

            $event_matches = $row_expectation['event'] === ''
                || empty($candidate['historical_event'])
                || strcasecmp($row_expectation['event'], (string) $candidate['historical_event']) === 0;
            $family_matches = $row_expectation['team_family_signature'] === ''
                || $candidate_family_signature === ''
                || $row_expectation['team_family_signature'] === $candidate_family_signature;

            $game_key_matches = $row_expectation['game_key'] !== ''
                && !empty($candidate['historical_game_key'])
                && $row_expectation['game_key'] === (string) $candidate['historical_game_key'];

            $team_key_matches = $row_expectation['team_key_signature'] !== ''
                && $candidate_team_signature !== ''
                && $row_expectation['team_key_signature'] === $candidate_team_signature;

            $church_matches = $event_matches
                && $family_matches
                && $row_expectation['church_signature'] !== ''
                && $candidate_church_signature !== ''
                && $row_expectation['church_signature'] === $candidate_church_signature;

            if ($game_key_matches || $team_key_matches || $church_matches) {
                $candidate['public_status'] = vaysf_get_result_public_status_value($candidate);
                $candidate['result_updated_at'] = $candidate['updated_at'] ?? '';
                $candidate['result_created_at'] = $candidate['created_at'] ?? '';
                $matches[$schedule_id] = $candidate;
            }
        }
    }

    return $matches;
}

/**
 * Maximum accepted score-sheet scan upload size in bytes (32 MB).
 *
 * @return int
 */
function vaysf_get_scoresheet_max_bytes() {
    return 33554432;
}

/**
 * Read files already attached to a result.
 *
 * @param int $result_id Result row id
 * @return array<int,array<string,mixed>> File rows with revision metadata
 */
function vaysf_get_result_files_for_result($result_id) {
    global $wpdb;

    $result_id = absint($result_id);
    if (!$result_id) {
        return array();
    }

    $table_files = vaysf_get_table_name('result_files');
    $table_revisions = vaysf_get_table_name('result_revisions');
    $rows = $wpdb->get_results(
        $wpdb->prepare(
            "SELECT f.*, rr.result_id, rr.revision_number
            FROM $table_files f
            INNER JOIN $table_revisions rr ON rr.revision_id = f.result_revision_id
            WHERE rr.result_id = %d
            ORDER BY f.uploaded_at DESC, f.file_id DESC",
            $result_id
        ),
        ARRAY_A
    );

    return is_array($rows) ? $rows : array();
}

/**
 * Build a protected download URL for a stored result file.
 *
 * @param int $file_id Result file id
 * @return string URL
 */
function vaysf_get_result_file_download_url($file_id) {
    $file_id = absint($file_id);
    return wp_nonce_url(
        admin_url('admin-post.php?action=vaysf_download_result_file&file_id=' . $file_id),
        'vaysf_download_result_file_' . $file_id
    );
}

/**
 * Build a protected inline view URL for a stored result file.
 *
 * @param int $file_id Result file id
 * @return string URL
 */
function vaysf_get_result_file_view_url($file_id) {
    $file_id = absint($file_id);
    return wp_nonce_url(
        admin_url('admin-post.php?action=vaysf_download_result_file&view=1&file_id=' . $file_id),
        'vaysf_download_result_file_' . $file_id
    );
}

/**
 * Fetch one result file plus its schedule context for authorization/downloads.
 *
 * @param int $file_id Result file id
 * @return array<string,mixed>|null File row
 */
function vaysf_get_result_file_with_context($file_id) {
    global $wpdb;

    $file_id = absint($file_id);
    if (!$file_id) {
        return null;
    }

    $table_files = vaysf_get_table_name('result_files');
    $table_revisions = vaysf_get_table_name('result_revisions');
    $table_results = vaysf_get_table_name('results');
    $table_schedules = vaysf_get_table_name('schedules');

    $row = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT f.*, rr.result_id, rr.revision_number, r.schedule_id, s.*
            FROM $table_files f
            INNER JOIN $table_revisions rr ON rr.revision_id = f.result_revision_id
            INNER JOIN $table_results r ON r.result_id = rr.result_id
            INNER JOIN $table_schedules s ON s.schedule_id = r.schedule_id
            WHERE f.file_id = %d",
            $file_id
        ),
        ARRAY_A
    );

    return is_array($row) ? $row : null;
}

/**
 * Check whether a user may download a protected result file.
 *
 * @param int $user_id WordPress user id
 * @param array<string,mixed> $file_row Result file row with schedule fields
 * @return bool
 */
function vaysf_user_can_download_result_file($user_id, $file_row) {
    $user_id = absint($user_id);
    if (!$user_id || !is_array($file_row)) {
        return false;
    }

    if (user_can($user_id, 'manage_options') || user_can($user_id, 'sf2025_admin') || user_can($user_id, 'sf2025_write')) {
        return true;
    }

    return vaysf_user_can_submit_schedule_result($user_id, $file_row);
}

/**
 * Validate an uploaded score-sheet scan and return trusted file metadata.
 *
 * @param array $file Uploaded file array
 * @return array<string,string|int>|WP_Error|null Metadata, error, or null when no file was chosen
 */
function vaysf_validate_scoresheet_upload($file) {
    if (empty($file) || !isset($file['tmp_name'])) {
        return null;
    }

    if (isset($file['error']) && (int) $file['error'] === UPLOAD_ERR_NO_FILE) {
        return null;
    }

    if (!empty($file['error']) && (int) $file['error'] !== UPLOAD_ERR_OK) {
        return new WP_Error('vaysf_scoresheet_upload_error', __('The score sheet scan could not be uploaded. Please try again.', 'vaysf'));
    }

    if (!isset($file['size']) || (int) $file['size'] <= 0 || (int) $file['size'] > vaysf_get_scoresheet_max_bytes()) {
        return new WP_Error('vaysf_scoresheet_size', __('Score sheet scans must be PDF/JPEG/PNG files no larger than 32 MB.', 'vaysf'));
    }

    $original_name = isset($file['name']) ? sanitize_file_name($file['name']) : 'score-sheet';
    $extension = strtolower(pathinfo($original_name, PATHINFO_EXTENSION));
    $allowed = array(
        'pdf' => 'application/pdf',
        'jpg' => 'image/jpeg',
        'jpeg' => 'image/jpeg',
        'png' => 'image/png',
    );
    if (!isset($allowed[$extension])) {
        return new WP_Error('vaysf_scoresheet_type', __('Score sheet scans must be PDF, JPEG, or PNG files.', 'vaysf'));
    }

    $signature = is_readable($file['tmp_name']) ? file_get_contents($file['tmp_name'], false, null, 0, 8) : '';
    $valid_magic = false;
    if ($extension === 'pdf') {
        $valid_magic = strpos((string) $signature, '%PDF-') === 0;
    } elseif ($extension === 'png') {
        $valid_magic = (string) $signature === "\x89PNG\r\n\x1a\n";
    } elseif ($extension === 'jpg' || $extension === 'jpeg') {
        $valid_magic = substr((string) $signature, 0, 3) === "\xff\xd8\xff";
    }

    if (!$valid_magic) {
        return new WP_Error('vaysf_scoresheet_magic', __('The score sheet scan does not look like the selected file type.', 'vaysf'));
    }

    return array(
        'original_name' => $original_name,
        'extension' => $extension === 'jpeg' ? 'jpg' : $extension,
        'mime_type' => $allowed[$extension],
        'byte_size' => (int) $file['size'],
    );
}

/**
 * Validate, store, and attach an optional score-sheet scan to a result revision.
 *
 * @param int $result_id Result id
 * @param int $revision_id Result revision id
 * @param int $user_id Uploader user id
 * @param array $file Uploaded file array
 * @return array<string,mixed>|WP_Error|null Stored file row, error, or null when no file was chosen
 */
function vaysf_store_result_scoresheet_file($result_id, $revision_id, $user_id, $file) {
    global $wpdb;

    $result_id = absint($result_id);
    $revision_id = absint($revision_id);
    $user_id = absint($user_id);
    if (!$result_id || !$revision_id || !$user_id) {
        return new WP_Error('vaysf_scoresheet_missing_context', __('Score sheet upload is missing result context.', 'vaysf'));
    }

    $metadata = vaysf_validate_scoresheet_upload($file);
    if ($metadata === null || is_wp_error($metadata)) {
        return $metadata;
    }

    $table_revisions = vaysf_get_table_name('result_revisions');
    $revision = $wpdb->get_row(
        $wpdb->prepare("SELECT * FROM $table_revisions WHERE revision_id = %d AND result_id = %d", $revision_id, $result_id),
        ARRAY_A
    );
    if (!$revision) {
        return new WP_Error('vaysf_scoresheet_revision_missing', __('Result revision not found for score sheet upload.', 'vaysf'));
    }

    $table_results = vaysf_get_table_name('results');
    $result = $wpdb->get_row(
        $wpdb->prepare("SELECT * FROM $table_results WHERE result_id = %d", $result_id),
        ARRAY_A
    );
    $schedule = $result ? vaysf_resolve_schedule_row($result['schedule_id']) : null;
    if (!$schedule || !vaysf_user_can_download_result_file($user_id, $schedule)) {
        return new WP_Error('vaysf_scoresheet_forbidden', __('You are not authorized to attach a score sheet scan for this game.', 'vaysf'));
    }

    $upload_dir = wp_upload_dir();
    if (!empty($upload_dir['error'])) {
        return new WP_Error('vaysf_scoresheet_upload_dir', __('The upload directory is not available. Please try again.', 'vaysf'));
    }

    $relative_dir = 'vaysf/result-scans/' . current_time('Y/m');
    $base_dir = trailingslashit($upload_dir['basedir']) . 'vaysf/result-scans';
    $target_dir = trailingslashit($upload_dir['basedir']) . $relative_dir;
    if (!file_exists($target_dir)) {
        wp_mkdir_p($target_dir);
    }
    if (!is_dir($target_dir)) {
        return new WP_Error('vaysf_scoresheet_storage_dir', __('The protected score sheet scan directory could not be created. The score itself was still recorded.', 'vaysf'));
    }
    foreach (array($base_dir, $target_dir) as $dir) {
        $index_file = trailingslashit($dir) . 'index.php';
        if (!file_exists($index_file)) {
            file_put_contents($index_file, '<?php // Silence is golden');
        }
    }
    $htaccess = trailingslashit($base_dir) . '.htaccess';
    if (!file_exists($htaccess)) {
        file_put_contents($htaccess, "Require all denied\n");
    }

    $game_key = !empty($schedule['game_key']) ? sanitize_file_name($schedule['game_key']) : 'result-' . $result_id;
    $filename = sanitize_file_name($game_key . '-rev' . absint($revision['revision_number']) . '-' . wp_generate_password(8, false, false) . '.' . $metadata['extension']);
    $relative_path = trailingslashit($relative_dir) . $filename;
    $dest_path = trailingslashit($target_dir) . $filename;
    $hash = hash_file('sha256', $file['tmp_name']);
    if (!$hash) {
        return new WP_Error('vaysf_scoresheet_hash', __('The score sheet scan could not be verified. The score itself was still recorded.', 'vaysf'));
    }

    if (!is_uploaded_file($file['tmp_name'])) {
        return new WP_Error('vaysf_scoresheet_source', __('The score sheet scan was not received as a valid upload. The score itself was still recorded.', 'vaysf'));
    }

    $moved = @move_uploaded_file($file['tmp_name'], $dest_path);
    if (!$moved) {
        return new WP_Error('vaysf_scoresheet_storage', __('The score sheet scan could not be saved. The score itself was still recorded.', 'vaysf'));
    }
    @chmod($dest_path, 0640);

    $table_files = vaysf_get_table_name('result_files');
    $inserted = $wpdb->insert(
        $table_files,
        array(
            'result_revision_id' => $revision_id,
            'file_path' => $relative_path,
            'original_filename' => $metadata['original_name'],
            'mime_type' => $metadata['mime_type'],
            'byte_size' => $metadata['byte_size'],
            'sha256_hash' => $hash,
            'uploaded_by_user_id' => $user_id,
            'uploaded_at' => current_time('mysql'),
        ),
        array('%d', '%s', '%s', '%s', '%d', '%s', '%d', '%s')
    );
    if ($inserted === false) {
        @unlink($dest_path);
        return new WP_Error('vaysf_scoresheet_db', __('The score sheet scan could not be attached to the result. The score itself was still recorded.', 'vaysf'));
    }

    $wpdb->update(
        $table_results,
        array('scan_status' => 'uploaded', 'updated_at' => current_time('mysql')),
        array('result_id' => $result_id),
        array('%s', '%s'),
        array('%d')
    );

    return array(
        'file_id' => absint($wpdb->insert_id),
        'file_path' => $relative_path,
        'original_filename' => $metadata['original_name'],
        'mime_type' => $metadata['mime_type'],
        'byte_size' => $metadata['byte_size'],
        'sha256_hash' => $hash,
    );
}

/**
 * Serve a protected result file through an authenticated admin-post URL.
 *
 * @return void
 */
function vaysf_download_result_file() {
    $file_id = isset($_GET['file_id']) ? absint($_GET['file_id']) : 0;
    if (!$file_id || !is_user_logged_in()) {
        wp_die(__('File not found.', 'vaysf'), __('File not found', 'vaysf'), array('response' => 404));
    }

    if (empty($_GET['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_GET['_wpnonce'])), 'vaysf_download_result_file_' . $file_id)) {
        wp_die(__('Invalid download link.', 'vaysf'), __('Forbidden', 'vaysf'), array('response' => 403));
    }

    $file = vaysf_get_result_file_with_context($file_id);
    if (!$file || !vaysf_user_can_download_result_file(get_current_user_id(), $file)) {
        wp_die(__('You are not authorized to download this score sheet scan.', 'vaysf'), __('Forbidden', 'vaysf'), array('response' => 403));
    }

    $upload_dir = wp_upload_dir();
    $base_dir = realpath(trailingslashit($upload_dir['basedir']) . 'vaysf/result-scans');
    $path = realpath(trailingslashit($upload_dir['basedir']) . $file['file_path']);
    $base_prefix = $base_dir ? trailingslashit(wp_normalize_path($base_dir)) : '';
    $normalized_path = $path ? wp_normalize_path($path) : '';
    if (!$base_dir || !$path || strpos($normalized_path, $base_prefix) !== 0 || !is_readable($path)) {
        wp_die(__('File not found.', 'vaysf'), __('File not found', 'vaysf'), array('response' => 404));
    }

    nocache_headers();
    header('Content-Type: ' . $file['mime_type']);
    header('Content-Length: ' . filesize($path));
    $disposition = !empty($_GET['view']) ? 'inline' : 'attachment';
    header('Content-Disposition: ' . $disposition . '; filename="' . sanitize_file_name($file['original_filename']) . '"');
    readfile($path);
    exit;
}

/**
 * Build a score-form URL for a schedule row.
 *
 * @param mixed $schedule Schedule id, row array, or row object
 * @param string $view Dashboard return view
 * @param string $event_filter Optional event filter
 * @return string URL
 */
function vaysf_get_simple_score_form_url($schedule, $view = 'assigned', $event_filter = '') {
    $schedule_row = vaysf_resolve_schedule_row($schedule);
    $schedule_id = $schedule_row && !empty($schedule_row['schedule_id']) ? absint($schedule_row['schedule_id']) : absint($schedule);
    $url = vaysf_get_coordinator_score_entry_url($view, $event_filter);

    return add_query_arg(
        array(
            'action' => 'score',
            'schedule_id' => $schedule_id,
        ),
        $url
    );
}

/**
 * Build a stable QR-friendly score-form URL for a schedule row.
 *
 * @param mixed $schedule Schedule id, row array, or row object
 * @param string $view Dashboard return view
 * @param string $event_filter Optional event filter
 * @return string URL
 */
function vaysf_get_score_form_url_by_game_key($schedule, $view = 'assigned', $event_filter = '') {
    $schedule_row = vaysf_resolve_schedule_row($schedule);
    $game_key = $schedule_row && !empty($schedule_row['game_key'])
        ? sanitize_text_field($schedule_row['game_key'])
        : '';
    $url = vaysf_get_coordinator_score_entry_url($view, $event_filter);

    return add_query_arg(
        array(
            'action' => 'score',
            'game_key' => $game_key,
        ),
        $url
    );
}

/**
 * Persist a score payload to the current result row and append a revision.
 *
 * @param int $user_id WordPress user id
 * @param array<string,mixed> $schedule Schedule row
 * @param array<string,mixed> $score_payload Score payload for score_json
 * @param array<int,string> $winner_keys Winner team keys
 * @param string $notes Optional notes
 * @param string $correction_reason Correction label for repeat submissions
 * @return array<string,int>|WP_Error Result/revision identifiers on success
 */
function vaysf_persist_score_result($user_id, $schedule, $score_payload, $winner_keys, $notes = '', $correction_reason = '') {
    global $wpdb;

    $user_id = absint($user_id);
    $schedule_id = isset($schedule['schedule_id']) ? absint($schedule['schedule_id']) : 0;
    $notes = sanitize_textarea_field(wp_unslash($notes));
    $correction_reason = sanitize_textarea_field($correction_reason);
    if (!$user_id || !$schedule_id) {
        return new WP_Error('vaysf_score_missing_context', __('Score entry is missing the user or schedule row.', 'vaysf'));
    }

    $submitting_user = get_userdata($user_id);
    if ($submitting_user && !empty($submitting_user->user_login)) {
        $notes .= ' - Submitted by ' . $submitting_user->user_login;
    }

    $now = current_time('mysql');
    $score_payload['submitted_at'] = $now;
    $score_json = wp_json_encode($score_payload);
    $winner_keys_json = wp_json_encode($winner_keys);
    if ($score_json === false || $winner_keys_json === false) {
        return new WP_Error('vaysf_score_json_failed', __('Could not encode the score payload.', 'vaysf'));
    }

    $table_results = vaysf_get_table_name('results');
    $table_revisions = vaysf_get_table_name('result_revisions');
    $table_schedules = vaysf_get_table_name('schedules');
    $existing = vaysf_get_result_for_schedule($schedule_id);
    $source_ip = isset($_SERVER['REMOTE_ADDR']) ? sanitize_text_field(wp_unslash($_SERVER['REMOTE_ADDR'])) : '';
    $metadata = wp_json_encode(
        array(
            'source' => 'coordinator-score-entry',
            'user_id' => $user_id,
            'schedule_id' => $schedule_id,
        )
    );

    $wpdb->query('START TRANSACTION');

    if ($existing) {
        $result_id = absint($existing['result_id']);
        $next_revision = absint($existing['current_revision']) + 1;
    } else {
        $created = $wpdb->insert(
            $table_results,
            array(
                'schedule_id' => $schedule_id,
                'score_json' => $score_json,
                'winner_keys_json' => $winner_keys_json,
                'submitted_by_user_id' => $user_id,
                'certified_at' => $now,
                'current_revision' => 0,
                'public_status' => 'reported',
                'scan_status' => 'pending',
                'notes' => $notes,
                'created_at' => $now,
                'updated_at' => $now,
            ),
            array('%d', '%s', '%s', '%d', '%s', '%d', '%s', '%s', '%s', '%s', '%s')
        );
        if ($created === false) {
            $wpdb->query('ROLLBACK');
            return new WP_Error('vaysf_score_create_failed', __('Could not create the result row.', 'vaysf'));
        }
        $result_id = absint($wpdb->insert_id);
        $next_revision = 1;
    }

    $revision_created = $wpdb->insert(
        $table_revisions,
        array(
            'result_id' => $result_id,
            'revision_number' => $next_revision,
            'score_json' => $score_json,
            'winner_keys_json' => $winner_keys_json,
            'notes' => $notes,
            'correction_reason' => $existing ? $correction_reason : '',
            'submitted_by_user_id' => $user_id,
            'submitted_at' => $now,
            'verification_state' => 'unverified',
            'source_ip' => $source_ip,
            'request_metadata' => $metadata,
        ),
        array('%d', '%d', '%s', '%s', '%s', '%s', '%d', '%s', '%s', '%s', '%s')
    );

    if ($revision_created === false) {
        $wpdb->query('ROLLBACK');
        return new WP_Error('vaysf_score_revision_failed', __('Could not append the result revision.', 'vaysf'));
    }
    $revision_id = absint($wpdb->insert_id);

    $updated = $wpdb->update(
        $table_results,
        array(
            'schedule_id' => $schedule_id,
            'score_json' => $score_json,
            'winner_keys_json' => $winner_keys_json,
            'submitted_by_user_id' => $user_id,
            'certified_at' => $now,
            'current_revision' => $next_revision,
            'correction_reason' => $existing ? $correction_reason : '',
            'public_status' => 'reported',
            'scan_status' => 'pending',
            'notes' => $notes,
            'updated_at' => $now,
        ),
        array('result_id' => $result_id),
        array('%d', '%s', '%s', '%d', '%s', '%d', '%s', '%s', '%s', '%s', '%s'),
        array('%d')
    );

    if ($updated === false) {
        $wpdb->query('ROLLBACK');
        return new WP_Error('vaysf_score_update_failed', __('Could not update the current result row.', 'vaysf'));
    }

    $current_game_status = isset($schedule['game_status']) ? sanitize_text_field($schedule['game_status']) : '';
    $next_game_status = in_array($current_game_status, array('official', 'under_review'), true)
        ? $current_game_status
        : 'reported';
    $schedule_updated = $wpdb->update(
        $table_schedules,
        array(
            'game_status' => $next_game_status,
            'updated_at' => $now,
        ),
        array('schedule_id' => $schedule_id),
        array('%s', '%s'),
        array('%d')
    );

    if ($schedule_updated === false) {
        $wpdb->query('ROLLBACK');
        return new WP_Error('vaysf_score_schedule_update_failed', __('Could not mark the game as reported.', 'vaysf'));
    }

    $wpdb->query('COMMIT');
    return array(
        'result_id' => $result_id,
        'revision_id' => $revision_id,
        'revision_number' => $next_revision,
    );
}

/**
 * Submit or correct a simple two-team score from the coordinator dashboard.
 *
 * @param int $user_id WordPress user id
 * @param int $schedule_id Schedule row id
 * @param int $team_a_score Team A score
 * @param int $team_b_score Team B score
 * @param bool $certified Whether the submitter certified the score
 * @param string $notes Optional notes
 * @return array<string,int>|WP_Error Result/revision identifiers on success
 */
function vaysf_submit_simple_score_result($user_id, $schedule_id, $team_a_score, $team_b_score, $certified, $notes = '') {
    if (!is_int($team_a_score) || !is_int($team_b_score) || $team_a_score < 0 || $team_b_score < 0) {
        return new WP_Error('vaysf_simple_score_invalid_score', __('Scores must be whole numbers zero or greater.', 'vaysf'));
    }

    $schedule = vaysf_resolve_schedule_row($schedule_id);
    if (!$schedule) {
        return new WP_Error('vaysf_simple_score_schedule_missing', __('Schedule row not found.', 'vaysf'));
    }

    if (!vaysf_user_can_submit_schedule_result($user_id, $schedule)) {
        return new WP_Error('vaysf_simple_score_forbidden', __('You are not authorized to submit a score for this game.', 'vaysf'));
    }

    if (!vaysf_is_simple_score_schedule($schedule)) {
        return new WP_Error('vaysf_simple_score_unsupported', __('This game needs a sport-specific score form that is not enabled yet.', 'vaysf'));
    }

    if (!$certified) {
        return new WP_Error('vaysf_simple_score_uncertified', __('Please certify that the score is complete and accurate.', 'vaysf'));
    }

    $team_a_key = sanitize_text_field($schedule['team_a_key']);
    $team_b_key = sanitize_text_field($schedule['team_b_key']);
    $winner_keys = array();
    if ($team_a_score > $team_b_score) {
        $winner_keys[] = $team_a_key;
    } elseif ($team_b_score > $team_a_score) {
        $winner_keys[] = $team_b_key;
    }

    return vaysf_persist_score_result(
        absint($user_id),
        $schedule,
        array(
            'type' => 'simple_score',
            'team_a_key' => $team_a_key,
            'team_a_label' => sanitize_text_field($schedule['team_a_label'] ?? $team_a_key),
            'team_a_score' => $team_a_score,
            'team_b_key' => $team_b_key,
            'team_b_label' => sanitize_text_field($schedule['team_b_label'] ?? $team_b_key),
            'team_b_score' => $team_b_score,
            'is_tie' => $team_a_score === $team_b_score,
        ),
        $winner_keys,
        $notes,
        __('Coordinator score correction', 'vaysf')
    );
}

/**
 * Submit or correct a three-team Bible Challenge score.
 *
 * @param int $user_id WordPress user id
 * @param int $schedule_id Schedule row id
 * @param int $team_a_score Team A score
 * @param int $team_b_score Team B score
 * @param int $team_c_score Team C score
 * @param bool $certified Whether the submitter certified the score
 * @param string $notes Optional notes
 * @return array<string,int>|WP_Error Result/revision identifiers on success
 */
function vaysf_submit_three_team_score_result($user_id, $schedule_id, $team_a_score, $team_b_score, $team_c_score, $certified, $notes = '') {
    if (
        !is_int($team_a_score) || !is_int($team_b_score) || !is_int($team_c_score)
    ) {
        return new WP_Error('vaysf_three_team_score_invalid_score', __('Scores must be whole numbers. Negative scores are allowed for Bible Challenge.', 'vaysf'));
    }

    $schedule = vaysf_resolve_schedule_row($schedule_id);
    if (!$schedule) {
        return new WP_Error('vaysf_three_team_score_schedule_missing', __('Schedule row not found.', 'vaysf'));
    }

    if (!vaysf_user_can_submit_schedule_result($user_id, $schedule)) {
        return new WP_Error('vaysf_three_team_score_forbidden', __('You are not authorized to submit a score for this game.', 'vaysf'));
    }

    if (!vaysf_is_three_team_score_schedule($schedule)) {
        return new WP_Error('vaysf_three_team_score_unsupported', __('This game needs a different score form.', 'vaysf'));
    }

    if (!$certified) {
        return new WP_Error('vaysf_three_team_score_uncertified', __('Please certify that the score is complete and accurate.', 'vaysf'));
    }

    $team_a_key = sanitize_text_field($schedule['team_a_key']);
    $team_b_key = sanitize_text_field($schedule['team_b_key']);
    $team_c_key = sanitize_text_field($schedule['team_c_key']);
    $max_score = max($team_a_score, $team_b_score, $team_c_score);
    $winner_keys = array();
    if ($team_a_score === $max_score) {
        $winner_keys[] = $team_a_key;
    }
    if ($team_b_score === $max_score) {
        $winner_keys[] = $team_b_key;
    }
    if ($team_c_score === $max_score) {
        $winner_keys[] = $team_c_key;
    }

    return vaysf_persist_score_result(
        absint($user_id),
        $schedule,
        array(
            'type' => 'three_team_score',
            'team_a_key' => $team_a_key,
            'team_a_label' => sanitize_text_field($schedule['team_a_label'] ?? $team_a_key),
            'team_a_score' => $team_a_score,
            'team_b_key' => $team_b_key,
            'team_b_label' => sanitize_text_field($schedule['team_b_label'] ?? $team_b_key),
            'team_b_score' => $team_b_score,
            'team_c_key' => $team_c_key,
            'team_c_label' => sanitize_text_field($schedule['team_c_label'] ?? $team_c_key),
            'team_c_score' => $team_c_score,
            'is_tie' => count($winner_keys) > 1,
        ),
        $winner_keys,
        $notes,
        __('Coordinator Bible Challenge score correction', 'vaysf')
    );
}

/**
 * Submit or correct a volleyball set-based score.
 *
 * The first two sets are required. A tiebreaker is optional for preliminary
 * rows, which may end as a split match. Playoff-style rows still require a
 * deciding tiebreaker when the first two sets split. Set caps are intentionally
 * not enforced because Sports Fest may cap sets at 25-24 or lower when time is
 * tight.
 *
 * @param int $user_id WordPress user id
 * @param int $schedule_id Schedule row id
 * @param int $set_1_team_a_score Team A set 1 score
 * @param int $set_1_team_b_score Team B set 1 score
 * @param int $set_2_team_a_score Team A set 2 score
 * @param int $set_2_team_b_score Team B set 2 score
 * @param int|null $tiebreaker_team_a_score Optional Team A tiebreaker score
 * @param int|null $tiebreaker_team_b_score Optional Team B tiebreaker score
 * @param bool $certified Whether the submitter certified the score
 * @param string $notes Optional notes
 * @param bool $require_tiebreaker_for_split Whether a split must have a winner
 * @return array<string,int>|WP_Error Result/revision identifiers on success
 */
function vaysf_submit_volleyball_score_result(
    $user_id,
    $schedule_id,
    $set_1_team_a_score,
    $set_1_team_b_score,
    $set_2_team_a_score,
    $set_2_team_b_score,
    $tiebreaker_team_a_score,
    $tiebreaker_team_b_score,
    $certified,
    $notes = '',
    $require_tiebreaker_for_split = false
) {
    $required_scores = array(
        $set_1_team_a_score,
        $set_1_team_b_score,
        $set_2_team_a_score,
        $set_2_team_b_score,
    );
    foreach ($required_scores as $score) {
        if (!is_int($score) || $score < 0) {
            return new WP_Error('vaysf_volleyball_score_invalid_score', __('Scores must be whole numbers zero or greater.', 'vaysf'));
        }
    }

    $has_tiebreaker = $tiebreaker_team_a_score !== null || $tiebreaker_team_b_score !== null;
    if ($has_tiebreaker) {
        if (
            !is_int($tiebreaker_team_a_score)
            || !is_int($tiebreaker_team_b_score)
            || $tiebreaker_team_a_score < 0
            || $tiebreaker_team_b_score < 0
        ) {
            return new WP_Error('vaysf_volleyball_score_invalid_tiebreaker', __('Enter both tiebreaker scores as whole numbers, or leave both blank.', 'vaysf'));
        }
    }

    $schedule = vaysf_resolve_schedule_row($schedule_id);
    if (!$schedule) {
        return new WP_Error('vaysf_volleyball_score_schedule_missing', __('Schedule row not found.', 'vaysf'));
    }

    if (!vaysf_user_can_submit_schedule_result($user_id, $schedule)) {
        return new WP_Error('vaysf_volleyball_score_forbidden', __('You are not authorized to submit a score for this game.', 'vaysf'));
    }

    if (!vaysf_is_volleyball_score_schedule($schedule)) {
        return new WP_Error('vaysf_volleyball_score_unsupported', __('This game needs a different score form.', 'vaysf'));
    }

    if (!$certified) {
        return new WP_Error('vaysf_volleyball_score_uncertified', __('Please certify that the score is complete and accurate.', 'vaysf'));
    }

    $team_a_key = sanitize_text_field($schedule['team_a_key']);
    $team_b_key = sanitize_text_field($schedule['team_b_key']);
    $team_a_label = sanitize_text_field($schedule['team_a_label'] ?? $team_a_key);
    $team_b_label = sanitize_text_field($schedule['team_b_label'] ?? $team_b_key);
    $set_specs = array(
        array('number' => 1, 'label' => __('Set 1', 'vaysf'), 'team_a_score' => $set_1_team_a_score, 'team_b_score' => $set_1_team_b_score),
        array('number' => 2, 'label' => __('Set 2', 'vaysf'), 'team_a_score' => $set_2_team_a_score, 'team_b_score' => $set_2_team_b_score),
    );

    $sets = array();
    $team_a_sets_won = 0;
    $team_b_sets_won = 0;
    foreach ($set_specs as $set) {
        if ($set['team_a_score'] === $set['team_b_score']) {
            return new WP_Error('vaysf_volleyball_score_tied_set', __('Volleyball sets cannot end tied.', 'vaysf'));
        }

        $winner_key = $set['team_a_score'] > $set['team_b_score'] ? $team_a_key : $team_b_key;
        if ($winner_key === $team_a_key) {
            $team_a_sets_won++;
        } else {
            $team_b_sets_won++;
        }

        $sets[] = array(
            'number' => $set['number'],
            'label' => $set['label'],
            'team_a_score' => $set['team_a_score'],
            'team_b_score' => $set['team_b_score'],
            'winner_key' => $winner_key,
        );
    }

    $split_first_two_sets = $team_a_sets_won === $team_b_sets_won;
    $allows_split_match = vaysf_volleyball_allows_split_match($schedule);
    if ($split_first_two_sets && !$has_tiebreaker && ($require_tiebreaker_for_split || !$allows_split_match)) {
        return new WP_Error('vaysf_volleyball_score_tiebreaker_required', __('The first two sets are split, so enter the tiebreaker score or clear the strict winner checkbox.', 'vaysf'));
    }
    if (!$split_first_two_sets && $has_tiebreaker) {
        return new WP_Error('vaysf_volleyball_score_unneeded_tiebreaker', __('Only enter a tiebreaker when the first two sets are split.', 'vaysf'));
    }

    if ($has_tiebreaker) {
        if ($tiebreaker_team_a_score === $tiebreaker_team_b_score) {
            return new WP_Error('vaysf_volleyball_score_tied_tiebreaker', __('The tiebreaker cannot end tied.', 'vaysf'));
        }

        $winner_key = $tiebreaker_team_a_score > $tiebreaker_team_b_score ? $team_a_key : $team_b_key;
        if ($winner_key === $team_a_key) {
            $team_a_sets_won++;
        } else {
            $team_b_sets_won++;
        }

        $sets[] = array(
            'number' => 3,
            'label' => __('Tiebreaker', 'vaysf'),
            'team_a_score' => $tiebreaker_team_a_score,
            'team_b_score' => $tiebreaker_team_b_score,
            'winner_key' => $winner_key,
        );
    }

    $is_split_match = $team_a_sets_won === $team_b_sets_won;
    $winner_keys = array();
    if (!$is_split_match) {
        $winner_keys = $team_a_sets_won > $team_b_sets_won ? array($team_a_key) : array($team_b_key);
    }

    return vaysf_persist_score_result(
        absint($user_id),
        $schedule,
        array(
            'type' => 'volleyball_set_score',
            'team_a_key' => $team_a_key,
            'team_a_label' => $team_a_label,
            'team_a_score' => $team_a_sets_won,
            'team_a_sets_won' => $team_a_sets_won,
            'team_b_key' => $team_b_key,
            'team_b_label' => $team_b_label,
            'team_b_score' => $team_b_sets_won,
            'team_b_sets_won' => $team_b_sets_won,
            'sets' => $sets,
            'tiebreaker_played' => $has_tiebreaker,
            'strict_match_winner_required' => (bool) $require_tiebreaker_for_split,
            'split_match' => $is_split_match,
            'is_tie' => $is_split_match,
        ),
        $winner_keys,
        $notes,
        __('Coordinator Volleyball score correction', 'vaysf')
    );
}

/**
 * Submit or correct a final-placement result for Track & Field / Tug-of-War
 * (Issue #209).
 *
 * Unlike the other score forms, a placement schedule row has no
 * team_a_key/team_b_key — placements are entered fresh at submission time
 * as church codes and stored ordered 1st→3rd in winner_keys_json, following
 * the RFC §9.5 design of fitting placements into the existing data model.
 *
 * @param int $user_id WordPress user id
 * @param int $schedule_id Schedule row id
 * @param string $first_church_code Church code placing 1st (required)
 * @param string $second_church_code Church code placing 2nd (required)
 * @param string $third_church_code Church code placing 3rd (optional)
 * @param bool $certified Whether the submitter certified the result
 * @param string $notes Optional notes
 * @return array<string,int>|WP_Error Result/revision identifiers on success
 */
function vaysf_submit_placement_result($user_id, $schedule_id, $first_church_code, $second_church_code, $third_church_code, $certified, $notes = '') {
    $first_church_code = sanitize_text_field($first_church_code);
    $second_church_code = sanitize_text_field($second_church_code);
    $third_church_code = sanitize_text_field($third_church_code);

    if ($first_church_code === '' || $second_church_code === '') {
        return new WP_Error('vaysf_placement_missing_places', __('Enter at least 1st and 2nd place churches.', 'vaysf'));
    }

    $placements = array_values(array_filter(
        array($first_church_code, $second_church_code, $third_church_code),
        function ($code) {
            return $code !== '';
        }
    ));
    if (count($placements) !== count(array_unique($placements))) {
        return new WP_Error('vaysf_placement_duplicate_church', __('Each place must be a different church.', 'vaysf'));
    }

    $schedule = vaysf_resolve_schedule_row($schedule_id);
    if (!$schedule) {
        return new WP_Error('vaysf_placement_schedule_missing', __('Schedule row not found.', 'vaysf'));
    }

    if (!vaysf_user_can_submit_schedule_result($user_id, $schedule)) {
        return new WP_Error('vaysf_placement_forbidden', __('You are not authorized to submit a result for this event.', 'vaysf'));
    }

    if (!vaysf_is_placement_score_schedule($schedule)) {
        return new WP_Error('vaysf_placement_unsupported', __('This game needs a different score form.', 'vaysf'));
    }

    if (!$certified) {
        return new WP_Error('vaysf_placement_uncertified', __('Please certify that the placements are complete and accurate.', 'vaysf'));
    }

    return vaysf_persist_score_result(
        absint($user_id),
        $schedule,
        array(
            'type' => 'placement',
            'first_church_code' => $first_church_code,
            'second_church_code' => $second_church_code,
            'third_church_code' => $third_church_code !== '' ? $third_church_code : null,
        ),
        $placements,
        $notes,
        __('Coordinator placement correction', 'vaysf')
    );
}

/**
 * Query current-schedule rows assigned to a coordinator by event authorization.
 *
 * @param int $user_id WordPress user id
 * @param string $view needs|submitted|assigned
 * @param string $event_filter Optional event name to filter within authorized events
 * @return array<int,array<string,mixed>> Schedule/result rows for the dashboard
 */
function vaysf_get_coordinator_score_dashboard_rows($user_id, $view = 'needs', $event_filter = '') {
    global $wpdb;

    $user_id = absint($user_id);
    if (!$user_id || !user_can($user_id, 'sf2025_submit_results')) {
        return array();
    }

    $authorized_events = vaysf_get_user_score_entry_events($user_id);
    if (!$authorized_events) {
        return array();
    }

    $event_filter = sanitize_text_field($event_filter);
    if ($event_filter !== '') {
        if (!in_array($event_filter, $authorized_events, true)) {
            return array();
        }
        $authorized_events = array($event_filter);
    }

    $current_version = vaysf_get_current_published_schedule_version();
    if ($current_version === null) {
        return array();
    }

    $view = sanitize_key($view);
    if (!in_array($view, array('needs', 'submitted', 'assigned'), true)) {
        $view = 'needs';
    }

    $table_schedules = vaysf_get_table_name('schedules');
    $table_results = vaysf_get_table_name('results');
    $event_placeholders = implode(', ', array_fill(0, count($authorized_events), '%s'));

    $where = array(
        's.schedule_version = %d',
        's.published_at IS NOT NULL',
        "COALESCE(s.game_status, '') <> 'cancelled'",
        "s.event IN ($event_placeholders)",
    );
    $args = array_merge(array($current_version), $authorized_events);

    $now = current_time('timestamp');
    $today_start = date('Y-m-d 00:00:00', $now);
    $tomorrow_start = date('Y-m-d 00:00:00', strtotime('+1 day', $now));
    $today_end = date('Y-m-d 23:59:59', $now);

    if ($view === 'needs') {
        $where[] = 'r.result_id IS NULL';
        $where[] = 's.scheduled_time IS NOT NULL';
        $where[] = 's.scheduled_time <= %s';
        $args[] = $today_end;
    } elseif ($view === 'submitted') {
        $where[] = 'r.updated_at >= %s';
        $where[] = 'r.updated_at < %s';
        if (!vaysf_user_has_all_score_entry_events($user_id)) {
            $where[] = 'r.submitted_by_user_id = %d';
        }
        $args[] = $today_start;
        $args[] = $tomorrow_start;
        if (!vaysf_user_has_all_score_entry_events($user_id)) {
            $args[] = $user_id;
        }
    }

    $sql = "
        SELECT
            s.*,
            r.result_id,
            r.score_json,
            r.public_status,
            r.scan_status,
            r.submitted_by_user_id,
            r.certified_at,
            r.verified_at,
            r.created_at AS result_created_at,
            r.updated_at AS result_updated_at
        FROM $table_schedules s
        LEFT JOIN $table_results r ON r.schedule_id = s.schedule_id
        WHERE " . implode(' AND ', $where) . "
        ORDER BY s.scheduled_time IS NULL, s.scheduled_time, s.event, s.game_key
    ";

    $rows = $wpdb->get_results($wpdb->prepare($sql, $args), ARRAY_A);
    if (!is_array($rows)) {
        return array();
    }

    $missing_result_rows = array();
    foreach ($rows as $row) {
        if (trim((string) ($row['score_json'] ?? '')) === '' && !empty($row['schedule_id'])) {
            $missing_result_rows[] = $row;
        }
    }

    $fallback_results = vaysf_get_result_fallbacks_for_schedule_rows($missing_result_rows);
    $resolved_rows = array();
    foreach ($rows as $row) {
        $schedule_id = !empty($row['schedule_id']) ? absint($row['schedule_id']) : 0;
        if (trim((string) ($row['score_json'] ?? '')) === '' && $schedule_id && !empty($fallback_results[$schedule_id])) {
            $fallback = $fallback_results[$schedule_id];
            foreach (array(
                'result_id', 'score_json', 'public_status', 'scan_status',
                'submitted_by_user_id', 'certified_at', 'verified_at',
                'result_created_at', 'result_updated_at',
            ) as $field) {
                if (isset($fallback[$field])) {
                    $row[$field] = $fallback[$field];
                }
            }
        }

        if (
            trim((string) ($row['score_json'] ?? '')) !== ''
            && (empty($row['public_status']) || $row['public_status'] === 'pending')
        ) {
            $row['public_status'] = 'reported';
        }

        if ($view === 'needs' && trim((string) ($row['score_json'] ?? '')) !== '') {
            continue;
        }

        $resolved_rows[] = $row;
    }

    return $resolved_rows;
}

/**
 * Get pool/prelim progress rows visible to one score-entry user.
 *
 * Reuses the Results Desk provisional ranking helper, but keeps ordinary
 * coordinators limited to their authorized schedule events.
 *
 * @param int $user_id WordPress user id
 * @param string $event_filter Optional event name to filter within authorized events
 * @param int $limit Maximum pool groups
 * @return array<int,array<string,mixed>>
 */
function vaysf_get_coordinator_score_pool_progress_rows($user_id, $event_filter = '', $limit = 200) {
    $user_id = absint($user_id);
    if (
        !$user_id
        || !user_can($user_id, 'sf2025_submit_results')
        || !function_exists('vaysf_get_results_desk_pool_progress_rows')
    ) {
        return array();
    }

    $authorized_events = vaysf_get_user_score_entry_events($user_id);
    if (!$authorized_events) {
        return array();
    }

    $event_filter = sanitize_text_field($event_filter);
    if ($event_filter !== '') {
        if (!in_array($event_filter, $authorized_events, true)) {
            return array();
        }

        return vaysf_get_results_desk_pool_progress_rows(
            array(
                'event' => $event_filter,
                'limit' => $limit,
            ),
            $limit
        );
    }

    if (vaysf_user_has_all_score_entry_events($user_id)) {
        return vaysf_get_results_desk_pool_progress_rows(array('limit' => $limit), $limit);
    }

    $pool_rows = array();
    foreach ($authorized_events as $authorized_event) {
        $pool_rows = array_merge(
            $pool_rows,
            vaysf_get_results_desk_pool_progress_rows(
                array(
                    'event' => $authorized_event,
                    'limit' => $limit,
                ),
                $limit
            )
        );
    }

    return array_slice($pool_rows, 0, max(1, min(absint($limit), 200)));
}

/**
 * Build the coordinator score entry URL.
 *
 * @param string $view Dashboard view key
 * @param string $event_filter Optional event filter
 * @return string URL
 */
function vaysf_get_coordinator_score_entry_url($view = 'assigned', $event_filter = '') {
    $view = sanitize_key($view);
    if (!in_array($view, array('needs', 'submitted', 'assigned'), true)) {
        $view = 'assigned';
    }

    $args = array('view' => $view);
    $event_filter = sanitize_text_field($event_filter);
    if ($event_filter !== '') {
        $args['event'] = $event_filter;
    }

    return add_query_arg($args, site_url('coordinator-score-entry'));
}

/**
 * Register a wp-admin dashboard widget for coordinator accounts.
 *
 * @return void
 */
function vaysf_register_coordinator_score_dashboard_widget() {
    if (!current_user_can('sf2025_submit_results')) {
        return;
    }

    wp_add_dashboard_widget(
        'vaysf_coordinator_score_entry',
        esc_html__('Sports Fest Score Entry', 'vaysf'),
        'vaysf_render_coordinator_score_dashboard_widget'
    );

    global $wp_meta_boxes;
    if (empty($wp_meta_boxes['dashboard']['normal']['core']['vaysf_coordinator_score_entry'])) {
        return;
    }

    $widget = $wp_meta_boxes['dashboard']['normal']['core']['vaysf_coordinator_score_entry'];
    unset($wp_meta_boxes['dashboard']['normal']['core']['vaysf_coordinator_score_entry']);
    $wp_meta_boxes['dashboard']['normal']['core'] = array(
        'vaysf_coordinator_score_entry' => $widget,
    ) + $wp_meta_boxes['dashboard']['normal']['core'];
}

/**
 * Render the coordinator dashboard widget.
 *
 * @return void
 */
function vaysf_render_coordinator_score_dashboard_widget() {
    $authorized_events = vaysf_get_user_score_entry_events(get_current_user_id());
    $dashboard_url = vaysf_get_coordinator_score_entry_url('assigned');
    ?>
    <p><?php esc_html_e('Open your assigned Sports Fest games from the coordinator dashboard. Basketball, Soccer-style, Bible Challenge, and Volleyball scores can be submitted now; other sport forms are coming in later slices.', 'vaysf'); ?></p>
    <?php if ($authorized_events) : ?>
        <p>
            <strong><?php esc_html_e('Assigned events:', 'vaysf'); ?></strong>
            <?php echo esc_html(implode(', ', $authorized_events)); ?>
        </p>
    <?php else : ?>
        <p><?php esc_html_e('No schedule events have been assigned to your coordinator account yet.', 'vaysf'); ?></p>
    <?php endif; ?>
    <p>
        <a class="button button-primary" href="<?php echo esc_url($dashboard_url); ?>">
            <?php esc_html_e('Open Score Entry Dashboard', 'vaysf'); ?>
        </a>
    </p>
    <?php
}

/**
 * Keep the score-entry dashboard widget first for coordinator-capable users.
 *
 * @param mixed $result Dashboard metabox order user option
 * @param string $option Option name
 * @param WP_User $user User object
 * @return mixed Updated option value
 */
function vaysf_prepend_coordinator_dashboard_widget_order($result, $option, $user) {
    if (!is_object($user) || !user_can($user->ID, 'sf2025_submit_results')) {
        return $result;
    }

    if (!is_array($result)) {
        $result = array();
    }

    $widget_id = 'vaysf_coordinator_score_entry';
    foreach (array('normal', 'side', 'column3', 'column4') as $column) {
        $ids = array();
        if (!empty($result[$column])) {
            $ids = array_filter(array_map('trim', explode(',', $result[$column])));
        }
        $ids = array_values(array_diff($ids, array($widget_id)));
        $result[$column] = implode(',', $ids);
    }

    $normal_ids = !empty($result['normal'])
        ? array_filter(array_map('trim', explode(',', $result['normal'])))
        : array();
    array_unshift($normal_ids, $widget_id);
    $result['normal'] = implode(',', array_values(array_unique($normal_ids)));

    return $result;
}

/**
 * Keep the score-entry dashboard widget visible for result-entry users.
 *
 * @param mixed $result Hidden metabox user option
 * @param string $option Option name
 * @param WP_User $user User object
 * @return mixed Updated hidden metabox list
 */
function vaysf_show_coordinator_dashboard_widget($result, $option, $user) {
    if (!is_object($user) || !user_can($user->ID, 'sf2025_submit_results')) {
        return $result;
    }

    $widget_id = 'vaysf_coordinator_score_entry';
    if (!is_array($result)) {
        return $result;
    }

    return array_values(array_diff($result, array($widget_id)));
}

/**
 * Render a coordinator score-entry link on user profile screens.
 *
 * @param WP_User $user User being viewed
 * @return void
 */
function vaysf_render_coordinator_score_profile_link($user) {
    if (!user_can($user->ID, 'sf2025_submit_results')) {
        return;
    }

    if ((int) get_current_user_id() !== (int) $user->ID && !current_user_can('edit_user', $user->ID)) {
        return;
    }

    $dashboard_url = vaysf_get_coordinator_score_entry_url('assigned');
    ?>
    <h2><?php esc_html_e('Sports Fest Score Entry', 'vaysf'); ?></h2>
    <table class="form-table" role="presentation">
        <tr>
            <th scope="row"><?php esc_html_e('Coordinator dashboard', 'vaysf'); ?></th>
            <td>
                <p>
                    <a class="button button-primary" href="<?php echo esc_url($dashboard_url); ?>">
                        <?php esc_html_e('Open Score Entry Dashboard', 'vaysf'); ?>
                    </a>
                </p>
                <p class="description">
                    <?php esc_html_e('This page shows the published games assigned to this coordinator account.', 'vaysf'); ?>
                </p>
            </td>
        </tr>
    </table>
    <?php
}

/**
 * Render user-profile controls for schedule-driven coordinator authorization.
 *
 * @param WP_User $user User being edited
 * @return void
 */
function vaysf_render_coordinator_authorization_fields($user) {
    if (!current_user_can('edit_user', $user->ID) || (!current_user_can('promote_users') && !current_user_can('manage_options'))) {
        return;
    }

    $current_version = vaysf_get_current_published_schedule_version();
    $available_events = vaysf_get_published_schedule_events($current_version);
    $authorized_events = vaysf_get_user_authorized_events($user->ID);
    $stale_events = array_values(array_diff($authorized_events, $available_events));
    ?>
    <h2><?php esc_html_e('Sports Fest Result Authorization', 'vaysf'); ?></h2>
    <table class="form-table" role="presentation">
        <tr>
            <th scope="row"><?php esc_html_e('Authorized schedule events', 'vaysf'); ?></th>
            <td>
                <?php wp_nonce_field('vaysf_save_coordinator_authorization_' . $user->ID, 'vaysf_coordinator_authorization_nonce'); ?>
                <?php if ($current_version === null || !$available_events) : ?>
                    <p class="description">
                        <?php esc_html_e('No published Sports Fest schedule events are available yet. Publish the approved schedule before assigning coordinator event access.', 'vaysf'); ?>
                    </p>
                <?php else : ?>
                    <p class="description">
                        <?php
                        printf(
                            esc_html__('Options come from published schedule version %d. Select the events this user may submit results for.', 'vaysf'),
                            absint($current_version)
                        );
                        ?>
                    </p>
                    <fieldset>
                        <?php foreach ($available_events as $event) : ?>
                            <label>
                                <input
                                    type="checkbox"
                                    name="vaysf_authorized_events[]"
                                    value="<?php echo esc_attr($event); ?>"
                                    <?php checked(in_array($event, $authorized_events, true)); ?>
                                >
                                <?php echo esc_html($event); ?>
                            </label><br>
                        <?php endforeach; ?>
                    </fieldset>
                    <?php if (!user_can($user->ID, 'sf2025_submit_results')) : ?>
                        <p class="description">
                            <?php esc_html_e('This user does not currently have sf2025_submit_results. Assign a Sports Fest Coordinator, Manager, or Admin role before relying on these selections.', 'vaysf'); ?>
                        </p>
                    <?php endif; ?>
                <?php endif; ?>
                <?php if ($stale_events) : ?>
                    <p class="description">
                        <?php
                        printf(
                            esc_html__('Previously saved event authorization no longer appears in the current published schedule: %s', 'vaysf'),
                            esc_html(implode(', ', $stale_events))
                        );
                        ?>
                    </p>
                <?php endif; ?>
            </td>
        </tr>
    </table>
    <?php
}

/**
 * Save user-profile schedule-event authorization.
 *
 * @param int $user_id User being edited
 * @return void
 */
function vaysf_save_coordinator_authorization_fields($user_id) {
    $user_id = absint($user_id);
    if (!$user_id || !current_user_can('edit_user', $user_id) || (!current_user_can('promote_users') && !current_user_can('manage_options'))) {
        return;
    }

    if (
        empty($_POST['vaysf_coordinator_authorization_nonce'])
        || !wp_verify_nonce(
            sanitize_text_field(wp_unslash($_POST['vaysf_coordinator_authorization_nonce'])),
            'vaysf_save_coordinator_authorization_' . $user_id
        )
    ) {
        return;
    }

    $selected_events = array();
    if (!empty($_POST['vaysf_authorized_events']) && is_array($_POST['vaysf_authorized_events'])) {
        $selected_events = wp_unslash($_POST['vaysf_authorized_events']);
    }

    vaysf_update_user_authorized_events($user_id, $selected_events);
}

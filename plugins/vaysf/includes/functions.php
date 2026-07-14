<?php
/**
 * File: includes/functions.php
 * Description: Helper functions for VAYSF Integration
 * Version: 1.0.8
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
 * Get table name
 * 
 * @param string $table Table name without prefix
 * @return string Full table name with prefix
 */
function vaysf_get_table_name($table) {
    global $wpdb;
    return $wpdb->prefix . 'sf_' . $table;
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
 * Check whether a schedule row currently has any coordinator score form.
 *
 * @param mixed $schedule Schedule id, row array, or row object
 * @return bool True when a supported score-entry form exists
 */
function vaysf_is_supported_score_schedule($schedule) {
    return vaysf_is_simple_score_schedule($schedule)
        || vaysf_is_three_team_score_schedule($schedule)
        || vaysf_is_volleyball_score_schedule($schedule);
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

    return is_array($result) ? $result : null;
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
 * Persist a score payload to the current result row and append a revision.
 *
 * @param int $user_id WordPress user id
 * @param array<string,mixed> $schedule Schedule row
 * @param array<string,mixed> $score_payload Score payload for score_json
 * @param array<int,string> $winner_keys Winner team keys
 * @param string $notes Optional notes
 * @param string $correction_reason Correction label for repeat submissions
 * @return true|WP_Error True on success
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
    return true;
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
 * @return true|WP_Error True on success
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
 * @return true|WP_Error True on success
 */
function vaysf_submit_three_team_score_result($user_id, $schedule_id, $team_a_score, $team_b_score, $team_c_score, $certified, $notes = '') {
    if (
        !is_int($team_a_score) || !is_int($team_b_score) || !is_int($team_c_score)
        || $team_a_score < 0 || $team_b_score < 0 || $team_c_score < 0
    ) {
        return new WP_Error('vaysf_three_team_score_invalid_score', __('Scores must be whole numbers zero or greater.', 'vaysf'));
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
 * The first two sets are required. A tiebreaker is required only when the
 * first two sets split. Set caps are intentionally not enforced because Sports
 * Fest may cap sets at 25-24 or lower when time is tight.
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
 * @return true|WP_Error True on success
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
    $notes = ''
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
    if ($split_first_two_sets && !$has_tiebreaker) {
        return new WP_Error('vaysf_volleyball_score_tiebreaker_required', __('The first two sets are split, so enter the tiebreaker score.', 'vaysf'));
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

    $winner_keys = $team_a_sets_won > $team_b_sets_won ? array($team_a_key) : array($team_b_key);

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
            'is_tie' => false,
        ),
        $winner_keys,
        $notes,
        __('Coordinator Volleyball score correction', 'vaysf')
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
            r.public_status,
            r.scan_status,
            r.submitted_by_user_id,
            r.certified_at,
            r.verified_at,
            r.created_at AS result_created_at
        FROM $table_schedules s
        LEFT JOIN $table_results r ON r.schedule_id = s.schedule_id
        WHERE " . implode(' AND ', $where) . "
        ORDER BY s.scheduled_time IS NULL, s.scheduled_time, s.event, s.game_key
    ";

    $rows = $wpdb->get_results($wpdb->prepare($sql, $args), ARRAY_A);
    return is_array($rows) ? $rows : array();
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

/**
 * Log sync request for churches
 * 
 * @return bool Success status
 */
 // In functions.php:
function vaysf_sync_churches() {
    global $wpdb;
    $table_name = vaysf_get_table_name('sync_log');
    
    return $wpdb->insert($table_name, array(
        'sync_type' => 'churches',
        'direction' => 'to_wp',
        'records_processed' => 0,
        'success_count' => 0,
        'error_count' => 0,
        'error_details' => 'Middleware sync requested via admin UI',
        'started_at' => current_time('mysql'),
        'completed_at' => null,
        'status' => 'pending'
    ));
}

/**
 * Log sync request for participants
 * 
 * @return bool Success status
 */
function vaysf_sync_participants() {
    global $wpdb;
    $table_name = vaysf_get_table_name('sync_log');
    
    return $wpdb->insert($table_name, array(
        'sync_type' => 'participants',
        'direction' => 'to_wp',
        'records_processed' => 0,
        'success_count' => 0,
        'error_count' => 0,
        'error_details' => 'Middleware sync requested via admin UI',
        'started_at' => current_time('mysql'),
        'completed_at' => null
    ));
}

/**
 * Log sync request for approvals
 * 
 * @return bool Success status
 */
function vaysf_generate_approvals() {
    global $wpdb;
    $table_name = vaysf_get_table_name('sync_log');
    
    return $wpdb->insert($table_name, array(
        'sync_type' => 'approvals',
        'direction' => 'to_wp',
        'records_processed' => 0,
        'success_count' => 0,
        'error_count' => 0,
        'error_details' => 'Approval token generation requested via admin UI',
        'started_at' => current_time('mysql'),
        'completed_at' => null
    ));
}

/**
 * Log validation request
 * 
 * @return bool Success status
 */
function vaysf_validate_data() {
    global $wpdb;
    $table_name = vaysf_get_table_name('sync_log');
    
    return $wpdb->insert($table_name, array(
        'sync_type' => 'validation',
        'direction' => 'to_wp',
        'records_processed' => 0,
        'success_count' => 0,
        'error_count' => 0,
        'error_details' => 'Data validation requested via admin UI',
        'started_at' => current_time('mysql'),
        'completed_at' => null
    ));
}

/**
 * Format validation severity
 * 
 * @param string $severity Validation severity
 * @return string Formatted severity
 */
function vaysf_format_validation_severity($severity) {
    switch ($severity) {
        case 'ERROR':
            return '<span class="validation-severity severity-error">' . esc_html__('Error', 'vaysf') . '</span>';
        case 'WARNING':
            return '<span class="validation-severity severity-warning">' . esc_html__('Warning', 'vaysf') . '</span>';
        case 'INFO':
            return '<span class="validation-severity severity-info">' . esc_html__('Info', 'vaysf') . '</span>';
        default:
            return '<span class="validation-severity severity-error">' . esc_html__('Error', 'vaysf') . '</span>';
    }
}

/**
 * Format validation status
 * 
 * @param string $status Validation status
 * @return string Formatted status
 */
function vaysf_format_validation_status($status) {
    switch ($status) {
        case 'resolved':
            return '<span class="validation-status status-resolved">' . esc_html__('Resolved', 'vaysf') . '</span>';
        case 'open':
        default:
            return '<span class="validation-status status-open">' . esc_html__('Open', 'vaysf') . '</span>';
    }
}

/**
 * Format approval status
 * 
 * @param string $status Approval status
 * @return string Formatted status
 */
function vaysf_format_approval_status($status) {
    switch ($status) {
        case 'approved':
            return '<span class="approval-status status-approved">' . esc_html__('Approved', 'vaysf') . '</span>';
        case 'denied':
            return '<span class="approval-status status-denied">' . esc_html__('Denied', 'vaysf') . '</span>';
        case 'validated':
            return '<span class="approval-status status-validated">' . esc_html__('Validated', 'vaysf') . '</span>';
        case 'pending_approval':
            return '<span class="approval-status status-pending-approval">' . esc_html__('Pending Approval', 'vaysf') . '</span>';
        case 'pending':
        default:
            return '<span class="approval-status status-pending">' . esc_html__('Pending', 'vaysf') . '</span>';
    }
}

/**
 * Get church by ID
 * 
 * @param int $church_id Church ID
 * @return object|false Church object or false if not found
 */
function vaysf_get_church($church_id) {
    global $wpdb;
    
    $table_name = vaysf_get_table_name('churches');
    
    return $wpdb->get_row(
        $wpdb->prepare("SELECT * FROM $table_name WHERE church_id = %d", $church_id)
    );
}

/**
 * Get participant by ID
 * 
 * @param int $participant_id Participant ID
 * @return object|false Participant object or false if not found
 */
function vaysf_get_participant($participant_id) {
    global $wpdb;
    
    $table_name = vaysf_get_table_name('participants');
    
    return $wpdb->get_row(
        $wpdb->prepare("SELECT * FROM $table_name WHERE participant_id = %d", $participant_id)
    );
}

/**
 * Get participant link
 * 
 * @param int $participant_id Participant ID
 * @param string $text Link text (optional)
 * @return string HTML link
 */
function vaysf_get_participant_link($participant_id, $text = '') {
    $participant = vaysf_get_participant($participant_id);
    
    if (!$participant) {
        return esc_html__('Unknown', 'vaysf');
    }
    
    if (empty($text)) {
        $text = esc_html($participant->first_name . ' ' . $participant->last_name);
    }
    
    $url = admin_url('admin.php?page=vaysf-participants&action=edit&id=' . $participant_id);
    
    return '<a href="' . esc_url($url) . '">' . $text . '</a>';
}

/**
 * Get church link
 * 
 * @param int $church_id Church ID
 * @param string $text Link text (optional)
 * @return string HTML link
 */
function vaysf_get_church_link($church_id, $text = '') {
    $church = vaysf_get_church($church_id);
    
    if (!$church) {
        return esc_html__('Unknown', 'vaysf');
    }
    
    if (empty($text)) {
        $text = esc_html($church->church_name);
    }
    
    $url = admin_url('admin.php?page=vaysf-churches&action=edit&id=' . $church_id);
    
    return '<a href="' . esc_url($url) . '">' . $text . '</a>';
}

/**
 * Sanitize and validate age
 * 
 * @param mixed $age Age value
 * @return int Sanitized age
 */
function vaysf_sanitize_age($age) {
    $age = intval($age);
    
    if ($age < 0) {
        $age = 0;
    }
    
    if ($age > 120) {
        $age = 120;
    }
    
    return $age;
}

/**
 * Calculate age from birthdate
 * 
 * @param string $birthdate Birthdate in Y-m-d format
 * @return int Age
 */
function vaysf_calculate_age($birthdate) {
    $birth_date = new DateTime($birthdate);
    $today = new DateTime();
    $age = $birth_date->diff($today)->y;
    
    return $age;
}

/**
 * Check if sport has an age exception
 * 
 * @param string $sport Sport name
 * @param int $age Age to check
 * @return bool True if age exception applies
 */
function vaysf_has_age_exception($sport, $age) {
    unset($age); // Helper answers whether the event has an exception, not whether age already qualifies.

    return in_array($sport, array(
        'Scripture Memorization',
        'Tug-of-war',
        'Pickleball 35+',
        'Table Tennis 35+',
    ), true);
}

/**
 * Get roster by ID
 * 
 * @param int $roster_id Roster ID
 * @return object|false Roster object or false if not found
 */
function vaysf_get_roster($roster_id) {
    global $wpdb;
    
    $table_name = vaysf_get_table_name('rosters');
    
    return $wpdb->get_row(
        $wpdb->prepare("SELECT * FROM $table_name WHERE roster_id = %d", $roster_id)
    );
}

/**
 * Get rosters by participant ID
 * 
 * @param int $participant_id Participant ID
 * @return array Array of roster objects
 */
function vaysf_get_rosters_by_participant($participant_id) {
    global $wpdb;
    
    $table_name = vaysf_get_table_name('rosters');
    
    return $wpdb->get_results(
        $wpdb->prepare("SELECT * FROM $table_name WHERE participant_id = %d", $participant_id),
        ARRAY_A
    );
}

/**
 * Get rosters by church code
 * 
 * @param string $church_code Church code
 * @return array Array of roster objects
 */
function vaysf_get_rosters_by_church($church_code) {
    global $wpdb;
    
    $table_name = vaysf_get_table_name('rosters');
    
    return $wpdb->get_results(
        $wpdb->prepare("SELECT * FROM $table_name WHERE church_code = %s", $church_code),
        ARRAY_A
    );
}

/**
 * Get sport options
 * 
 * @return array Sport options
 */
function vaysf_get_sport_options() {
    return array(
        '' => __('None', 'vaysf'),
        'Badminton' => __('Badminton', 'vaysf'),
        'Basketball - Men Team' => __('Basketball - Men Team', 'vaysf'),
        'Bible Challenge - Mixed Team' => __('Bible Challenge - Mixed Team', 'vaysf'),
        'Pickleball' => __('Pickleball', 'vaysf'),
        'Pickleball 35+' => __('Pickleball 35+', 'vaysf'),
        'Scripture Memorization' => __('Scripture Memorization', 'vaysf'),
        'Table Tennis' => __('Table Tennis', 'vaysf'),
        'Table Tennis 35+' => __('Table Tennis 35+', 'vaysf'),
        'Tennis' => __('Tennis', 'vaysf'),
        'Track & Field' => __('Track & Field', 'vaysf'),
        'Tug-of-war' => __('Tug-of-war', 'vaysf'),
        'Volleyball - Men Team' => __('Volleyball - Men Team', 'vaysf'),
        'Volleyball - Women Team' => __('Volleyball - Women Team', 'vaysf'),
    );
}

/**
 * Get format options for racquet sports
 * 
 * @param string $sport Sport name
 * @return array Format options
 */
function vaysf_get_format_options($sport) {
    switch ($sport) {
        case 'Tennis':
        case 'Pickleball':
        case 'Pickleball 35+':
        case 'Table Tennis':
        case 'Table Tennis 35+':
        case 'Badminton':
            return array(
                'Singles' => __('Singles', 'vaysf'),
                'Doubles' => __('Doubles', 'vaysf'),
                'Mixed Doubles' => __('Mixed Doubles', 'vaysf'),
            );
        default:
            return array();
    }
}

/**
 * Get team sports
 * 
 * @return array Team sports
 */
function vaysf_get_team_sports() {
    return array(
        'Basketball - Men Team',
        'Volleyball - Men Team',
        'Volleyball - Women Team',
        'Bible Challenge - Mixed Team',
    );
}

/**
 * Get individual sports
 * 
 * @return array Individual sports
 */
function vaysf_get_individual_sports() {
    return array(
        'Badminton',
        'Tennis',
        'Pickleball',
        'Pickleball 35+',
        'Table Tennis',
        'Table Tennis 35+',
        'Track & Field',
        'Scripture Memorization',
        'Tug-of-war',
    );
}

/**
 * Check if sport is a team sport
 * 
 * @param string $sport Sport name
 * @return bool True if team sport
 */
function vaysf_is_team_sport($sport) {
    return in_array($sport, vaysf_get_team_sports());
}

/**
 * Check if sport is an individual sport
 * 
 * @param string $sport Sport name
 * @return bool True if individual sport
 */
function vaysf_is_individual_sport($sport) {
    return in_array($sport, vaysf_get_individual_sports());
}

/**
 * Check if sport is a racquet sport
 * 
 * @param string $sport Sport name
 * @return bool True if racquet sport
 */
function vaysf_is_racquet_sport($sport) {
    return in_array($sport, array(
        'Tennis',
        'Pickleball',
        'Pickleball 35+',
        'Table Tennis',
        'Table Tennis 35+',
        'Badminton',
    ), true);
}

/**
 * Normalize a recipient list for Cc/Bcc headers.
 *
 * @param string|array $emails Recipient email(s) as an array or comma-separated string
 * @return array Sanitized unique email addresses
 */
function vaysf_normalize_email_list($emails) {
    if (empty($emails)) {
        return array();
    }

    if (!is_array($emails)) {
        $emails = preg_split('/[;,]+/', (string) $emails);
    }

    $normalized = array();
    foreach ($emails as $email) {
        $sanitized = sanitize_email(trim((string) $email));
        if (!empty($sanitized)) {
            $normalized[] = $sanitized;
        }
    }

    return array_values(array_unique($normalized));
}

/**
 * Build a valid From header from a plain email or "Name <email>" string.
 *
 * @param string $from Sender identity supplied by the caller
 * @return string Fully formatted From header
 */
function vaysf_build_from_header($from = '') {
    $from = trim((string) $from);

    if (!empty($from) && preg_match('/^(.*)<([^>]+)>$/', $from, $matches)) {
        $from_name = sanitize_text_field(trim($matches[1], " \t\n\r\0\x0B\"'"));
        $from_email = sanitize_email(trim($matches[2]));
        if (!empty($from_email)) {
            return !empty($from_name)
                ? 'From: ' . $from_name . ' <' . $from_email . '>'
                : 'From: ' . $from_email;
        }
    }

    $from_email = sanitize_email($from);
    if (!empty($from_email)) {
        return 'From: ' . $from_email;
    }

    $default_from_email = sanitize_email(get_option('vaysf_email_from', get_option('admin_email')));
    return 'From: Sports Fest <' . $default_from_email . '>';
}

/**
 * Build HTML mail headers with optional From/Cc/Bcc entries.
 *
 * @param array $args Optional arguments (from, cc, bcc)
 * @return array Ready-to-send wp_mail() headers
 */
function vaysf_build_mail_headers($args = array()) {
    $from = isset($args['from']) ? $args['from'] : '';
    $cc_list = isset($args['cc']) ? $args['cc'] : array();
    $bcc_list = isset($args['bcc']) ? $args['bcc'] : array();

    $headers = array(
        'Content-Type: text/html; charset=UTF-8',
        vaysf_build_from_header($from)
    );

    foreach (vaysf_normalize_email_list($cc_list) as $cc_email) {
        $headers[] = 'Cc: ' . $cc_email;
    }

    foreach (vaysf_normalize_email_list($bcc_list) as $bcc_email) {
        $headers[] = 'Bcc: ' . $bcc_email;
    }

    return $headers;
}

/**
 * Send an email and optionally log it in the database
 *
 * @param string $to      Recipient email address
 * @param string $subject Email subject line
 * @param string $message HTML email body
 * @param array  $args    Optional arguments (from, cc, bcc)
 * @return bool True if email was sent successfully
 */
function vaysf_send_email($to, $subject, $message, $args = array()) {
    $to = sanitize_email($to);
    $subject = sanitize_text_field($subject);
    $message = wp_kses_post($message);
    $headers = vaysf_build_mail_headers($args);

    $sent = wp_mail($to, $subject, $message, $headers);

    if (get_option('vaysf_log_emails', false)) {
        global $wpdb;
        $table_name = $wpdb->prefix . 'sf_email_log';
        $wpdb->insert($table_name, array(
            'to_email' => $to,
            'subject'  => $subject,
            'message'  => $message,
            'sent_at'  => current_time('mysql'),
            'status'   => $sent ? 'sent' : 'failed'
        ));
    }

    return $sent;
}

/**
 * Resend pastor approval email for a given approval record
 * Updated to match the original email logic from the middleware
 * Generates fresh token and resets approval status to 'pending'
 *
 * @param array $approval Approval record with participant and church info
 * @return bool True if email sent
 */
function vaysf_resend_approval_email($approval) {
    global $wpdb;
    
    // Generate fresh token and expiry date
    $new_token = wp_generate_uuid4();
    $token_expiry_days = get_option('vaysf_token_expiry_days', 7);
    $new_expiry = date('Y-m-d H:i:s', strtotime("+{$token_expiry_days} days"));
    
    // Update the existing approval record with fresh token
    $table_approvals = vaysf_get_table_name('approvals');
    $update_result = $wpdb->update(
        $table_approvals,
        array(
            'approval_token' => $new_token,
            'token_expiry' => $new_expiry,
            'approval_status' => 'pending',  // Reset to pending regardless of current status
            'updated_at' => current_time('mysql')
        ),
        array('approval_id' => $approval['approval_id']),
        array('%s', '%s', '%s', '%s'),
        array('%d')
    );
    
    // Verify the update was successful
    if (false === $update_result) {
        error_log('VAYSF: Failed to update approval record for resend - ID: ' . $approval['approval_id']);
        return false;
    }
    
    // Update the approval array with new values for email generation
    $approval['approval_token'] = $new_token;
    $approval['token_expiry'] = $new_expiry;
    
    // Get full participant and church data to match original email
    $table_participants = vaysf_get_table_name('participants');
    $table_churches = vaysf_get_table_name('churches');
    
    // Fetch complete participant data
    $participant = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT * FROM $table_participants WHERE participant_id = %d",
            $approval['participant_id']
        ),
        ARRAY_A
    );
    
    // Fetch complete church data
    $church = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT * FROM $table_churches WHERE church_id = %d",
            $approval['church_id']
        ),
        ARRAY_A
    );
    
    if (!$participant || !$church) {
        error_log('VAYSF: Missing participant or church data for resend email');
        return false;
    }
    
    $participant_name = $participant['first_name'] . ' ' . $participant['last_name'];
    
    // Get church representative info (matching original logic)
    $church_rep_name = $church['church_rep_name'] ?: 'N/A';
    $church_rep_email = $church['church_rep_email'] ?: 'N/A';
    $church_rep_phone = $church['church_rep_phone'] ?: 'N/A';
    
    // Format dates (matching original logic)
    $sports_fest_date = VAYSF_Integration::get_sports_fest_date_formatted();
    $token_expiry_date = date_i18n('F j, Y \a\t g:i A', strtotime($approval['token_expiry']));
    
    // Get membership claim info
    $membership_claim = $participant['is_church_member'] ? 'Yes' : 'No';
    
    // Build photo HTML (matching original logic)
    $photo_html = '';
    if (!empty($participant['photo_url'])) {
        $photo_html = '<img src="' . esc_url($participant['photo_url']) . '" alt="' . esc_attr($participant_name) . '" style="max-width: 200px; max-height: 200px; margin: 10px 0;">';
    } else {
        $photo_html = '<p>(No photo available)</p>';
    }
    
    // Build approval links
    $approve_link = site_url('pastor-approval') . '?token=' . urlencode($approval['approval_token']) . '&decision=approve';
    $deny_link = site_url('pastor-approval') . '?token=' . urlencode($approval['approval_token']) . '&decision=deny';
    
    // Build subject (matching original logic)
    $subject_base = get_option('vaysf_approval_email_subject', 'Sports Fest Pastor Approval Required');
    $subject = '[RESEND] ' . $subject_base . ' for ' . $participant_name . ' from ' . $church['church_name'];
    
    // Build rich HTML message (matching original middleware logic)
    $message = '<h2>Sports Fest Pastor Approval Required for ' . esc_html($participant_name) . '</h2>';
    $message .= '<p><em><strong>Note:</strong> This is a resent approval request with a fresh approval link.</em></p>';
    $message .= '<p>Dear Pastor ' . esc_html($church['pastor_name']) . ',</p>';
    
    $message .= '<p>A participant has registered for Sports Fest (starting on ' . $sports_fest_date . ') and listed <strong>' . esc_html($church['church_name']) . '</strong> as their home church. Please review their information and confirm their church membership.</p>';
    
    // Add participant photo
    $message .= '<div style="margin: 15px 0;">';
    $message .= '<strong>Participant Photo:</strong><br>';
    $message .= $photo_html;
    $message .= '</div>';
    
    // Add participant details
    $message .= '<div style="margin: 15px 0; padding: 10px; background-color: #f9f9f9; border-left: 4px solid #0073aa;">';
    $message .= '<h3 style="margin-top: 0;">Participant Information:</h3>';
    $message .= '<p><strong>Name:</strong> ' . esc_html($participant_name) . '</p>';
    $message .= '<p><strong>Email:</strong> ' . esc_html($participant['email']) . '</p>';
    $message .= '<p><strong>Phone:</strong> ' . esc_html($participant['phone'] ?: 'Not provided') . '</p>';
    $message .= '<p><strong>Date of Birth:</strong> ' . esc_html($participant['date_of_birth'] ?: 'Not provided') . '</p>';
    $message .= '<p><strong>Claims Church Membership:</strong> ' . esc_html($membership_claim) . '</p>';
    
    // Add sports information
    $sports = array();
    if (!empty($participant['primary_sport'])) {
        $sports[] = $participant['primary_sport'] . ' (' . ($participant['primary_format'] ?: 'Team') . ')';
    }
    if (!empty($participant['secondary_sport'])) {
        $sports[] = $participant['secondary_sport'] . ' (' . ($participant['secondary_format'] ?: 'Team') . ')';
    }
    if (!empty($participant['other_events'])) {
        $other_events = explode(',', $participant['other_events']);
        foreach ($other_events as $event) {
            $sports[] = trim($event);
        }
    }
    
    if (!empty($sports)) {
        $message .= '<p><strong>Sports/Events:</strong> ' . esc_html(implode(', ', $sports)) . '</p>';
    }
    $message .= '</div>';
    
    // Add church representative info (matching original)
    $message .= '<div style="margin: 15px 0; padding: 10px; background-color: #f0f8ff; border-left: 4px solid #2271b1;">';
    $message .= '<h3 style="margin-top: 0;">Your Church Representative:</h3>';
    $message .= '<p><strong>Name:</strong> ' . esc_html($church_rep_name) . '</p>';
    $message .= '<p><strong>Email:</strong> ' . esc_html($church_rep_email) . '</p>';
    $message .= '<p><strong>Phone:</strong> ' . esc_html($church_rep_phone) . '</p>';
    $message .= '</div>';
    
    // Add action buttons
    $message .= '<div style="margin: 20px 0; text-align: center;">';
    $message .= '<p><strong>Please confirm this person is a member of your church:</strong></p>';
    $message .= '<a href="' . esc_url($approve_link) . '" style="display: inline-block; padding: 12px 24px; background-color: #00a32a; color: white; text-decoration: none; border-radius: 5px; margin: 0 10px; font-weight: bold;">✓ APPROVE (Member)</a>';
    $message .= '<a href="' . esc_url($deny_link) . '" style="display: inline-block; padding: 12px 24px; background-color: #d63638; color: white; text-decoration: none; border-radius: 5px; margin: 0 10px; font-weight: bold;">✗ DENY (Not a Member)</a>';
    $message .= '</div>';
    
    // Add expiry and contact info
    $message .= '<div style="margin: 20px 0; padding: 10px; background-color: #fff3cd; border-left: 4px solid #ffc107;">';
    $message .= '<p><strong>Important:</strong> This approval link will expire on ' . esc_html($token_expiry_date) . '.</p>';
    $message .= '<p>If you need more time, please contact the church representative: <strong>' . esc_html($church_rep_name) . '</strong> at ' . esc_html($church_rep_phone) . ' or ' . esc_html($church_rep_email) . '</p>';
    $message .= '</div>';
    
    $message .= '<p>Thank you for your help with Sports Fest!</p>';
    $message .= '<p>VAY Sports Ministry</p>';
    
    // Use proper from email (matching original)
    $from_email = get_option('vaysf_email_from', get_option('admin_email'));
    $args = array('from' => $from_email);
    
    // Send email using the centralized function
    $pastor_result = vaysf_send_email($approval['pastor_email'], $subject, $message, $args);
    
    // Send notification to participant and church rep (matching original logic)
    if (!empty($participant['email']) && !empty($church_rep_email) && $church_rep_email !== 'N/A') {
        $notification_subject = '[RESEND] Sports Fest Pastor Approval Requested for you, ' . $participant_name;
        $notification_message = '<p>Dear ' . esc_html($participant_name) . ',</p>';
        $notification_message .= '<p><strong>Update:</strong> We have resent your approval request to your church pastor with a fresh approval link.</p>';
        $notification_message .= '<p>Your church pastor now has a new approval request for Sports Fest (starting on ' . $sports_fest_date . ').</p>';
        $notification_message .= '<p>Your Sports Fest registration will be finalized once the pastor confirms your church membership.</p>';
        $notification_message .= '<p>The pastor has until ' . esc_html($token_expiry_date) . ' to respond to this request. If you don\'t receive confirmation by then, please follow up with your church representative, ' . esc_html($church_rep_name) . ', at ' . esc_html($church_rep_email) . '.</p>';
        $notification_message .= '<p>Thank you for registering for Sports Fest!</p>';
        
        // Send to participant with CC to church rep
        vaysf_send_email($participant['email'], $notification_subject, $notification_message, array(
            'from' => $from_email,
            'cc'   => $church_rep_email,
        ));
    }
    
    return $pastor_result;
}

/**
 * Format an insurance status into an admin status badge.
 *
 * @param string $status Insurance status (pending|submitted|approved|rejected)
 * @return string HTML badge
 */
function vaysf_format_insurance_status($status) {
    switch ($status) {
        case 'approved':
            return '<span class="approval-status status-approved">' . esc_html__('Approved', 'vaysf') . '</span>';
        case 'rejected':
            return '<span class="approval-status status-denied">' . esc_html__('Rejected', 'vaysf') . '</span>';
        case 'submitted':
            return '<span class="approval-status status-validated">' . esc_html__('Submitted', 'vaysf') . '</span>';
        case 'pending':
        default:
            return '<span class="approval-status status-pending">' . esc_html__('Pending', 'vaysf') . '</span>';
    }
}

/**
 * Maximum accepted proof-of-insurance upload size in bytes (10 MB).
 *
 * @return int
 */
function vaysf_get_insurance_max_bytes() {
    return 10485760;
}

/**
 * Validate, store, and attach a proof-of-insurance PDF to a church record.
 *
 * Used by both the public token upload flow and the admin upload flow so the
 * same PDF checks and storage behavior stay in one place.
 *
 * @param array $church Church row (associative)
 * @param array $file   Uploaded file array from REST or $_FILES
 * @param array $args   Optional behavior flags
 * @return array|WP_Error Stored upload details or validation/storage error
 */
function vaysf_store_insurance_pdf_for_church($church, $file, $args = array()) {
    global $wpdb;

    $args = wp_parse_args($args, array(
        'notify_rep'       => true,
        'notify_admin'     => get_option('vaysf_insurance_admin_notify', false),
        'preserve_approved' => true,
    ));

    if (empty($church) || empty($church['church_code'])) {
        return new WP_Error(
            'insurance_missing_church',
            esc_html__('Church not found.', 'vaysf'),
            array('status' => 404)
        );
    }

    if (empty($file) || !isset($file['tmp_name'])) {
        return new WP_Error(
            'rest_no_file',
            esc_html__('No file was uploaded.', 'vaysf'),
            array('status' => 400)
        );
    }

    if (!empty($file['error']) && $file['error'] !== UPLOAD_ERR_OK) {
        return new WP_Error(
            'rest_upload_error',
            esc_html__('The file could not be uploaded. Please try again.', 'vaysf'),
            array('status' => 400)
        );
    }

    if (!isset($file['size']) || $file['size'] <= 0 || $file['size'] > vaysf_get_insurance_max_bytes()) {
        return new WP_Error(
            'rest_file_too_large',
            esc_html__('The file must be a PDF no larger than 10 MB.', 'vaysf'),
            array('status' => 422)
        );
    }

    $declared_type = isset($file['type']) ? strtolower($file['type']) : '';
    $name_ext = strtolower(pathinfo(isset($file['name']) ? $file['name'] : '', PATHINFO_EXTENSION));
    $magic = '';
    if (is_readable($file['tmp_name'])) {
        $handle = fopen($file['tmp_name'], 'rb');
        if ($handle) {
            $magic = fread($handle, 5);
            fclose($handle);
        }
    }

    $is_pdf = ($declared_type === 'application/pdf')
        && ($name_ext === 'pdf')
        && (strpos((string) $magic, '%PDF-') === 0);

    if (!$is_pdf) {
        return new WP_Error(
            'rest_invalid_file_type',
            esc_html__('Only PDF files are accepted.', 'vaysf'),
            array('status' => 422)
        );
    }

    $upload_dir = wp_upload_dir();
    if (!empty($upload_dir['error'])) {
        return new WP_Error(
            'rest_upload_dir_failed',
            esc_html__('The upload directory is not available. Please try again.', 'vaysf'),
            array('status' => 500)
        );
    }

    $insurance_dir = trailingslashit($upload_dir['basedir']) . 'vaysf/insurance';
    if (!file_exists($insurance_dir)) {
        wp_mkdir_p($insurance_dir);
    }

    $filename = sanitize_file_name($church['church_code'] . '_' . current_time('YmdHis') . '.pdf');
    $dest_path = trailingslashit($insurance_dir) . $filename;
    $dest_url = trailingslashit($upload_dir['baseurl']) . 'vaysf/insurance/' . $filename;

    $moved = @move_uploaded_file($file['tmp_name'], $dest_path);
    if (!$moved) {
        $moved = @copy($file['tmp_name'], $dest_path);
    }

    if (!$moved) {
        return new WP_Error(
            'rest_storage_failed',
            esc_html__('The file could not be saved. Please try again.', 'vaysf'),
            array('status' => 500)
        );
    }

    $new_status = (!empty($args['preserve_approved']) && isset($church['insurance_status']) && $church['insurance_status'] === 'approved')
        ? 'approved'
        : 'submitted';

    $uploaded_at = current_time('mysql');
    $table_churches = vaysf_get_table_name('churches');
    $updated = $wpdb->update(
        $table_churches,
        array(
            'insurance_file_url'     => $dest_url,
            'insurance_uploaded_at'  => $uploaded_at,
            'insurance_status'       => $new_status,
            'insurance_token'        => null,
            'insurance_token_expiry' => null,
            'updated_at'             => $uploaded_at,
        ),
        array('church_code' => $church['church_code']),
        array('%s', '%s', '%s', '%s', '%s', '%s'),
        array('%s')
    );

    if ($updated === false) {
        return new WP_Error(
            'rest_db_update_failed',
            esc_html__('The insurance record could not be updated. Please try again.', 'vaysf'),
            array('status' => 500)
        );
    }

    $updated_church = array_merge($church, array(
        'insurance_file_url'    => $dest_url,
        'insurance_uploaded_at' => $uploaded_at,
        'insurance_status'      => $new_status,
    ));

    $rep_email_sent = false;
    if (!empty($args['notify_rep'])) {
        $rep_email_sent = vaysf_send_insurance_confirmation_email($updated_church);
    }

    $admin_email_sent = false;
    if (!empty($args['notify_admin'])) {
        $admin_email = sanitize_email(get_option('vaysf_email_from', get_option('admin_email')));
        if (!empty($admin_email)) {
            $subject = sprintf(
                esc_html__('Insurance uploaded: %s', 'vaysf'),
                $church['church_name']
            );
            $message = '<p>' . sprintf(
                esc_html__('%1$s (%2$s) has uploaded a proof-of-insurance document.', 'vaysf'),
                esc_html($church['church_name']),
                esc_html($church['church_code'])
            ) . '</p>';
            $message .= '<p><a href="' . esc_url($dest_url) . '">' . esc_html__('Download PDF', 'vaysf') . '</a></p>';
            $admin_email_sent = vaysf_send_email($admin_email, $subject, $message);
        }
    }

    return array(
        'success'          => true,
        'file_url'         => $dest_url,
        'status'           => $new_status,
        'rep_email_sent'   => $rep_email_sent,
        'admin_email_sent' => $admin_email_sent,
    );
}

/**
 * Send the one-time proof-of-insurance upload link to a church rep (Issue #154).
 *
 * @param array  $church Church row (associative)
 * @param string $token  One-time upload token
 * @param string $expiry MySQL datetime when the token expires
 * @param string $upload_page_url Optional page URL to receive the token
 * @return bool True if the email was sent
 */
function vaysf_send_insurance_link_email($church, $token, $expiry, $upload_page_url = '') {
    $rep_email = isset($church['church_rep_email']) ? $church['church_rep_email'] : '';
    if (empty($rep_email)) {
        return false;
    }

    $rep_name = !empty($church['church_rep_name']) ? $church['church_rep_name'] : esc_html__('Church Representative', 'vaysf');
    $upload_base_url = !empty($upload_page_url) ? $upload_page_url : site_url('insurance-upload');
    $upload_link = add_query_arg('token', $token, $upload_base_url);
    $expiry_display = date_i18n('F j, Y \a\t g:i A', strtotime($expiry));

    $subject = sprintf(
        esc_html__('Sports Fest: Upload Proof of Insurance for %s', 'vaysf'),
        $church['church_name']
    );

    $message  = '<p>' . sprintf(esc_html__('Dear %s,', 'vaysf'), esc_html($rep_name)) . '</p>';
    $message .= '<p>' . sprintf(
        esc_html__('Please use the secure link below to upload your church\'s proof of insurance (PDF, max 10 MB) for %s.', 'vaysf'),
        esc_html($church['church_name'])
    ) . '</p>';
    $message .= '<div style="margin: 20px 0; text-align: center;">';
    $message .= '<a href="' . esc_url($upload_link) . '" style="display: inline-block; padding: 12px 24px; background-color: #2271b1; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">' . esc_html__('Upload Proof of Insurance', 'vaysf') . '</a>';
    $message .= '</div>';
    $message .= '<p><strong>' . esc_html__('Important:', 'vaysf') . '</strong> ' . sprintf(
        esc_html__('This link will expire on %s. If it expires, you can request a new one from the upload page.', 'vaysf'),
        esc_html($expiry_display)
    ) . '</p>';
    $message .= '<p>' . esc_html__('Thank you for your help with Sports Fest!', 'vaysf') . '</p>';
    $message .= '<p>VAY Sports Ministry</p>';

    $from_email = get_option('vaysf_email_from', get_option('admin_email'));

    return vaysf_send_email($rep_email, $subject, $message, array('from' => $from_email));
}

/**
 * Send a confirmation email after a successful insurance upload (Issue #154).
 *
 * @param array $church Church row (associative)
 * @return bool True if the email was sent
 */
function vaysf_send_insurance_confirmation_email($church) {
    $rep_email = isset($church['church_rep_email']) ? $church['church_rep_email'] : '';
    if (empty($rep_email)) {
        return false;
    }

    $rep_name = !empty($church['church_rep_name']) ? $church['church_rep_name'] : esc_html__('Church Representative', 'vaysf');

    $subject = sprintf(
        esc_html__('Sports Fest: Proof of Insurance Received for %s', 'vaysf'),
        $church['church_name']
    );

    $message  = '<p>' . sprintf(esc_html__('Dear %s,', 'vaysf'), esc_html($rep_name)) . '</p>';
    $message .= '<p>' . sprintf(
        esc_html__('We have received the proof-of-insurance document for %s. No further action is needed unless our staff contact you.', 'vaysf'),
        esc_html($church['church_name'])
    ) . '</p>';
    $message .= '<p>' . esc_html__('Thank you for your help with Sports Fest!', 'vaysf') . '</p>';
    $message .= '<p>VAY Sports Ministry</p>';

    $from_email = get_option('vaysf_email_from', get_option('admin_email'));

    return vaysf_send_email($rep_email, $subject, $message, array('from' => $from_email));
}

/**
 * Send a confirmation email after staff approve a proof-of-insurance document.
 *
 * @param array $church Church row (associative)
 * @return bool True if the email was sent
 */
function vaysf_send_insurance_approved_email($church) {
    $rep_email = isset($church['church_rep_email']) ? $church['church_rep_email'] : '';
    if (empty($rep_email)) {
        return false;
    }

    $rep_name = !empty($church['church_rep_name']) ? $church['church_rep_name'] : esc_html__('Church Representative', 'vaysf');

    $subject = sprintf(
        esc_html__('Sports Fest: Proof of Insurance Approved for %s', 'vaysf'),
        $church['church_name']
    );

    $message  = '<p>' . sprintf(esc_html__('Dear %s,', 'vaysf'), esc_html($rep_name)) . '</p>';
    $message .= '<p>' . sprintf(
        esc_html__('Our staff has reviewed and approved the proof-of-insurance document for %s.', 'vaysf'),
        esc_html($church['church_name'])
    ) . '</p>';
    $message .= '<p>' . esc_html__('No further action is needed for your church\'s proof of insurance at this time.', 'vaysf') . '</p>';
    $message .= '<p>' . esc_html__('Thank you for your help with Sports Fest!', 'vaysf') . '</p>';
    $message .= '<p>VAY Sports Ministry</p>';

    $from_email = get_option('vaysf_email_from', get_option('admin_email'));

    return vaysf_send_email($rep_email, $subject, $message, array('from' => $from_email));
}

<?php
/**
 * File: admin/class-vaysf-admin-schedules.php
 * Description: Schedules admin page - list/edit/cancel event-day schedule rows,
 *              source-hash computation matching middleware/schedule_publisher.py
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

/**
 * Return the requested event-day schedule version from an admin export request.
 *
 * @return int
 */
function vaysf_get_event_day_export_schedule_version_from_request() {
    $schedule_version = isset($_GET['schedule_version']) && $_GET['schedule_version'] !== ''
        ? absint($_GET['schedule_version'])
        : (function_exists('vaysf_get_current_published_schedule_version') ? vaysf_get_current_published_schedule_version() : null);
    $schedule_version = $schedule_version === null ? 0 : absint($schedule_version);
    if (!$schedule_version) {
        wp_die(esc_html__('No published schedule version is available to export.', 'vaysf'), 400);
    }

    return $schedule_version;
}

/**
 * Fetch the live WordPress event-day schedule/results state as arrays.
 *
 * @param int $schedule_version Schedule version
 * @return array<string,mixed>
 */
function vaysf_get_event_day_state_export_payload($schedule_version) {
    global $wpdb;

    $schedule_version = absint($schedule_version);

    $table_schedules = vaysf_get_table_name('schedules');
    $table_results = vaysf_get_table_name('results');
    $table_revisions = vaysf_get_table_name('result_revisions');
    $table_advancement = vaysf_get_table_name('pool_advancement');

    $schedules = $wpdb->get_results(
        $wpdb->prepare(
            "SELECT *
                FROM $table_schedules
                WHERE schedule_version = %d
                ORDER BY scheduled_time IS NULL, scheduled_time, event, game_key, schedule_id",
            $schedule_version
        ),
        ARRAY_A
    );
    if (!is_array($schedules)) {
        $schedules = array();
    }

    $results = $wpdb->get_results(
        $wpdb->prepare(
            "SELECT r.*
                FROM $table_results r
                INNER JOIN $table_schedules s ON s.schedule_id = r.schedule_id
                WHERE s.schedule_version = %d
                ORDER BY r.updated_at, r.result_id",
            $schedule_version
        ),
        ARRAY_A
    );
    if (!is_array($results)) {
        $results = array();
    }

    $result_revisions = $wpdb->get_results(
        $wpdb->prepare(
            "SELECT rr.*
                FROM $table_revisions rr
                INNER JOIN $table_results r ON r.result_id = rr.result_id
                INNER JOIN $table_schedules s ON s.schedule_id = r.schedule_id
                WHERE s.schedule_version = %d
                ORDER BY rr.submitted_at, rr.result_id, rr.revision_number",
            $schedule_version
        ),
        ARRAY_A
    );
    if (!is_array($result_revisions)) {
        $result_revisions = array();
    }

    $pool_advancement = $wpdb->get_results(
        $wpdb->prepare(
            "SELECT *
                FROM $table_advancement
                WHERE schedule_version = %d
                ORDER BY event, pool_id, advancement_id",
            $schedule_version
        ),
        ARRAY_A
    );
    if (!is_array($pool_advancement)) {
        $pool_advancement = array();
    }

    $status_counts = array();
    foreach ($schedules as $row) {
        $status = (string) ($row['game_status'] ?? 'scheduled');
        if (!isset($status_counts[$status])) {
            $status_counts[$status] = 0;
        }
        $status_counts[$status]++;
    }
    ksort($status_counts);

    $payload = array(
        'schema' => 'vaysf_event_day_state_export_v1',
        'generated_at' => current_time('mysql'),
        'generated_at_utc' => gmdate('Y-m-d H:i:s'),
        'site_url' => site_url(),
        'plugin_version' => defined('VAYSF_Integration::VERSION') ? VAYSF_Integration::VERSION : '',
        'db_version' => defined('VAYSF_Integration::DB_VERSION') ? VAYSF_Integration::DB_VERSION : '',
        'schedule_version' => $schedule_version,
        'counts' => array(
            'schedules' => count($schedules),
            'results' => count($results),
            'result_revisions' => count($result_revisions),
            'pool_advancement' => count($pool_advancement),
            'schedule_statuses' => $status_counts,
        ),
        'tables' => array(
            'schedules' => $schedules,
            'results' => $results,
            'result_revisions' => $result_revisions,
            'pool_advancement' => $pool_advancement,
        ),
    );

    return $payload;
}

/**
 * Download the live WordPress event-day schedule/results state as JSON.
 *
 * This is the operator-facing handoff from WordPress (live event source of
 * truth) back to the local operations computer. It exports the selected or
 * current published schedule version without transforming score payloads,
 * so local tools can archive/import the exact WP state instead of rerunning
 * the scheduler during Sports Fest.
 *
 * @return void
 */
function vaysf_download_event_day_state_json() {
    if (!current_user_can('sf2025_admin')) {
        wp_die(esc_html__('You are not authorized to export event-day state.', 'vaysf'), 403);
    }
    if (empty($_GET['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_GET['_wpnonce'])), 'vaysf_download_event_day_state_json')) {
        wp_die(esc_html__('Invalid event-day export request.', 'vaysf'), 403);
    }

    $schedule_version = vaysf_get_event_day_export_schedule_version_from_request();
    $payload = vaysf_get_event_day_state_export_payload($schedule_version);
    $json = wp_json_encode($payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    if ($json === false) {
        wp_die(esc_html__('Could not encode event-day state export.', 'vaysf'), 500);
    }

    $filename = sprintf('vaysf-event-day-state-v%d-%s.json', $schedule_version, date_i18n('Ymd-His'));
    nocache_headers();
    header('Content-Type: application/json; charset=utf-8');
    header('Content-Disposition: attachment; filename="' . sanitize_file_name($filename) . '"');
    echo $json;
    exit;
}

/**
 * Infer a schedule_input resource_type from the event name stored in WordPress.
 *
 * @param array<string,mixed> $row Schedule row
 * @return string
 */
function vaysf_event_day_export_resource_type($row) {
    $event = (string) ($row['event'] ?? '');
    if (stripos($event, 'Basketball') !== false) {
        return 'Basketball Court';
    }
    if (stripos($event, 'Volleyball') !== false) {
        return 'Volleyball Court';
    }
    if (stripos($event, 'Soccer') !== false) {
        return 'Soccer Field';
    }
    if (stripos($event, 'Bible Challenge') !== false) {
        return 'BC Station';
    }
    if (stripos($event, 'Table Tennis') !== false) {
        return 'Table Tennis Table';
    }
    if (stripos($event, 'Tennis') !== false) {
        return 'Tennis Court';
    }
    if (stripos($event, 'Badminton') !== false) {
        return 'Badminton Court';
    }
    if (stripos($event, 'Pickleball') !== false) {
        return 'Pickleball Court';
    }
    if (stripos($event, 'Tug-of-war') !== false || stripos($event, 'Tug of war') !== false) {
        return 'Tug-of-war';
    }
    if (stripos($event, 'Track') !== false) {
        return 'Track & Field';
    }

    return $event !== '' ? $event : 'Event-Day Resource';
}

/**
 * Infer a conservative game duration for exported schedule_input rows.
 *
 * @param array<string,mixed> $row Schedule row
 * @return float
 */
function vaysf_event_day_export_duration_minutes($row) {
    $game_key = (string) ($row['game_key'] ?? '');
    if ($game_key === 'BC-Final') {
        return 90.0;
    }

    $event = (string) ($row['event'] ?? '');
    if (stripos($event, 'Track') !== false || stripos($event, 'Tug-of-war') !== false || stripos($event, 'Tug of war') !== false) {
        return 30.0;
    }

    return 60.0;
}

/**
 * Parse a scheduler slot label into day/time parts.
 *
 * @param string $slot Slot such as Sat-2-20:30
 * @return array{day:string,time:string}
 */
function vaysf_event_day_export_parse_slot($slot) {
    $slot = trim((string) $slot);
    if (preg_match('/^(.+)-(\d{1,2}:\d{2})$/', $slot, $matches)) {
        return array('day' => $matches[1], 'time' => $matches[2]);
    }

    return array('day' => 'Event-Day', 'time' => '08:00');
}

/**
 * Add minutes to a HH:MM time string, capped at 23:59 for contract validity.
 *
 * @param string $time HH:MM
 * @param float $minutes Minutes to add
 * @return string
 */
function vaysf_event_day_export_add_minutes($time, $minutes) {
    $parts = explode(':', trim((string) $time));
    $hour = isset($parts[0]) ? absint($parts[0]) : 8;
    $minute = isset($parts[1]) ? absint($parts[1]) : 0;
    $total = min(23 * 60 + 59, $hour * 60 + $minute + max(1, (int) ceil((float) $minutes)));

    return sprintf('%02d:%02d', (int) floor($total / 60), $total % 60);
}

/**
 * Convert live WordPress schedule rows into publish-schedule JSON artifacts.
 *
 * The resulting pair is intentionally a replay/export contract, not a full
 * reconstruction of the original solver model. WordPress does not store the
 * original venue availability, athlete conflict edges, or solver diagnostics.
 *
 * @param array<string,mixed> $state_payload Event-day state payload
 * @return array{input:array<string,mixed>,output:array<string,mixed>}
 */
function vaysf_build_event_day_publish_artifacts($state_payload) {
    $schedule_version = absint($state_payload['schedule_version'] ?? 0);
    $rows = isset($state_payload['tables']['schedules']) && is_array($state_payload['tables']['schedules'])
        ? $state_payload['tables']['schedules']
        : array();

    $games = array();
    $assignments = array();
    $resources_by_id = array();
    $day_order = array();

    foreach ($rows as $row) {
        if (!is_array($row) || (string) ($row['game_status'] ?? '') === 'cancelled') {
            continue;
        }

        $game_id = trim((string) ($row['game_key'] ?? ''));
        if ($game_id === '') {
            continue;
        }

        $duration = vaysf_event_day_export_duration_minutes($row);
        $resource_type = vaysf_event_day_export_resource_type($row);
        $resource_id = trim((string) ($row['resource_id'] ?? ''));
        if ($resource_id === '') {
            $resource_id = 'WP-UNASSIGNED-' . sanitize_key($game_id);
        }
        $slot = trim((string) ($row['scheduled_slot'] ?? ''));
        if ($slot === '') {
            $slot = 'Event-Day-08:00';
        }
        $parsed_slot = vaysf_event_day_export_parse_slot($slot);
        $day_order[$parsed_slot['day']] = true;

        $team_ids = array_values(array_filter(array(
            trim((string) ($row['team_a_key'] ?? '')),
            trim((string) ($row['team_b_key'] ?? '')),
            trim((string) ($row['team_c_key'] ?? '')),
        ), 'strlen'));

        $round = isset($row['round_number']) && is_numeric($row['round_number'])
            ? (int) $row['round_number']
            : null;

        $games[] = array(
            'game_id' => $game_id,
            'event' => (string) ($row['event'] ?? ''),
            'stage' => (string) ($row['stage'] ?? ''),
            'pool_id' => (string) ($row['pool_id'] ?? ''),
            'round' => $round,
            'duration_minutes' => $duration,
            'resource_type' => $resource_type,
            'team_a_id' => (string) ($row['team_a_key'] ?? ''),
            'team_a_label' => (string) ($row['team_a_label'] ?? ''),
            'team_b_id' => (string) ($row['team_b_key'] ?? ''),
            'team_b_label' => (string) ($row['team_b_label'] ?? ''),
            'team_c_id' => (string) ($row['team_c_key'] ?? ''),
            'team_c_label' => (string) ($row['team_c_label'] ?? ''),
            'team_ids' => $team_ids,
            'x_wp_schedule_id' => absint($row['schedule_id'] ?? 0),
            'x_wp_game_status' => (string) ($row['game_status'] ?? ''),
        );

        $assignments[] = array(
            'game_id' => $game_id,
            'resource_id' => $resource_id,
            'slot' => $slot,
            'event' => (string) ($row['event'] ?? ''),
            'stage' => (string) ($row['stage'] ?? ''),
            'team_a_id' => (string) ($row['team_a_key'] ?? ''),
            'team_b_id' => (string) ($row['team_b_key'] ?? ''),
            'team_c_id' => (string) ($row['team_c_key'] ?? ''),
            'scheduled_location' => (string) ($row['scheduled_location'] ?? ''),
        );

        if (!isset($resources_by_id[$resource_id])) {
            $resources_by_id[$resource_id] = array(
                'resource_id' => $resource_id,
                'resource_type' => $resource_type,
                'day' => $parsed_slot['day'],
                'open_time' => $parsed_slot['time'],
                'close_time' => vaysf_event_day_export_add_minutes($parsed_slot['time'], $duration),
                'slot_minutes' => max(15, (int) min(60, $duration)),
                'label' => $resource_id,
                'venue_name' => (string) ($row['scheduled_location'] ?? ''),
                'x_event_day_export_stub' => true,
            );
        } elseif ($resources_by_id[$resource_id]['day'] === $parsed_slot['day']) {
            if (strcmp($parsed_slot['time'], $resources_by_id[$resource_id]['open_time']) < 0) {
                $resources_by_id[$resource_id]['open_time'] = $parsed_slot['time'];
            }
            $close_time = vaysf_event_day_export_add_minutes($parsed_slot['time'], $duration);
            if (strcmp($close_time, $resources_by_id[$resource_id]['close_time']) > 0) {
                $resources_by_id[$resource_id]['close_time'] = $close_time;
            }
        }
    }

    $metadata = array(
        'source' => 'wordpress_event_day_export',
        'schema' => 'vaysf_event_day_publish_bundle_v1',
        'schedule_version' => $schedule_version,
        'generated_at' => (string) ($state_payload['generated_at'] ?? ''),
        'site_url' => (string) ($state_payload['site_url'] ?? ''),
        'note' => 'Replay pair exported from WordPress event-day state. Resource rows are inferred stubs; admins can export raw state JSON separately for audit.',
    );

    return array(
        'input' => array(
            'generated_at' => (string) ($state_payload['generated_at'] ?? ''),
            'games' => $games,
            'resources' => array_values($resources_by_id),
            'playoff_slots' => array(),
            'team_conflicts' => array(),
            'precedence' => array(),
            'day_order' => array_keys($day_order),
            'approved_games' => $metadata,
        ),
        'output' => array(
            'solved_at' => (string) ($state_payload['generated_at'] ?? ''),
            'status' => 'FEASIBLE',
            'assignments' => $assignments,
            'unscheduled' => array(),
            'approved_games' => $metadata,
        ),
    );
}

/**
 * Download publish-schedule-compatible event-day JSON files as a ZIP bundle.
 *
 * @return void
 */
function vaysf_download_event_day_publish_zip() {
    if (!current_user_can('sf2025_write')) {
        wp_die(esc_html__('You are not authorized to export event-day publish JSON.', 'vaysf'), 403);
    }
    if (empty($_GET['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_GET['_wpnonce'])), 'vaysf_download_event_day_publish_zip')) {
        wp_die(esc_html__('Invalid event-day publish export request.', 'vaysf'), 403);
    }
    if (!class_exists('ZipArchive')) {
        wp_die(esc_html__('The PHP ZipArchive extension is required to download the publish JSON bundle.', 'vaysf'), 500);
    }

    $schedule_version = vaysf_get_event_day_export_schedule_version_from_request();
    $state_payload = vaysf_get_event_day_state_export_payload($schedule_version);
    $artifacts = vaysf_build_event_day_publish_artifacts($state_payload);
    $include_state_backup = current_user_can('sf2025_admin');

    $json_flags = JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE;
    if (defined('JSON_PRESERVE_ZERO_FRACTION')) {
        $json_flags |= JSON_PRESERVE_ZERO_FRACTION;
    }

    $input_json = wp_json_encode($artifacts['input'], $json_flags);
    $output_json = wp_json_encode($artifacts['output'], $json_flags);
    $state_json = $include_state_backup
        ? wp_json_encode($state_payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE)
        : '';
    if ($input_json === false || $output_json === false || ($include_state_backup && $state_json === false)) {
        wp_die(esc_html__('Could not encode event-day publish export.', 'vaysf'), 500);
    }

    $zip_path = wp_tempnam('vaysf-event-day-publish-v' . $schedule_version . '.zip');
    if (!$zip_path) {
        wp_die(esc_html__('Could not create a temporary export file.', 'vaysf'), 500);
    }

    $zip = new ZipArchive();
    if ($zip->open($zip_path, ZipArchive::OVERWRITE) !== true) {
        wp_delete_file($zip_path);
        wp_die(esc_html__('Could not create the event-day publish ZIP.', 'vaysf'), 500);
    }
    $zip->addFromString('approved_schedule_input.json', $input_json);
    $zip->addFromString('approved_schedule_output.json', $output_json);
    if ($include_state_backup) {
        $zip->addFromString(sprintf('vaysf-event-day-state-v%d.json', $schedule_version), $state_json);
    }
    $zip->close();

    $filename = sprintf('vaysf-event-day-publish-v%d-%s.zip', $schedule_version, date_i18n('Ymd-His'));
    nocache_headers();
    header('Content-Type: application/zip');
    header('Content-Disposition: attachment; filename="' . sanitize_file_name($filename) . '"');
    header('Content-Length: ' . filesize($zip_path));
    readfile($zip_path);
    wp_delete_file($zip_path);
    exit;
}

class VAYSF_Admin_Schedules extends VAYSF_Admin_Page {

    /**
     * Return source_hash fields in the same order as middleware/schedule_publisher.py.
     */
    private function schedule_hash_fields() {
        return array(
            'event', 'stage', 'pool_id', 'round_number',
            'team_a_key', 'team_a_label', 'team_b_key', 'team_b_label',
            'team_c_key', 'team_c_label', 'team_ids_json',
            'resource_id', 'scheduled_slot',
        );
    }

    /**
     * Compute the schedule source hash used by publish-schedule diffing.
     */
    private function compute_schedule_source_hash($row) {
        $subset = array();
        foreach ($this->schedule_hash_fields() as $field) {
            $subset[$field] = array_key_exists($field, $row) ? $row[$field] : null;
        }
        ksort($subset);

        return hash('sha256', wp_json_encode($subset, JSON_UNESCAPED_SLASHES));
    }
    private function sanitize_schedule_payload_from_post() {
        $payload = array();
        $text_fields = array(
            'game_key', 'event', 'stage', 'pool_id', 'sub_event',
            'team_a_key', 'team_a_label', 'team_b_key', 'team_b_label',
            'team_c_key', 'team_c_label', 'team_ids_json',
            'resource_id', 'scheduled_slot', 'scheduled_time',
            'scheduled_location', 'game_status',
        );

        foreach ($text_fields as $field) {
            $payload[$field] = isset($_POST[$field])
                ? sanitize_text_field(wp_unslash($_POST[$field]))
                : '';
        }

        // Nullable sf_schedules columns that also feed compute_schedule_source_hash():
        // normalize a blank submission to null (not '') so an admin-edited row hashes
        // the same way middleware/schedule_publisher.py hashes a game whose optional
        // field is simply absent from schedule_input.json (Python .get() -> None ->
        // JSON null). Leaving these as '' would make publish-schedule's diff report
        // every admin-touched row as "changed" even when nothing meaningful changed.
        foreach ($this->schedule_hash_fields() as $field) {
            if ($field !== 'round_number' && $payload[$field] === '') {
                $payload[$field] = null;
            }
        }

        $payload['round_number'] = isset($_POST['round_number']) && $_POST['round_number'] !== ''
            ? absint($_POST['round_number'])
            : null;
        $payload['schedule_version'] = isset($_POST['schedule_version'])
            ? absint($_POST['schedule_version'])
            : 0;
        $payload['synced_to_chmeetings'] = !empty($_POST['synced_to_chmeetings']) ? 1 : 0;

        return $payload;
    }

    private function save_schedule_from_post($schedule_id = 0) {
        global $wpdb;

        if (!current_user_can('sf2025_admin')) {
            return new WP_Error('vaysf_forbidden', 'You are not allowed to modify schedules.');
        }

        $table_schedules = vaysf_get_table_name('schedules');
        $schedule_id = absint($schedule_id);
        $existing = null;

        if ($schedule_id) {
            $existing = $wpdb->get_row(
                $wpdb->prepare("SELECT * FROM $table_schedules WHERE schedule_id = %d", $schedule_id),
                ARRAY_A
            );
            if (!$existing) {
                return new WP_Error('vaysf_schedule_missing', 'Schedule row not found.');
            }
        }

        $payload = $this->sanitize_schedule_payload_from_post();
        if ($payload['game_key'] === '') {
            return new WP_Error('vaysf_schedule_game_key_required', 'Game key is required.');
        }
        if (!in_array($payload['game_status'], $this->schedule_status_options(), true)) {
            return new WP_Error('vaysf_schedule_bad_status', 'Invalid game status.');
        }

        if ($existing && $this->is_protected_schedule_status($existing['game_status']) && empty($_POST['confirm_protected'])) {
            return new WP_Error('vaysf_schedule_protected', 'Protected schedule rows require explicit confirmation before editing.');
        }
        if ($payload['game_status'] === 'cancelled' && empty($_POST['confirm_cancel'])) {
            return new WP_Error('vaysf_schedule_cancel_confirm', 'Cancelling a schedule row requires explicit confirmation.');
        }

        $payload['source_hash'] = $this->compute_schedule_source_hash($payload);
        $payload['updated_at'] = current_time('mysql');

        $data = array(
            'game_key' => $payload['game_key'],
            'schedule_version' => $payload['schedule_version'],
            'event' => $payload['event'],
            'stage' => $payload['stage'],
            'pool_id' => $payload['pool_id'],
            'round_number' => $payload['round_number'],
            'sub_event' => $payload['sub_event'],
            'team_a_key' => $payload['team_a_key'],
            'team_a_label' => $payload['team_a_label'],
            'team_b_key' => $payload['team_b_key'],
            'team_b_label' => $payload['team_b_label'],
            'team_c_key' => $payload['team_c_key'],
            'team_c_label' => $payload['team_c_label'],
            'team_ids_json' => $payload['team_ids_json'],
            'resource_id' => $payload['resource_id'],
            'scheduled_slot' => $payload['scheduled_slot'],
            'scheduled_time' => $payload['scheduled_time'] ?: null,
            'scheduled_location' => $payload['scheduled_location'],
            'game_status' => $payload['game_status'],
            'source_hash' => $payload['source_hash'],
            'synced_to_chmeetings' => $payload['synced_to_chmeetings'],
            'updated_at' => $payload['updated_at'],
        );
        $formats = array(
            '%s', '%d', '%s', '%s', '%s', '%d', '%s',
            '%s', '%s', '%s', '%s', '%s', '%s', '%s',
            '%s', '%s', '%s', '%s', '%s', '%s', '%d', '%s',
        );

        if ($schedule_id) {
            $result = $wpdb->update(
                $table_schedules,
                $data,
                array('schedule_id' => $schedule_id),
                $formats,
                array('%d')
            );
        } else {
            $data['created_at'] = current_time('mysql');
            $formats[] = '%s';
            $result = $wpdb->insert($table_schedules, $data, $formats);
        }

        if ($result === false) {
            return new WP_Error('vaysf_schedule_save_failed', 'Could not save schedule row.');
        }

        return true;
    }

    private function cancel_schedule_from_post($schedule_id) {
        global $wpdb;

        if (!current_user_can('sf2025_admin')) {
            return new WP_Error('vaysf_forbidden', 'You are not allowed to cancel schedules.');
        }
        if (empty($_POST['confirm_cancel'])) {
            return new WP_Error('vaysf_schedule_cancel_confirm', 'Cancelling a schedule row requires explicit confirmation.');
        }

        $table_schedules = vaysf_get_table_name('schedules');
        $schedule = $wpdb->get_row(
            $wpdb->prepare("SELECT * FROM $table_schedules WHERE schedule_id = %d", absint($schedule_id)),
            ARRAY_A
        );
        if (!$schedule) {
            return new WP_Error('vaysf_schedule_missing', 'Schedule row not found.');
        }
        if ($this->is_protected_schedule_status($schedule['game_status']) && empty($_POST['confirm_protected'])) {
            return new WP_Error('vaysf_schedule_protected', 'Protected schedule rows require explicit confirmation before cancellation.');
        }

        $schedule['game_status'] = 'cancelled';
        $schedule['source_hash'] = $this->compute_schedule_source_hash($schedule);

        $result = $wpdb->update(
            $table_schedules,
            array(
                'game_status' => 'cancelled',
                'source_hash' => $schedule['source_hash'],
                'updated_at' => current_time('mysql'),
            ),
            array('schedule_id' => absint($schedule_id)),
            array('%s', '%s', '%s'),
            array('%d')
        );

        if ($result === false) {
            return new WP_Error('vaysf_schedule_cancel_failed', 'Could not cancel schedule row.');
        }

        return true;
    }

    /**
     * Return the 2026 manager playoff placement template from issue #337.
     *
     * These defaults come from the attached manager schedule image. They only
     * place existing rows; they do not change teams, brackets, or results.
     */
    private function playoff_placement_template() {
        return array(
            'BBM-QF-3' => array('scheduled_time' => '2026-07-25 08:00:00', 'scheduled_slot' => 'Sat-2-08:00', 'resource_id' => 'ORN-MAIN-CC-1', 'scheduled_location' => 'ORN Church - Main Gym Center Court 1'),
            'BBM-QF-2' => array('scheduled_time' => '2026-07-25 08:00:00', 'scheduled_slot' => 'Sat-2-08:00', 'resource_id' => 'ORN-MAIN-CC-2', 'scheduled_location' => 'ORN Church - Main Gym Center Court 2'),
            'BBM-QF-1' => array('scheduled_time' => '2026-07-25 09:00:00', 'scheduled_slot' => 'Sat-2-09:00', 'resource_id' => 'ORN-MAIN-CC-1', 'scheduled_location' => 'ORN Church - Main Gym Center Court 1'),
            'BBM-QF-4' => array('scheduled_time' => '2026-07-25 09:00:00', 'scheduled_slot' => 'Sat-2-09:00', 'resource_id' => 'ORN-MAIN-CC-2', 'scheduled_location' => 'ORN Church - Main Gym Center Court 2'),
            'BBM-Semi-1' => array('scheduled_time' => '2026-07-25 11:00:00', 'scheduled_slot' => 'Sat-2-11:00', 'resource_id' => 'ORN-MAIN-CC-1', 'scheduled_location' => 'ORN Church - Main Gym Center Court 1'),
            'BBM-Semi-2' => array('scheduled_time' => '2026-07-25 11:00:00', 'scheduled_slot' => 'Sat-2-11:00', 'resource_id' => 'ORN-MAIN-CC-2', 'scheduled_location' => 'ORN Church - Main Gym Center Court 2'),
            'BBM-3rd-Place' => array('scheduled_time' => '2026-07-26 14:00:00', 'scheduled_slot' => 'Sun-2-14:00', 'resource_id' => 'ORN-MAIN-CC', 'scheduled_location' => 'ORN Church - Main Gym Center Court'),
            'BBM-Final' => array('scheduled_time' => '2026-07-26 15:00:00', 'scheduled_slot' => 'Sun-2-15:00', 'resource_id' => 'ORN-MAIN-CC', 'scheduled_location' => 'ORN Church - Main Gym Center Court'),
            'VBW-QF-3' => array('scheduled_time' => '2026-07-25 08:00:00', 'scheduled_slot' => 'Sat-2-08:00', 'resource_id' => 'ORN-PRACTICE-VB2', 'scheduled_location' => 'ORN Church - Practice Gym VB2'),
            'VBW-QF-2' => array('scheduled_time' => '2026-07-25 08:00:00', 'scheduled_slot' => 'Sat-2-08:00', 'resource_id' => 'ORN-PRACTICE-VB3', 'scheduled_location' => 'ORN Church - Practice Gym VB3'),
            'VBW-QF-1' => array('scheduled_time' => '2026-07-25 09:00:00', 'scheduled_slot' => 'Sat-2-09:00', 'resource_id' => 'ORN-PRACTICE-VB2', 'scheduled_location' => 'ORN Church - Practice Gym VB2'),
            'VBW-QF-4' => array('scheduled_time' => '2026-07-25 09:00:00', 'scheduled_slot' => 'Sat-2-09:00', 'resource_id' => 'ORN-PRACTICE-VB3', 'scheduled_location' => 'ORN Church - Practice Gym VB3'),
            'MVB-QF-1' => array('scheduled_time' => '2026-07-25 10:00:00', 'scheduled_slot' => 'Sat-2-10:00', 'resource_id' => 'ORN-PRACTICE-VB2', 'scheduled_location' => 'ORN Church - Practice Gym VB2'),
            'MVB-QF-2' => array('scheduled_time' => '2026-07-25 10:00:00', 'scheduled_slot' => 'Sat-2-10:00', 'resource_id' => 'ORN-PRACTICE-VB3', 'scheduled_location' => 'ORN Church - Practice Gym VB3'),
            'MVB-QF-4' => array('scheduled_time' => '2026-07-25 11:00:00', 'scheduled_slot' => 'Sat-2-11:00', 'resource_id' => 'ORN-PRACTICE-VB2', 'scheduled_location' => 'ORN Church - Practice Gym VB2'),
            'MVB-QF-3' => array('scheduled_time' => '2026-07-25 11:00:00', 'scheduled_slot' => 'Sat-2-11:00', 'resource_id' => 'ORN-PRACTICE-VB3', 'scheduled_location' => 'ORN Church - Practice Gym VB3'),
            'VBW-Semi-1' => array('scheduled_time' => '2026-07-25 14:00:00', 'scheduled_slot' => 'Sat-2-14:00', 'resource_id' => 'ORN-PRACTICE-VB2', 'scheduled_location' => 'ORN Church - Practice Gym VB2'),
            'VBW-Semi-2' => array('scheduled_time' => '2026-07-25 14:00:00', 'scheduled_slot' => 'Sat-2-14:00', 'resource_id' => 'ORN-PRACTICE-VB3', 'scheduled_location' => 'ORN Church - Practice Gym VB3'),
            'MVB-Semi-1' => array('scheduled_time' => '2026-07-25 15:00:00', 'scheduled_slot' => 'Sat-2-15:00', 'resource_id' => 'ORN-PRACTICE-VB2', 'scheduled_location' => 'ORN Church - Practice Gym VB2'),
            'MVB-Semi-2' => array('scheduled_time' => '2026-07-25 15:00:00', 'scheduled_slot' => 'Sat-2-15:00', 'resource_id' => 'ORN-PRACTICE-VB3', 'scheduled_location' => 'ORN Church - Practice Gym VB3'),
            'MVB-Final' => array('scheduled_time' => '2026-07-26 12:00:00', 'scheduled_slot' => 'Sun-2-12:00', 'resource_id' => 'ORN-MAIN-CC', 'scheduled_location' => 'ORN Church - Main Gym Center Court'),
            'MVB-3rd-Place' => array('scheduled_time' => '2026-07-26 12:00:00', 'scheduled_slot' => 'Sun-2-12:00', 'resource_id' => 'ORN-PRACTICE-CC', 'scheduled_location' => 'ORN Church - Practice Gym Center Court'),
            'VBW-Final' => array('scheduled_time' => '2026-07-26 13:00:00', 'scheduled_slot' => 'Sun-2-13:00', 'resource_id' => 'ORN-MAIN-CC', 'scheduled_location' => 'ORN Church - Main Gym Center Court'),
            'VBW-3rd-Place' => array('scheduled_time' => '2026-07-26 13:00:00', 'scheduled_slot' => 'Sun-2-13:00', 'resource_id' => 'ORN-PRACTICE-CC', 'scheduled_location' => 'ORN Church - Practice Gym Center Court'),
            'BC-Semi-1' => array('scheduled_time' => '2026-07-25 14:00:00', 'scheduled_slot' => 'Sat-2-14:00', 'resource_id' => 'ORN-BC-LIBRARY', 'scheduled_location' => 'ORN Church - BC Library'),
            'BC-Semi-2' => array('scheduled_time' => '2026-07-25 15:00:00', 'scheduled_slot' => 'Sat-2-15:00', 'resource_id' => 'ORN-BC-LIBRARY', 'scheduled_location' => 'ORN Church - BC Library'),
            'BC-Semi-3' => array('scheduled_time' => '2026-07-25 16:00:00', 'scheduled_slot' => 'Sat-2-16:00', 'resource_id' => 'ORN-BC-LIBRARY', 'scheduled_location' => 'ORN Church - BC Library'),
            'BC-Final' => array('scheduled_time' => '2026-07-26 14:30:00', 'scheduled_slot' => 'Sun-2-14:30', 'resource_id' => 'ORN-PRACTICE-CC', 'scheduled_location' => 'ORN Church - Practice Gym Center Court'),
        );
    }

    private function placement_row_needs_values($row) {
        if (!$row) {
            return true;
        }

        foreach (array('scheduled_time', 'scheduled_slot', 'resource_id', 'scheduled_location') as $field) {
            if (trim((string) ($row[$field] ?? '')) === '') {
                return true;
            }
        }

        return false;
    }

    private function playoff_placement_row_metadata($game_key) {
        $game_key = (string) $game_key;
        $event = '';
        if (strpos($game_key, 'BBM-') === 0) {
            $event = 'Basketball - Men Team';
        } elseif (strpos($game_key, 'MVB-') === 0) {
            $event = 'Volleyball - Men Team';
        } elseif (strpos($game_key, 'VBW-') === 0) {
            $event = 'Volleyball - Women Team';
        } elseif (strpos($game_key, 'BC-') === 0) {
            $event = 'Bible Challenge - Mixed Team';
        }

        $stage = '';
        if (strpos($game_key, '-QF-') !== false) {
            $stage = 'Quarterfinal';
        } elseif (strpos($game_key, '-Semi-') !== false) {
            $stage = 'Semifinal';
        } elseif (substr($game_key, -10) === '-3rd-Place') {
            $stage = '3rd Place';
        } elseif (substr($game_key, -6) === '-Final') {
            $stage = 'Final';
        }

        return array(
            'event' => $event,
            'stage' => $stage,
        );
    }

    private function datetime_local_value($mysql_datetime) {
        $mysql_datetime = trim((string) $mysql_datetime);
        if ($mysql_datetime === '') {
            return '';
        }

        return str_replace(' ', 'T', substr($mysql_datetime, 0, 16));
    }

    private function sanitize_placement_datetime($value) {
        $value = sanitize_text_field(wp_unslash($value));
        $value = str_replace('T', ' ', trim($value));
        if ($value === '') {
            return '';
        }
        if (preg_match('/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/', $value)) {
            return $value . ':00';
        }
        if (preg_match('/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/', $value)) {
            return $value;
        }

        return '';
    }

    private function get_playoff_placement_rows($schedule_version) {
        global $wpdb;

        $template = $this->playoff_placement_template();
        $rows_by_key = array();
        $schedule_version = absint($schedule_version);
        if ($schedule_version) {
            $table_schedules = vaysf_get_table_name('schedules');
            $table_results = vaysf_get_table_name('results');
            $game_keys = array_keys($template);
            $placeholders = implode(', ', array_fill(0, count($game_keys), '%s'));
            $sql = "SELECT s.*, r.result_id, r.score_json
                FROM $table_schedules s
                LEFT JOIN $table_results r ON r.schedule_id = s.schedule_id
                WHERE s.schedule_version = %d
                  AND s.game_key IN ($placeholders)";
            $query_args = array_merge(array($schedule_version), $game_keys);
            $rows = $wpdb->get_results($wpdb->prepare($sql, $query_args), ARRAY_A);
            if (is_array($rows)) {
                foreach ($rows as $row) {
                    $rows_by_key[(string) ($row['game_key'] ?? '')] = $row;
                }
            }
        }

        $placements = array();
        foreach ($template as $game_key => $defaults) {
            $row = $rows_by_key[$game_key] ?? null;
            $protected = $row
                ? ($this->is_protected_schedule_status((string) ($row['game_status'] ?? '')) || !empty($row['result_id']) || trim((string) ($row['score_json'] ?? '')) !== '')
                : false;
            $placements[] = array(
                'game_key' => $game_key,
                'row' => $row,
                'defaults' => $defaults,
                'protected' => $protected,
                'needs_values' => $this->placement_row_needs_values($row),
            );
        }

        return $placements;
    }

    private function save_playoff_placements_from_post($schedule_version) {
        global $wpdb;

        if (!current_user_can('sf2025_write')) {
            return new WP_Error('vaysf_forbidden', 'You are not allowed to place playoff schedule rows.');
        }

        $schedule_version = absint($schedule_version);
        if (!$schedule_version) {
            return new WP_Error('vaysf_schedule_version_required', 'A schedule version is required.');
        }

        $submitted = isset($_POST['placements']) && is_array($_POST['placements'])
            ? wp_unslash($_POST['placements'])
            : array();
        if (!$submitted) {
            return new WP_Error('vaysf_playoff_placement_empty', 'No playoff placement rows were submitted.');
        }

        $template = $this->playoff_placement_template();
        $table_schedules = vaysf_get_table_name('schedules');
        $updated_count = 0;
        $created_count = 0;
        $skipped_count = 0;
        $selected_count = 0;

        foreach ($submitted as $game_key_raw => $posted) {
            $game_key = sanitize_text_field($game_key_raw);
            if (!isset($template[$game_key]) || !is_array($posted) || empty($posted['apply'])) {
                continue;
            }
            $selected_count++;

            $existing = $wpdb->get_row(
                $wpdb->prepare(
                    "SELECT * FROM $table_schedules WHERE game_key = %s AND schedule_version = %d",
                    $game_key,
                    $schedule_version
                ),
                ARRAY_A
            );
            if ($existing && ($this->is_protected_schedule_status((string) ($existing['game_status'] ?? '')) || vaysf_schedule_row_has_protected_result($existing))) {
                $skipped_count++;
                continue;
            }

            $scheduled_time = $this->sanitize_placement_datetime($posted['scheduled_time'] ?? '');
            $scheduled_slot = sanitize_text_field($posted['scheduled_slot'] ?? '');
            $resource_id = sanitize_text_field($posted['resource_id'] ?? '');
            $scheduled_location = sanitize_text_field($posted['scheduled_location'] ?? '');
            if ($scheduled_time === '' || $scheduled_slot === '' || $resource_id === '' || $scheduled_location === '') {
                return new WP_Error('vaysf_playoff_placement_incomplete', sprintf('Placement for %s is missing time, slot, resource, or location.', $game_key));
            }

            if ($existing) {
                $merged = array_merge($existing, array(
                    'resource_id' => $resource_id,
                    'scheduled_slot' => $scheduled_slot,
                ));
            } else {
                $metadata = $this->playoff_placement_row_metadata($game_key);
                $merged = array_merge(array(
                    'game_key' => $game_key,
                    'schedule_version' => $schedule_version,
                    'event' => $metadata['event'],
                    'stage' => $metadata['stage'],
                    'pool_id' => null,
                    'round_number' => null,
                    'sub_event' => null,
                    'team_a_key' => null,
                    'team_a_label' => null,
                    'team_b_key' => null,
                    'team_b_label' => null,
                    'team_c_key' => null,
                    'team_c_label' => null,
                    'team_ids_json' => null,
                ), array(
                    'resource_id' => $resource_id,
                    'scheduled_slot' => $scheduled_slot,
                ));
            }
            $source_hash = $this->compute_schedule_source_hash($merged);
            $data = array(
                'resource_id' => $resource_id,
                'scheduled_slot' => $scheduled_slot,
                'scheduled_time' => $scheduled_time,
                'scheduled_location' => $scheduled_location,
                'source_hash' => $source_hash,
                'published_at' => !empty($existing['published_at']) ? $existing['published_at'] : current_time('mysql'),
                'updated_at' => current_time('mysql'),
            );

            if ($existing) {
                $result = $wpdb->update(
                    $table_schedules,
                    $data,
                    array(
                        'schedule_id' => absint($existing['schedule_id']),
                        'schedule_version' => $schedule_version,
                    ),
                    array('%s', '%s', '%s', '%s', '%s', '%s', '%s'),
                    array('%d', '%d')
                );
            } else {
                $metadata = $this->playoff_placement_row_metadata($game_key);
                $data = array_merge(array(
                    'game_key' => $game_key,
                    'schedule_version' => $schedule_version,
                    'event' => $metadata['event'],
                    'stage' => $metadata['stage'],
                    'pool_id' => null,
                    'round_number' => null,
                    'sub_event' => null,
                    'team_a_key' => null,
                    'team_a_label' => null,
                    'team_b_key' => null,
                    'team_b_label' => null,
                    'team_c_key' => null,
                    'team_c_label' => null,
                    'team_ids_json' => null,
                    'game_status' => 'scheduled',
                    'created_at' => current_time('mysql'),
                ), $data);
                $result = $wpdb->insert(
                    $table_schedules,
                    $data,
                    array('%s', '%d', '%s', '%s', '%s', '%d', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s')
                );
            }
            if ($result === false) {
                return new WP_Error('vaysf_playoff_placement_failed', sprintf('Could not update playoff placement for %s.', $game_key));
            }
            if ($existing) {
                $updated_count++;
            } else {
                $created_count++;
            }
        }

        if (!$selected_count) {
            return new WP_Error('vaysf_playoff_placement_none_selected', 'Select at least one playoff row to place.');
        }

        if (!$updated_count && !$created_count && $skipped_count) {
            return new WP_Error('vaysf_playoff_placement_all_skipped', 'No rows were updated; selected rows were missing or protected.');
        }

        return array(
            'updated' => $updated_count,
            'created' => $created_count,
            'skipped' => $skipped_count,
        );
    }

    private function render_playoff_placement_panel($schedule_version, $publish_export_url) {
        if (!current_user_can('sf2025_write') || !$schedule_version) {
            return;
        }

        $placements = $this->get_playoff_placement_rows($schedule_version);
        $missing_count = 0;
        foreach ($placements as $placement) {
            if (!empty($placement['needs_values'])) {
                $missing_count++;
            }
        }
        ?>
        <div class="card" style="max-width: none; margin-top: 16px;">
            <h2>Playoff Placement From Manager Schedule</h2>
            <p>
                Fill venue/time data for the Basketball, Volleyball, and Bible Challenge playoff rows in schedule version
                <strong><?php echo esc_html($schedule_version); ?></strong>. This only updates placement fields; teams, brackets, and results are not changed.
            </p>
            <p>
                <a class="button" href="<?php echo esc_url($publish_export_url); ?>">Download Publish JSON ZIP after saving</a>
                <span class="description"><?php echo esc_html($missing_count); ?> template row(s) are missing at least one placement field.</span>
            </p>
            <form method="post">
                <?php wp_nonce_field('save_playoff_placements_' . absint($schedule_version)); ?>
                <input type="hidden" name="vaysf_action" value="save_playoff_placements">
                <input type="hidden" name="schedule_version" value="<?php echo esc_attr($schedule_version); ?>">
                <table class="wp-list-table widefat striped">
                    <thead>
                        <tr>
                            <th>Apply</th>
                            <th>Game Key</th>
                            <th>Current Row</th>
                            <th>Scheduled Time</th>
                            <th>Slot</th>
                            <th>Resource</th>
                            <th>Location</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($placements as $placement) : ?>
                            <?php
                            $row = $placement['row'];
                            $defaults = $placement['defaults'];
                            $protected = !empty($placement['protected']);
                            $missing = !empty($placement['needs_values']);
                            $values = array();
                            foreach (array('scheduled_time', 'scheduled_slot', 'resource_id', 'scheduled_location') as $field) {
                                $current = $row ? trim((string) ($row[$field] ?? '')) : '';
                                $values[$field] = $current !== '' ? $current : $defaults[$field];
                            }
                            ?>
                            <tr>
                                <td>
                                    <?php if ($protected) : ?>
                                        <span class="dashicons dashicons-lock" title="Protected/scored row"></span>
                                    <?php else : ?>
                                        <input type="checkbox" name="placements[<?php echo esc_attr($placement['game_key']); ?>][apply]" value="1" <?php checked($missing); ?>>
                                    <?php endif; ?>
                                </td>
                                <td><strong><?php echo esc_html($placement['game_key']); ?></strong></td>
                                <td>
                                    <?php if (!$row) : ?>
                                        <span class="description">Will create blank row</span>
                                    <?php else : ?>
                                        <?php echo esc_html($row['event'] ?? ''); ?><br>
                                        <small><?php echo esc_html(trim(($row['stage'] ?? '') . ' ' . ($row['game_status'] ?? ''))); ?></small>
                                    <?php endif; ?>
                                </td>
                                <td><input type="datetime-local" name="placements[<?php echo esc_attr($placement['game_key']); ?>][scheduled_time]" value="<?php echo esc_attr($this->datetime_local_value($values['scheduled_time'])); ?>" <?php disabled($protected); ?>></td>
                                <td><input name="placements[<?php echo esc_attr($placement['game_key']); ?>][scheduled_slot]" value="<?php echo esc_attr($values['scheduled_slot']); ?>" <?php disabled($protected); ?>></td>
                                <td><input name="placements[<?php echo esc_attr($placement['game_key']); ?>][resource_id]" value="<?php echo esc_attr($values['resource_id']); ?>" <?php disabled($protected); ?>></td>
                                <td><input class="regular-text" name="placements[<?php echo esc_attr($placement['game_key']); ?>][scheduled_location]" value="<?php echo esc_attr($values['scheduled_location']); ?>" <?php disabled($protected); ?>></td>
                            </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
                <p>
                    <label><input type="checkbox" required> I reviewed the manager schedule image and understand this writes placement fields directly to WordPress.</label>
                </p>
                <?php submit_button('Save Playoff Placements'); ?>
            </form>
        </div>
        <?php
    }

    private function render_schedule_form($schedule = array()) {
        $schedule_id = isset($schedule['schedule_id']) ? absint($schedule['schedule_id']) : 0;
        $action = $schedule_id ? 'save_schedule' : 'create_schedule';
        $nonce_action = $action . '_' . $schedule_id;
        $statuses = $this->schedule_status_options();
        ?>
        <form method="post" class="vaysf-admin-form">
            <?php wp_nonce_field($nonce_action); ?>
            <input type="hidden" name="vaysf_action" value="<?php echo esc_attr($action); ?>">
            <input type="hidden" name="schedule_id" value="<?php echo esc_attr($schedule_id); ?>">
            <table class="form-table" role="presentation">
                <tr>
                    <th><label for="game_key">Game Key</label></th>
                    <td><input name="game_key" id="game_key" class="regular-text" required value="<?php echo esc_attr($schedule['game_key'] ?? ''); ?>"></td>
                </tr>
                <tr>
                    <th><label for="schedule_version">Schedule Version</label></th>
                    <td><input name="schedule_version" id="schedule_version" type="number" min="0" value="<?php echo esc_attr($schedule['schedule_version'] ?? 0); ?>"></td>
                </tr>
                <tr>
                    <th>Event Metadata</th>
                    <td>
                        <input name="event" placeholder="Event" value="<?php echo esc_attr($schedule['event'] ?? ''); ?>">
                        <input name="stage" placeholder="Stage" value="<?php echo esc_attr($schedule['stage'] ?? ''); ?>">
                        <input name="pool_id" placeholder="Pool" value="<?php echo esc_attr($schedule['pool_id'] ?? ''); ?>">
                        <input name="round_number" type="number" min="0" placeholder="Round" value="<?php echo esc_attr($schedule['round_number'] ?? ''); ?>">
                        <input name="sub_event" placeholder="Sub-event" value="<?php echo esc_attr($schedule['sub_event'] ?? ''); ?>">
                    </td>
                </tr>
                <tr>
                    <th>Teams</th>
                    <td>
                        <p><input name="team_a_key" placeholder="Team A key" value="<?php echo esc_attr($schedule['team_a_key'] ?? ''); ?>"> <input class="regular-text" name="team_a_label" placeholder="Team A label" value="<?php echo esc_attr($schedule['team_a_label'] ?? ''); ?>"></p>
                        <p><input name="team_b_key" placeholder="Team B key" value="<?php echo esc_attr($schedule['team_b_key'] ?? ''); ?>"> <input class="regular-text" name="team_b_label" placeholder="Team B label" value="<?php echo esc_attr($schedule['team_b_label'] ?? ''); ?>"></p>
                        <p><input name="team_c_key" placeholder="Team C key" value="<?php echo esc_attr($schedule['team_c_key'] ?? ''); ?>"> <input class="regular-text" name="team_c_label" placeholder="Team C label" value="<?php echo esc_attr($schedule['team_c_label'] ?? ''); ?>"></p>
                        <textarea name="team_ids_json" rows="3" class="large-text code" placeholder='["TEAM-A","TEAM-B"]'><?php echo esc_textarea($schedule['team_ids_json'] ?? ''); ?></textarea>
                    </td>
                </tr>
                <tr>
                    <th>Schedule</th>
                    <td>
                        <input name="resource_id" placeholder="Resource ID" value="<?php echo esc_attr($schedule['resource_id'] ?? ''); ?>">
                        <input name="scheduled_slot" placeholder="Slot" value="<?php echo esc_attr($schedule['scheduled_slot'] ?? ''); ?>">
                        <input name="scheduled_time" placeholder="YYYY-MM-DD HH:MM:SS" value="<?php echo esc_attr($schedule['scheduled_time'] ?? ''); ?>">
                        <input class="regular-text" name="scheduled_location" placeholder="Location" value="<?php echo esc_attr($schedule['scheduled_location'] ?? ''); ?>">
                    </td>
                </tr>
                <tr>
                    <th><label for="game_status">Status</label></th>
                    <td>
                        <select name="game_status" id="game_status">
                            <?php foreach ($statuses as $status) : ?>
                                <option value="<?php echo esc_attr($status); ?>" <?php selected($schedule['game_status'] ?? 'scheduled', $status); ?>><?php echo esc_html($status); ?></option>
                            <?php endforeach; ?>
                        </select>
                        <label><input type="checkbox" name="synced_to_chmeetings" value="1" <?php checked(!empty($schedule['synced_to_chmeetings'])); ?>> Synced to ChMeetings</label>
                    </td>
                </tr>
                <tr>
                    <th>Guards</th>
                    <td>
                        <label><input type="checkbox" name="confirm_protected" value="1"> I understand this may change a protected reported/official/under-review row.</label><br>
                        <label><input type="checkbox" name="confirm_cancel" value="1"> I understand cancelled games follow the force-cancel path and should not be hard-deleted.</label>
                    </td>
                </tr>
            </table>
            <?php submit_button($schedule_id ? 'Save Schedule' : 'Create Schedule'); ?>
        </form>
        <?php
    }

    /**
     * Display event-day schedules admin page.
     */
    public function display_schedules_page() {
        global $wpdb;

        $table_schedules = vaysf_get_table_name('schedules');
        $vaysf_action = isset($_POST['vaysf_action']) ? sanitize_text_field(wp_unslash($_POST['vaysf_action'])) : '';
        $schedule_id = isset($_POST['schedule_id'])
            ? absint($_POST['schedule_id'])
            : (isset($_REQUEST['id']) ? absint($_REQUEST['id']) : 0);

        if ($vaysf_action === 'save_schedule' || $vaysf_action === 'create_schedule') {
            $nonce_action = $vaysf_action . '_' . $schedule_id;
            if (!isset($_POST['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'])), $nonce_action)) {
                $this->print_admin_notice(new WP_Error('vaysf_bad_nonce', 'Invalid schedule request.'), '');
            } else {
                $this->print_admin_notice($this->save_schedule_from_post($schedule_id), 'Schedule saved.');
            }
        } elseif ($vaysf_action === 'cancel_schedule') {
            if (!isset($_POST['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'])), 'cancel_schedule_' . $schedule_id)) {
                $this->print_admin_notice(new WP_Error('vaysf_bad_nonce', 'Invalid schedule cancellation request.'), '');
            } else {
                $this->print_admin_notice($this->cancel_schedule_from_post($schedule_id), 'Schedule cancelled.');
            }
        } elseif ($vaysf_action === 'save_playoff_placements') {
            $placement_schedule_version = isset($_POST['schedule_version']) ? absint($_POST['schedule_version']) : 0;
            if (!isset($_POST['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'])), 'save_playoff_placements_' . $placement_schedule_version)) {
                $this->print_admin_notice(new WP_Error('vaysf_bad_nonce', 'Invalid playoff placement request.'), '');
            } else {
                $this->print_admin_notice($this->save_playoff_placements_from_post($placement_schedule_version), 'Playoff placements saved.');
            }
        }

        $action = isset($_GET['action']) ? sanitize_text_field(wp_unslash($_GET['action'])) : '';
        if ($action === 'new' || ($action === 'edit' && $schedule_id)) {
            $schedule = array();
            if ($schedule_id) {
                $schedule = $wpdb->get_row(
                    $wpdb->prepare("SELECT * FROM $table_schedules WHERE schedule_id = %d", $schedule_id),
                    ARRAY_A
                );
            }
            ?>
            <div class="wrap">
                <h1><?php echo $schedule_id ? 'Edit Schedule' : 'Create Schedule'; ?></h1>
                <p><a class="button" href="<?php echo esc_url(admin_url('admin.php?page=vaysf-schedules')); ?>">Back to Schedules</a></p>
                <?php
                if ($schedule_id && !$schedule) {
                    echo '<div class="notice notice-error"><p>Schedule row not found.</p></div>';
                } else {
                    $this->render_schedule_form($schedule ?: array('game_status' => 'scheduled'));
                }
                ?>
            </div>
            <?php
            return;
        }

        $event_filter = isset($_GET['event']) ? sanitize_text_field(wp_unslash($_GET['event'])) : '';
        $status_filter = isset($_GET['game_status']) ? sanitize_text_field(wp_unslash($_GET['game_status'])) : '';
        $version_filter = isset($_GET['schedule_version']) && $_GET['schedule_version'] !== '' ? absint($_GET['schedule_version']) : null;
        $paged = max(1, isset($_GET['paged']) ? absint($_GET['paged']) : 1);
        $per_page = 50;
        $offset = ($paged - 1) * $per_page;

        $where = array();
        $args = array();
        if ($event_filter !== '') {
            $where[] = 'event = %s';
            $args[] = $event_filter;
        }
        if ($status_filter !== '') {
            $where[] = 'game_status = %s';
            $args[] = $status_filter;
        }
        if ($version_filter !== null) {
            $where[] = 'schedule_version = %d';
            $args[] = $version_filter;
        }
        $where_clause = $where ? 'WHERE ' . implode(' AND ', $where) : '';

        $count_sql = "SELECT COUNT(*) FROM $table_schedules $where_clause";
        $total_items = $args ? (int) $wpdb->get_var($wpdb->prepare($count_sql, $args)) : (int) $wpdb->get_var($count_sql);
        $query_args = array_merge($args, array($per_page, $offset));
        $query_sql = "SELECT * FROM $table_schedules $where_clause ORDER BY schedule_version DESC, scheduled_time IS NULL, scheduled_time, schedule_id LIMIT %d OFFSET %d";
        $schedules = $wpdb->get_results($wpdb->prepare($query_sql, $query_args), ARRAY_A);
        $events = $wpdb->get_col("SELECT DISTINCT event FROM $table_schedules WHERE event IS NOT NULL AND event <> '' ORDER BY event");
        $versions = $wpdb->get_col("SELECT DISTINCT schedule_version FROM $table_schedules ORDER BY schedule_version DESC");
        $total_pages = max(1, (int) ceil($total_items / $per_page));
        $current_schedule_version = function_exists('vaysf_get_current_published_schedule_version')
            ? vaysf_get_current_published_schedule_version()
            : null;
        $export_schedule_version = $version_filter !== null
            ? $version_filter
            : ($current_schedule_version !== null ? absint($current_schedule_version) : 0);
        $export_url = wp_nonce_url(
            add_query_arg(
                array(
                    'action' => 'vaysf_download_event_day_state_json',
                    'schedule_version' => $export_schedule_version,
                ),
                admin_url('admin-post.php')
            ),
            'vaysf_download_event_day_state_json'
        );
        $publish_export_url = wp_nonce_url(
            add_query_arg(
                array(
                    'action' => 'vaysf_download_event_day_publish_zip',
                    'schedule_version' => $export_schedule_version,
                ),
                admin_url('admin-post.php')
            ),
            'vaysf_download_event_day_publish_zip'
        );
        ?>
        <div class="wrap">
            <h1>
                Schedules
                <a href="<?php echo esc_url(admin_url('admin.php?page=vaysf-schedules&action=new')); ?>" class="page-title-action">Add New</a>
                <?php if ($export_schedule_version) : ?>
                    <a href="<?php echo esc_url($publish_export_url); ?>" class="page-title-action">Export Publish JSON ZIP</a>
                    <?php if (current_user_can('sf2025_admin')) : ?>
                        <a href="<?php echo esc_url($export_url); ?>" class="page-title-action">Export State JSON</a>
                    <?php endif; ?>
                <?php endif; ?>
            </h1>
            <?php if ($export_schedule_version) : ?>
                <p class="description">
                    Publish ZIP downloads `approved_schedule_input.json` and `approved_schedule_output.json` reconstructed from WordPress schedule version
                    <?php echo esc_html($export_schedule_version); ?> for local middleware replay.
                    <?php if (current_user_can('sf2025_admin')) : ?>
                        State JSON downloads the raw schedules, results, revisions, and pool confirmations backup.
                    <?php endif; ?>
                </p>
            <?php endif; ?>
            <?php $this->render_playoff_placement_panel($export_schedule_version, $publish_export_url); ?>
            <form method="get" class="tablenav top">
                <input type="hidden" name="page" value="vaysf-schedules">
                <select name="event">
                    <option value="">All events</option>
                    <?php foreach ($events as $event) : ?>
                        <option value="<?php echo esc_attr($event); ?>" <?php selected($event_filter, $event); ?>><?php echo esc_html($event); ?></option>
                    <?php endforeach; ?>
                </select>
                <select name="game_status">
                    <option value="">All statuses</option>
                    <?php foreach ($this->schedule_status_options() as $status) : ?>
                        <option value="<?php echo esc_attr($status); ?>" <?php selected($status_filter, $status); ?>><?php echo esc_html($status); ?></option>
                    <?php endforeach; ?>
                </select>
                <select name="schedule_version">
                    <option value="">All versions</option>
                    <?php foreach ($versions as $version) : ?>
                        <option value="<?php echo esc_attr($version); ?>" <?php selected((string) $version_filter, (string) $version); ?>><?php echo esc_html($version); ?></option>
                    <?php endforeach; ?>
                </select>
                <input type="submit" class="button" value="Filter">
            </form>
            <table class="wp-list-table widefat fixed striped">
                <thead>
                    <tr>
                        <th>Game Key</th>
                        <th>Event / Stage / Pool</th>
                        <th>Teams</th>
                        <th>Resource / Slot</th>
                        <th>Status</th>
                        <th>Published</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    <?php if (!$schedules) : ?>
                        <tr><td colspan="7">No schedule rows found.</td></tr>
                    <?php else : ?>
                        <?php foreach ($schedules as $schedule) : ?>
                            <tr>
                                <td><strong><?php echo esc_html($schedule['game_key']); ?></strong><br><small>ID <?php echo esc_html($schedule['schedule_id']); ?> | v<?php echo esc_html($schedule['schedule_version']); ?></small></td>
                                <td><?php echo esc_html($schedule['event']); ?><br><small><?php echo esc_html(trim(($schedule['stage'] ?: '') . ' ' . ($schedule['pool_id'] ?: ''))); ?></small></td>
                                <td><?php echo esc_html($this->format_game_teams($schedule)); ?></td>
                                <td><?php echo esc_html($schedule['resource_id']); ?><br><small><?php echo esc_html($schedule['scheduled_slot']); ?></small></td>
                                <td><?php echo esc_html($schedule['game_status']); ?></td>
                                <td><?php echo esc_html($schedule['published_at'] ?: '-'); ?></td>
                                <td>
                                    <a class="button button-small" href="<?php echo esc_url(admin_url('admin.php?page=vaysf-schedules&action=edit&id=' . $schedule['schedule_id'])); ?>">Edit</a>
                                    <?php if ($schedule['game_status'] !== 'cancelled') : ?>
                                        <?php
                                        $row_is_protected = $this->is_protected_schedule_status($schedule['game_status']);
                                        $cancel_confirm_message = $row_is_protected
                                            ? sprintf(
                                                'This game is currently "%s" (protected — reported/official/under review). '
                                                . 'Cancelling it marks a completed or in-review match as cancelled. '
                                                . 'This does not hard-delete it, but is a significant action. Continue?',
                                                $schedule['game_status']
                                            )
                                            : 'Cancel this schedule row? This does not hard-delete it.';
                                        ?>
                                        <form method="post" style="display:inline;">
                                            <?php wp_nonce_field('cancel_schedule_' . $schedule['schedule_id']); ?>
                                            <input type="hidden" name="vaysf_action" value="cancel_schedule">
                                            <input type="hidden" name="id" value="<?php echo esc_attr($schedule['schedule_id']); ?>">
                                            <input type="hidden" name="confirm_cancel" value="1">
                                            <?php if ($row_is_protected) : ?>
                                                <input type="hidden" name="confirm_protected" value="1">
                                            <?php endif; ?>
                                            <button type="submit" class="button button-small<?php echo $row_is_protected ? ' button-link-delete' : ''; ?>" onclick="return confirm('<?php echo esc_js($cancel_confirm_message); ?>');"><?php echo $row_is_protected ? 'Cancel (protected)' : 'Cancel'; ?></button>
                                        </form>
                                    <?php endif; ?>
                                </td>
                            </tr>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </tbody>
            </table>
            <div class="tablenav bottom">
                <div class="tablenav-pages">
                    <span class="displaying-num"><?php echo esc_html($total_items); ?> row(s)</span>
                    <?php
                    $base_args = array(
                        'page' => 'vaysf-schedules',
                        'event' => $event_filter,
                        'game_status' => $status_filter,
                    );
                    if ($version_filter !== null) {
                        $base_args['schedule_version'] = $version_filter;
                    }
                    if ($paged > 1) {
                        echo '<a class="button" href="' . esc_url(add_query_arg(array_merge($base_args, array('paged' => $paged - 1)), admin_url('admin.php'))) . '">&laquo; Previous</a> ';
                    }
                    echo '<span class="paging-input">Page ' . esc_html($paged) . ' of ' . esc_html($total_pages) . '</span>';
                    if ($paged < $total_pages) {
                        echo ' <a class="button" href="' . esc_url(add_query_arg(array_merge($base_args, array('paged' => $paged + 1)), admin_url('admin.php'))) . '">Next &raquo;</a>';
                    }
                    ?>
                </div>
            </div>
        </div>
        <?php
    }
}

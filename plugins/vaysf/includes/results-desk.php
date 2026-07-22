<?php
/**
 * File: includes/results-desk.php
 * Description: Manager/admin Results Desk helpers for event-day operations (Issue #208)
 * Version: 1.0.0
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

/**
 * Check whether a user may view the Results Desk.
 *
 * @param int|null $user_id WordPress user id; defaults to current user
 * @return bool
 */
function vaysf_user_can_view_results_desk($user_id = null) {
    $user_id = $user_id === null ? get_current_user_id() : absint($user_id);
    if (!$user_id) {
        return false;
    }

    return user_can($user_id, 'manage_options')
        || user_can($user_id, 'sf2025_admin')
        || user_can($user_id, 'sf2025_write');
}

/**
 * Check whether a user may preview/reassign/apply Basketball/Volleyball QF
 * matchups — broader than vaysf_user_can_view_results_desk(), since
 * coordinators (sf2025_submit_results, no Results Desk access) are meant to
 * be able to do this from the Coordinator Score Entry screen once a manager
 * has already confirmed QF seeding there. Confirming seeding itself
 * (vaysf_confirm_event_qf_seeding()) and the coin-toss flow stay
 * Results-Desk-only — this only broadens preview/reorder/Apply.
 *
 * @param int|null $user_id WordPress user id; defaults to current user
 * @return bool
 */
function vaysf_user_can_manage_team_qf_schedule($user_id = null) {
    $user_id = $user_id === null ? get_current_user_id() : absint($user_id);
    if (!$user_id) {
        return false;
    }

    return vaysf_user_can_view_results_desk($user_id) || user_can($user_id, 'sf2025_submit_results');
}

/**
 * Build the Results Desk route URL.
 *
 * @return string
 */
function vaysf_get_results_desk_url() {
    return site_url('results-desk');
}

/**
 * Reconstruct the current request's full URL from scheme + host +
 * REQUEST_URI, without routing it through home_url().
 *
 * home_url($_SERVER['REQUEST_URI']) looks reasonable but silently doubles
 * any subdirectory already baked into the site's home URL — e.g. a Bluehost
 * staging site mounted at /staging/<id>/, where REQUEST_URI (what the
 * browser actually requested) already includes that prefix, and home_url()
 * prepends it again. The result is an unroutable
 * /staging/<id>/staging/<id>/... URL. Building from host + REQUEST_URI
 * directly avoids that: REQUEST_URI is already an absolute path from the
 * domain root and needs no additional site-path prefix.
 *
 * @return string
 */
function vaysf_results_desk_current_request_url() {
    if (!isset($_SERVER['REQUEST_URI']) || !isset($_SERVER['HTTP_HOST'])) {
        return vaysf_get_results_desk_url();
    }

    $host = sanitize_text_field(wp_unslash($_SERVER['HTTP_HOST']));
    $scheme = is_ssl() ? 'https' : 'http';
    $request_uri = wp_unslash($_SERVER['REQUEST_URI']);

    return esc_url_raw($scheme . '://' . $host . $request_uri);
}

/**
 * Sanitize Results Desk filters from shortcode attributes or query args.
 *
 * @param array<string,mixed> $atts Raw attributes
 * @return array<string,mixed>
 */
function vaysf_sanitize_results_desk_filters($atts = array()) {
    $event = isset($atts['event']) ? sanitize_text_field(wp_unslash($atts['event'])) : '';
    if ($event === '' && isset($_GET['event'])) {
        $event = sanitize_text_field(wp_unslash($_GET['event']));
    }

    $church = isset($atts['church']) ? vaysf_sanitize_public_church_filter($atts['church']) : '';
    if ($church === '' && isset($_GET['church'])) {
        $church = vaysf_sanitize_public_church_filter($_GET['church']);
    }

    $late_grace_minutes = isset($atts['late_grace_minutes']) ? absint($atts['late_grace_minutes']) : 75;
    if ($late_grace_minutes < 1) {
        $late_grace_minutes = 75;
    }

    $revision_hours = isset($atts['revision_hours']) ? absint($atts['revision_hours']) : 12;
    if ($revision_hours < 1) {
        $revision_hours = 12;
    }

    $limit = isset($atts['limit']) ? absint($atts['limit']) : 50;
    if ($limit < 1) {
        $limit = 50;
    }
    $limit = min($limit, 200);

    return array(
        'event' => $event,
        'church' => $church,
        'late_grace_minutes' => $late_grace_minutes,
        'revision_hours' => $revision_hours,
        'limit' => $limit,
    );
}

/**
 * Add an event filter clause for Results Desk SQL.
 *
 * @param array<int,string> $where SQL WHERE fragments
 * @param array<int,mixed> $args SQL prepare args
 * @param string $event Event filter
 * @param string $alias Schedule table alias
 * @return void
 */
function vaysf_results_desk_add_event_filter(&$where, &$args, $event, $alias = 's') {
    if ($event === '') {
        return;
    }

    $where[] = "{$alias}.event = %s";
    $args[] = $event;
}

/**
 * Add a church-code filter clause for Results Desk SQL.
 *
 * Matches team_*_church_code directly, falling back to team_*_key/label
 * (taking the token after a trailing "::", the historical church-code-style
 * key format) when the dedicated column is empty — the same fallback tiers
 * as vaysf_resolve_row_slot_church_code() in public-display.php, expressed
 * in SQL so it works across GROUP BY aggregates in Results Desk queries.
 *
 * @param array<int,string> $where SQL WHERE fragments
 * @param array<int,mixed> $args SQL prepare args
 * @param string $church Uppercase church code filter
 * @param string $alias Schedule table alias
 * @return void
 */
function vaysf_results_desk_add_church_filter(&$where, &$args, $church, $alias = 's') {
    if ($church === '') {
        return;
    }

    $conditions = array();
    foreach (array('a', 'b', 'c') as $slot) {
        $conditions[] = "UPPER(COALESCE({$alias}.team_{$slot}_church_code, '')) = %s";
        $args[] = $church;
        $conditions[] = "UPPER(TRIM(SUBSTRING_INDEX(COALESCE({$alias}.team_{$slot}_key, ''), '::', -1))) = %s";
        $args[] = $church;
        $conditions[] = "UPPER(TRIM(SUBSTRING_INDEX(COALESCE({$alias}.team_{$slot}_label, ''), '::', -1))) = %s";
        $args[] = $church;
    }

    $where[] = '(' . implode(' OR ', $conditions) . ')';
}

/**
 * Format a DateTimeImmutable as a MySQL DATETIME string.
 *
 * @param DateTimeImmutable $datetime Date/time to format
 * @return string
 */
function vaysf_results_desk_mysql_datetime($datetime) {
    return $datetime->format('Y-m-d H:i:s');
}

/**
 * Return the DateTime cutoff for schedule wall-clock comparisons.
 *
 * Schedule rows are stored as Sports Fest local wall-clock time, so overdue
 * game comparisons must use that same clock rather than the WordPress/server
 * timezone.
 *
 * @param int $minutes Grace period in minutes
 * @return DateTimeImmutable
 */
function vaysf_results_desk_schedule_cutoff_datetime($minutes) {
    return vaysf_get_sports_fest_now()->modify('-' . absint($minutes) . ' minutes');
}

/**
 * Return a cutoff for WordPress-stored activity timestamps.
 *
 * Result revisions and update timestamps are written with current_time('mysql'),
 * so rolling activity windows should stay in the WordPress timezone used for
 * those stored DATETIME values.
 *
 * @param int $hours Lookback window in hours
 * @return string MySQL DATETIME string in the WordPress timezone
 */
function vaysf_results_desk_activity_cutoff($hours) {
    return vaysf_results_desk_mysql_datetime(
        (new DateTimeImmutable('now', wp_timezone()))->modify('-' . absint($hours) . ' hours')
    );
}

/**
 * Return late/missing schedule rows, honoring scheduled_slot fallbacks.
 *
 * @param array<string,mixed> $filters Sanitized filters
 * @param int|null $limit Maximum rows; null uses filter limit, 0 means no limit
 * @return array<int,array<string,mixed>>
 */
function vaysf_get_results_desk_late_missing_rows($filters = array(), $limit = null) {
    global $wpdb;

    $schedule_version = vaysf_get_current_published_schedule_version();
    if ($schedule_version === null) {
        return array();
    }

    $filters = vaysf_sanitize_results_desk_filters($filters);
    if ($limit === null) {
        $limit = absint($filters['limit']);
    } else {
        $limit = absint($limit);
    }

    $table_schedules = vaysf_get_table_name('schedules');
    $table_results = vaysf_get_table_name('results');
    $where = array(
        's.schedule_version = %d',
        's.published_at IS NOT NULL',
        "COALESCE(s.game_status, '') <> 'cancelled'",
        "(r.result_id IS NULL OR COALESCE(r.score_json, '') = '')",
    );
    $args = array($schedule_version);
    vaysf_results_desk_add_event_filter($where, $args, $filters['event']);
    vaysf_results_desk_add_church_filter($where, $args, $filters['church']);

    $sql = "SELECT s.*, r.result_id, r.public_status, r.scan_status, r.updated_at AS result_updated_at
        FROM $table_schedules s
        LEFT JOIN $table_results r ON r.schedule_id = s.schedule_id
        WHERE " . implode(' AND ', $where);

    $rows = $wpdb->get_results($wpdb->prepare($sql, $args), ARRAY_A);
    if (!is_array($rows)) {
        return array();
    }

    $cutoff = vaysf_results_desk_schedule_cutoff_datetime($filters['late_grace_minutes']);
    $late_rows = array();
    foreach ($rows as $row) {
        $competition_at = vaysf_get_schedule_competition_datetime($row);
        if ($competition_at instanceof DateTimeImmutable && $competition_at <= $cutoff) {
            $late_rows[] = $row;
        }
    }

    $late_rows = vaysf_sort_public_schedule_rows_by_competition_time($late_rows);

    if ($limit > 0) {
        return array_slice($late_rows, 0, $limit);
    }

    return $late_rows;
}

/**
 * Fetch one Results Desk dataset.
 *
 * @param string $section Section key
 * @param array<string,mixed> $filters Sanitized filters
 * @return array<int,array<string,mixed>>
 */
function vaysf_get_results_desk_rows($section, $filters = array()) {
    global $wpdb;

    $schedule_version = vaysf_get_current_published_schedule_version();
    if ($schedule_version === null) {
        return array();
    }

    $filters = vaysf_sanitize_results_desk_filters($filters);
    $table_schedules = vaysf_get_table_name('schedules');
    $table_results = vaysf_get_table_name('results');
    $table_revisions = vaysf_get_table_name('result_revisions');
    $table_files = vaysf_get_table_name('result_files');
    $limit = absint($filters['limit']);

    $base_where = array(
        's.schedule_version = %d',
        's.published_at IS NOT NULL',
        "COALESCE(s.game_status, '') <> 'cancelled'",
    );
    $base_args = array($schedule_version);
    vaysf_results_desk_add_event_filter($base_where, $base_args, $filters['event']);
    vaysf_results_desk_add_church_filter($base_where, $base_args, $filters['church']);

    if ($section === 'late_missing') {
        return vaysf_get_results_desk_late_missing_rows($filters, $limit);
    }

    if ($section === 'attention') {
        // A first-time submission is accepted as soon as it's reported — it
        // does not sit here waiting for a second person to confirm it. Only
        // a correction (current_revision > 1, i.e. someone submitted a
        // second, different score for the same game) or an explicit
        // in_progress/under_review flag counts as needing human review.
        $where = $base_where;
        $args = $base_args;
        $where[] = 'r.result_id IS NOT NULL';
        $where[] = "(r.current_revision > 1 OR r.public_status IN ('in_progress', 'under_review'))";
        $args[] = $limit;

        $sql = "SELECT s.*, r.result_id, r.public_status, r.scan_status, r.current_revision,
                r.certified_at, r.verified_at, r.correction_reason, r.updated_at AS result_updated_at
            FROM $table_schedules s
            INNER JOIN $table_results r ON r.schedule_id = s.schedule_id
            WHERE " . implode(' AND ', $where) . "
            ORDER BY r.updated_at DESC, s.scheduled_time IS NULL, s.scheduled_time
            LIMIT %d";

        $rows = $wpdb->get_results($wpdb->prepare($sql, $args), ARRAY_A);
        return is_array($rows) ? $rows : array();
    }

    if ($section === 'recent_corrections') {
        $where = $base_where;
        $args = $base_args;
        $where[] = 'rr.revision_number > 1';
        $where[] = 'rr.submitted_at >= %s';
        $args[] = vaysf_results_desk_activity_cutoff($filters['revision_hours']);
        $args[] = $limit;

        $sql = "SELECT s.*, r.result_id, r.public_status, r.scan_status, r.current_revision,
                rr.revision_id, rr.revision_number, rr.correction_reason, rr.verification_state,
                rr.submitted_by_user_id, rr.submitted_at
            FROM $table_revisions rr
            INNER JOIN $table_results r ON r.result_id = rr.result_id
            INNER JOIN $table_schedules s ON s.schedule_id = r.schedule_id
            WHERE " . implode(' AND ', $where) . "
            ORDER BY rr.submitted_at DESC, rr.revision_id DESC
            LIMIT %d";

        $rows = $wpdb->get_results($wpdb->prepare($sql, $args), ARRAY_A);
        return is_array($rows) ? $rows : array();
    }

    if ($section === 'missing_scans') {
        $where = $base_where;
        $args = $base_args;
        $where[] = 'r.result_id IS NOT NULL';
        $where[] = "COALESCE(r.score_json, '') <> ''";
        $where[] = "COALESCE(r.scan_status, 'pending') IN ('pending', 'missing')";
        $args[] = $limit;

        $sql = "SELECT s.*, r.result_id, r.public_status, r.scan_status, r.current_revision,
                r.certified_at, r.verified_at, r.updated_at AS result_updated_at,
                COUNT(f.file_id) AS file_count
            FROM $table_schedules s
            INNER JOIN $table_results r ON r.schedule_id = s.schedule_id
            LEFT JOIN $table_revisions rr ON rr.result_id = r.result_id
            LEFT JOIN $table_files f ON f.result_revision_id = rr.revision_id
            WHERE " . implode(' AND ', $where) . "
            GROUP BY r.result_id
            HAVING file_count = 0
            ORDER BY r.updated_at DESC, s.scheduled_time IS NULL, s.scheduled_time
            LIMIT %d";

        $rows = $wpdb->get_results($wpdb->prepare($sql, $args), ARRAY_A);
        return is_array($rows) ? $rows : array();
    }

    if ($section === 'pool_progress') {
        return vaysf_get_results_desk_pool_progress_rows($filters, $limit);
    }

    return array();
}

/**
 * Fetch high-level Results Desk counts and heartbeat timestamps.
 *
 * @param array<string,mixed> $filters Sanitized filters
 * @return array<string,mixed>
 */
function vaysf_get_results_desk_summary($filters = array()) {
    global $wpdb;

    $schedule_version = vaysf_get_current_published_schedule_version();
    $empty = array(
        'schedule_version' => null,
        'total_games' => 0,
        'reported_results' => 0,
        'late_missing' => 0,
        'attention' => 0,
        'missing_scans' => 0,
        'recent_corrections' => 0,
        'complete_pools' => 0,
        'last_schedule_update' => '',
        'last_result_update' => '',
        'public_data_updated_at' => '',
        'sports_fest_time' => vaysf_results_desk_mysql_datetime(vaysf_get_sports_fest_now()),
    );

    if ($schedule_version === null) {
        return $empty;
    }

    $filters = vaysf_sanitize_results_desk_filters($filters);
    $table_schedules = vaysf_get_table_name('schedules');
    $table_results = vaysf_get_table_name('results');

    $where = array(
        's.schedule_version = %d',
        's.published_at IS NOT NULL',
        "COALESCE(s.game_status, '') <> 'cancelled'",
    );
    $args = array($schedule_version);
    vaysf_results_desk_add_event_filter($where, $args, $filters['event']);
    vaysf_results_desk_add_church_filter($where, $args, $filters['church']);
    $where_clause = implode(' AND ', $where);

    $summary_sql = "SELECT
            COUNT(*) AS total_games,
            SUM(CASE WHEN r.result_id IS NOT NULL AND COALESCE(r.score_json, '') <> '' THEN 1 ELSE 0 END) AS reported_results,
            SUM(CASE WHEN r.result_id IS NOT NULL AND (r.current_revision > 1 OR r.public_status IN ('in_progress', 'under_review')) THEN 1 ELSE 0 END) AS attention,
            MAX(s.updated_at) AS last_schedule_update,
            MAX(r.updated_at) AS last_result_update
        FROM $table_schedules s
        LEFT JOIN $table_results r ON r.schedule_id = s.schedule_id
        WHERE $where_clause";

    $summary = $wpdb->get_row($wpdb->prepare($summary_sql, $args), ARRAY_A);
    if (!is_array($summary)) {
        $summary = array();
    }

    $last_schedule_update = isset($summary['last_schedule_update']) ? (string) $summary['last_schedule_update'] : '';
    $last_result_update = isset($summary['last_result_update']) ? (string) $summary['last_result_update'] : '';
    $public_data_updated_at = max($last_schedule_update, $last_result_update);
    $pool_progress_rows = vaysf_get_results_desk_rows('pool_progress', array_merge($filters, array('limit' => 200)));
    $complete_pool_count = 0;
    foreach ($pool_progress_rows as $pool_progress_row) {
        if (!empty($pool_progress_row['complete'])) {
            $complete_pool_count++;
        }
    }

    return array_merge($empty, array(
        'schedule_version' => $schedule_version,
        'total_games' => isset($summary['total_games']) ? (int) $summary['total_games'] : 0,
        'reported_results' => isset($summary['reported_results']) ? (int) $summary['reported_results'] : 0,
        'late_missing' => count(vaysf_get_results_desk_late_missing_rows($filters, 0)),
        'attention' => isset($summary['attention']) ? (int) $summary['attention'] : 0,
        'missing_scans' => count(vaysf_get_results_desk_rows('missing_scans', array_merge($filters, array('limit' => 200)))),
        'recent_corrections' => count(vaysf_get_results_desk_rows('recent_corrections', array_merge($filters, array('limit' => 200)))),
        'complete_pools' => $complete_pool_count,
        'last_schedule_update' => $last_schedule_update,
        'last_result_update' => $last_result_update,
        'public_data_updated_at' => $public_data_updated_at,
    ));
}

/**
 * Parse a stored Results Desk timestamp.
 *
 * @param string $mysql_datetime MySQL datetime
 * @param DateTimeZone|null $source_timezone Timezone of the stored value
 * @return DateTimeImmutable|null
 */
function vaysf_parse_results_desk_datetime($mysql_datetime, $source_timezone = null) {
    $mysql_datetime = trim((string) $mysql_datetime);
    if ($mysql_datetime === '') {
        return null;
    }

    if (!$source_timezone instanceof DateTimeZone) {
        $source_timezone = wp_timezone();
    }

    foreach (array('Y-m-d H:i:s', 'Y-m-d H:i') as $format) {
        $parsed = DateTimeImmutable::createFromFormat($format, $mysql_datetime, $source_timezone);
        if ($parsed instanceof DateTimeImmutable) {
            return $parsed;
        }
    }

    try {
        return new DateTimeImmutable($mysql_datetime, $source_timezone);
    } catch (Exception $e) {
        return null;
    }
}

/**
 * Format a Results Desk timestamp for display in Sports Fest local time.
 *
 * @param string $mysql_datetime MySQL datetime
 * @param DateTimeZone|null $source_timezone Timezone of the stored value
 * @return string
 */
function vaysf_format_results_desk_datetime($mysql_datetime, $source_timezone = null) {
    $mysql_datetime = trim((string) $mysql_datetime);
    if ($mysql_datetime === '') {
        return '-';
    }

    $datetime = vaysf_parse_results_desk_datetime($mysql_datetime, $source_timezone);
    if (!$datetime instanceof DateTimeImmutable) {
        return $mysql_datetime;
    }

    return vaysf_format_sports_fest_time($datetime, 'D M j, g:i A T');
}

/**
 * Decode a JSON field into an array.
 *
 * @param mixed $json Raw JSON
 * @return array<int|string,mixed>
 */
function vaysf_results_desk_decode_json_array($json) {
    $json = trim((string) $json);
    if ($json === '') {
        return array();
    }

    $decoded = json_decode($json, true);
    return is_array($decoded) ? $decoded : array();
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
 *        (Issue #207 — feeds head-to-head tiebreak resolution)
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
    // scores present — a 3-team game (e.g. Bible Challenge) has no single
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
 * Ranking order (VAY SM convention confirmed for the 2026 weekend 1→2
 * transition — Issue #207): win/loss record, then point differential, then
 * head-to-head result among teams still fully tied. A group that
 * head-to-head cannot fully order (e.g. a round-robin cycle where every
 * team in the group beat exactly one other team in it) is flagged
 * needs_manual_tiebreak rather than resolved by alphabetical guesswork —
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
                        __('Tied — head-to-head could not resolve order; decide manually.', 'vaysf')
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
 * order when the group's results do not produce a strict ranking — e.g. a
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
        }

        $score_json = trim((string) ($row['score_json'] ?? ''));
        if ($score_json === '') {
            $pool_missing_counts[$pool_id] = ($pool_missing_counts[$pool_id] ?? 0) + 1;
            continue;
        }
        $payload = vaysf_results_desk_decode_json_array($score_json);
        $scores = vaysf_results_desk_pool_score_by_team($payload, $slots);
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

        foreach ($slots as $slot) {
            $key = $slot['key'];
            if (!isset($scores[$key])) {
                continue;
            }
            $teams[$key]['played']++;
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

    // Difficulty of schedule (§3.3.2/§3.4.2): sum, over every game a team
    // played, of that game's opponent's final net W-L record (wins minus
    // losses). Requires final W-L for every team, which the pass above just
    // finished computing, hence the separate second pass here.
    foreach ($teams as $key => $team) {
        $sos = 0;
        foreach (($opponents_played[$key] ?? array()) as $opponent_key) {
            $opponent = $teams[$opponent_key] ?? null;
            if ($opponent) {
                $sos += ((int) $opponent['wins'] - (int) $opponent['losses']);
            }
        }
        $teams[$key]['sos'] = $sos;
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
 * Resolve one still-tied group of teams (equal wins/losses) through the
 * remaining 2026 tie-break cascade (Issue #329): head-to-head, then
 * difficulty-of-schedule, then point differential, then coin toss. Each step
 * may only partially resolve a group — e.g. head-to-head might cleanly
 * separate 2 of 4 tied teams while leaving the other 2 still tied — so the
 * remainder recurses through the remaining, narrower criteria exactly the
 * way vaysf_resolve_pool_head_to_head_group() already does for the
 * single-criterion per-pool case.
 *
 * @param array<int,array<string,mixed>> $group Team rows, already tied on wins/losses
 * @param array<string,string> $head_to_head pair_key => winner key or 'tie'
 * @param array<string,int> $vb_match_point_diff pair_key => single-match point diff (Volleyball only)
 * @param array<string,string> $coin_toss_decisions pair_key => winner key, from recorded flips
 * @param bool $is_volleyball
 * @param string $diff_field 'capped_diff' (Basketball) or 'diff' (Volleyball)
 * @return array{ordered:array<int,array<string,mixed>>,unresolved_groups:array<int,array<int,string>>}
 */
function vaysf_results_desk_resolve_seeding_group($group, $head_to_head, $vb_match_point_diff, $coin_toss_decisions, $is_volleyball, $diff_field) {
    if (count($group) <= 1) {
        return array('ordered' => $group, 'unresolved_groups' => array());
    }

    // Step 1: head-to-head, with Volleyball's §3.4.1.1 split-match point-diff
    // sub-rule folded in — a recorded 'tie' entry for a genuine split match
    // is upgraded to a real winner here before group resolution runs, so a
    // 1-1 split still counts as "decided" for this step rather than falling
    // straight through to difficulty-of-schedule.
    $effective_head_to_head = $head_to_head;
    if ($is_volleyball) {
        foreach ($vb_match_point_diff as $pair_key => $point_diff) {
            if (($effective_head_to_head[$pair_key] ?? null) === 'tie' && $point_diff !== 0) {
                $pair = explode('|', $pair_key);
                $effective_head_to_head[$pair_key] = $point_diff > 0 ? $pair[0] : $pair[1];
            }
        }
    }
    $group_keys = array_map(function ($t) {
        return $t['team_key'];
    }, $group);
    $by_key = array_combine($group_keys, $group);

    $h2h_order = vaysf_resolve_pool_head_to_head_group($group_keys, $effective_head_to_head);
    if ($h2h_order !== null) {
        $ordered = array();
        foreach ($h2h_order as $key) {
            $ordered[] = $by_key[$key];
        }
        return array('ordered' => $ordered, 'unresolved_groups' => array());
    }

    // Step 2: difficulty of schedule — numeric, so re-sort and re-group
    // rather than a pairwise decision map.
    return vaysf_results_desk_resolve_seeding_group_numeric(
        $group,
        'sos',
        $head_to_head,
        $vb_match_point_diff,
        $coin_toss_decisions,
        $is_volleyball,
        $diff_field,
        'point_diff'
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
 * then head-to-head, then difficulty-of-schedule, then point differential
 * (Basketball capped at 40/game, Volleyball uncapped), then coin toss.
 *
 * @param string $event Schedule event name
 * @param int $schedule_version Published schedule version
 * @return array<string,mixed> {sport_type, complete, pools_complete, rankings, fully_resolved, unresolved_groups}
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
        $result = vaysf_results_desk_resolve_seeding_group($group, $head_to_head, $vb_match_point_diff, $coin_toss_decisions, $is_volleyball, $diff_field);
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

    return array(
        'sport_type' => $sport_type,
        'complete' => $complete,
        'pools_complete' => $pools_complete,
        'rankings' => $ordered,
        'fully_resolved' => empty($unresolved_groups),
        'unresolved_groups' => $unresolved_groups,
    );
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
 * Thin wrapper over vaysf_get_results_desk_pool_progress_rows() — reuses
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
 * Check whether a pool's confirmed advancement is stale — i.e. at least one
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
            // The contributing result row is gone entirely — treat as stale.
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
            // (e.g. "P1") — it has no concept of the cross-pool "ALL"
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
 * Deliberately does NOT auto-populate Semifinal/Final schedule rows — which
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

/**
 * Confirm the cross-pool QF seeding for one Basketball/Volleyball event
 * (Issue #329), replacing the need to individually confirm each of that
 * event's pools. Requires every pool for the event to be fully reported and
 * every tie fully resolved (through coin toss where a deterministic
 * tie-break could not decide it) before it will write anything. Stored in
 * `sf_pool_advancement` under the sentinel pool_id "ALL" (see
 * vaysf_results_desk_event_seeding_pool_id()) so it reuses that table's
 * existing read/staleness machinery unchanged.
 *
 * @param int $user_id WordPress user id confirming
 * @param string $event Schedule event name
 * @param int|null $schedule_version Defaults to the current published version
 * @return array<int,array<string,mixed>>|WP_Error Seeding snapshot on success
 */
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
    if (empty($seeding['fully_resolved'])) {
        $pending = array();
        foreach ($seeding['unresolved_groups'] as $group) {
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
            'call' => $call,
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
 * Render a tiny help marker using the browser's native hover tooltip.
 *
 * @param string $label Visible marker text
 * @param string $tooltip Tooltip text
 * @return void
 */
function vaysf_render_results_desk_tooltip($label, $tooltip) {
    ?>
    <span class="vaysf-results-desk-help" title="<?php echo esc_attr($tooltip); ?>"><?php echo esc_html($label); ?></span>
    <?php
}

/**
 * Convert an internal pool-review flag key to compact display text.
 *
 * @param string $flag_key Internal flag key
 * @return string Human-readable label
 */
function vaysf_results_desk_pool_flag_label($flag_key) {
    switch (sanitize_key($flag_key)) {
        case 'missing_results':
            return __('Missing results', 'vaysf');
        case 'invalid_payload':
            return __('Invalid score', 'vaysf');
        case 'unsupported_payload':
            return __('Unsupported score', 'vaysf');
        case 'split_match':
            return __('Split match', 'vaysf');
        case 'tie':
            return __('Tie', 'vaysf');
        case 'unresolved_tiebreak':
            return __('Needs tiebreak', 'vaysf');
        case 'incomplete':
            return __('Incomplete', 'vaysf');
        default:
            return ucwords(str_replace('_', ' ', sanitize_key($flag_key)));
    }
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

/**
 * Render compact labels for a preview row.
 *
 * @param array<int,array<string,mixed>> $suggestions Team/placeholder labels
 * @return void
 */
function vaysf_render_results_desk_playoff_suggestions($suggestions) {
    if (!$suggestions) {
        echo '<span class="vaysf-results-desk-muted">' . esc_html__('Pending rules / TBD', 'vaysf') . '</span>';
        return;
    }
    ?>
    <ol class="vaysf-playoff-preview-list">
        <?php foreach ($suggestions as $suggestion) : ?>
            <li>
                <?php if (!empty($suggestion['seed'])) : ?>
                    <span class="vaysf-results-desk-muted"><?php echo esc_html(sprintf(__('Seed %d', 'vaysf'), (int) $suggestion['seed'])); ?></span>
                <?php endif; ?>
                <strong><?php echo esc_html($suggestion['label'] ?? __('TBD', 'vaysf')); ?></strong>
            </li>
        <?php endforeach; ?>
    </ol>
    <?php
}

/**
 * Render existing schedule-row status for one playoff preview row.
 *
 * @param array<string,mixed>|null $row Schedule row
 * @return void
 */
function vaysf_render_results_desk_playoff_schedule_status($row) {
    if (!$row) {
        echo '<span class="vaysf-results-desk-warning" title="' . esc_attr__('This schedule row does not exist for the current schedule version.', 'vaysf') . '">' . esc_html__('Missing row', 'vaysf') . '</span>';
        return;
    }

    $status = (string) ($row['game_status'] ?? 'scheduled');
    $protected = in_array($status, array('reported', 'official', 'under_review'), true)
        || trim((string) ($row['score_json'] ?? '')) !== '';
    $class = $protected ? 'vaysf-results-desk-warning' : 'vaysf-results-desk-pill';
    $tooltip = $protected
        ? __('This row already has a protected/reported result; do not overwrite silently.', 'vaysf')
        : __('This row exists and has no submitted score payload.', 'vaysf');
    ?>
    <span class="<?php echo esc_attr($class); ?>" title="<?php echo esc_attr($tooltip); ?>"><?php echo esc_html($status); ?></span>
    <br><small><?php echo esc_html(sprintf(__('ID %d', 'vaysf'), absint($row['schedule_id'] ?? 0))); ?></small>
    <?php if (!empty($row['schedule_id'])) : ?>
        <br><a class="button button-small" href="<?php echo esc_url(admin_url('admin.php?page=vaysf-schedules&action=edit&id=' . absint($row['schedule_id']))); ?>"><?php esc_html_e('Edit row', 'vaysf'); ?></a>
    <?php endif; ?>
    <?php
}

/**
 * Render confirmed review chips for an event-level preview.
 *
 * @param array<int,array<string,mixed>> $reviews Confirmed reviews
 * @return void
 */
function vaysf_render_results_desk_playoff_reviews($reviews) {
    if (!$reviews) {
        echo '<p class="vaysf-results-desk-muted">' . esc_html__('No confirmed pool reviews yet.', 'vaysf') . '</p>';
        return;
    }
    ?>
    <div class="vaysf-playoff-preview-reviews">
        <?php foreach ($reviews as $review) : ?>
            <?php $confirmer = get_userdata((int) ($review['confirmed_by_user_id'] ?? 0)); ?>
            <span class="<?php echo esc_attr(!empty($review['stale']) ? 'vaysf-results-desk-warning' : 'vaysf-results-desk-pill'); ?>" title="<?php echo esc_attr(vaysf_format_results_desk_datetime($review['confirmed_at'] ?? '')); ?>">
                <?php
                echo esc_html(sprintf(
                    /* translators: 1: pool id, 2: user display name */
                    __('%1$s by %2$s', 'vaysf'),
                    (string) ($review['pool_id'] ?? ''),
                    $confirmer ? $confirmer->display_name : __('a Sports Fest admin', 'vaysf')
                ));
                ?>
            </span>
            <?php if (!empty($review['review_note'])) : ?>
                <span class="vaysf-results-desk-warning" title="<?php echo esc_attr($review['review_note']); ?>"><?php esc_html_e('note', 'vaysf'); ?></span>
            <?php endif; ?>
        <?php endforeach; ?>
    </div>
    <?php
}

/**
 * Render the event-level playoff/QF preview panel.
 *
 * @param array<string,mixed> $preview Preview model
 * @param array<string,mixed> $filters Current Results Desk filters
 * @param string $return_url Current page URL, used to build the Apply return link
 * @return void
 */
function vaysf_render_results_desk_playoff_preview($preview, $filters = array(), $return_url = '') {
    ?>
    <section class="vaysf-results-desk-section">
        <h2>
            <?php esc_html_e('Playoff / QF Preview', 'vaysf'); ?>
            <?php vaysf_render_results_desk_tooltip('?', __('Preview from confirmed pool reviews and current schedule rows. On its own it does not create, update, or delete schedule rows. For Bible Challenge, an explicit Apply action lets an operator write a chosen semifinal matchup directly into the schedule.', 'vaysf')); ?>
        </h2>
        <?php if (($preview['status'] ?? '') === 'select_event') : ?>
            <div class="vaysf-results-desk-notice">
                <p><?php esc_html_e('Select one event above to preview its QF/Semifinal schedule rows and confirmed pool-review inputs.', 'vaysf'); ?></p>
            </div>
            <?php return; ?>
        <?php endif; ?>
        <?php if (($preview['status'] ?? '') === 'unsupported') : ?>
            <div class="vaysf-results-desk-notice">
                <p><?php esc_html_e('This event does not have a playoff preview rule yet.', 'vaysf'); ?></p>
            </div>
            <?php return; ?>
        <?php endif; ?>
        <?php if (($preview['status'] ?? '') !== 'ok') : ?>
            <div class="vaysf-results-desk-notice vaysf-results-desk-error">
                <p><?php esc_html_e('No published schedule is available for playoff preview.', 'vaysf'); ?></p>
            </div>
            <?php return; ?>
        <?php endif; ?>

        <p>
            <?php
            echo esc_html(sprintf(
                /* translators: 1: event name, 2: schedule version */
                __('Previewing %1$s using schedule version %2$d. Nothing is applied from this panel.', 'vaysf'),
                (string) ($preview['event'] ?? ''),
                absint($preview['schedule_version'] ?? 0)
            ));
            ?>
        </p>
        <?php if (!empty($preview['warnings']) && is_array($preview['warnings'])) : ?>
            <div class="vaysf-results-desk-notice">
                <?php foreach ($preview['warnings'] as $warning) : ?>
                    <p><?php echo esc_html($warning); ?></p>
                <?php endforeach; ?>
            </div>
        <?php endif; ?>
        <?php vaysf_render_results_desk_playoff_reviews($preview['reviews'] ?? array()); ?>

        <?php if (($preview['mode'] ?? '') === 'team_qf') : ?>
            <?php vaysf_render_results_desk_event_qf_seeding_panel((string) ($preview['event'] ?? ''), absint($preview['schedule_version'] ?? 0), $return_url); ?>
        <?php endif; ?>

        <?php if (($preview['mode'] ?? '') === 'bible_challenge') : ?>
            <?php vaysf_render_results_desk_bible_challenge_reorder_form($preview, $filters); ?>
        <?php elseif (($preview['mode'] ?? '') === 'team_qf') : ?>
            <?php vaysf_render_results_desk_team_qf_reorder_form($preview, $filters); ?>
        <?php endif; ?>

        <?php if (empty($preview['rows'])) : ?>
            <div class="vaysf-results-desk-ok"><?php esc_html_e('No playoff schedule rows exist yet for this event.', 'vaysf'); ?></div>
        <?php else : ?>
            <table class="vaysf-results-desk-table vaysf-playoff-preview-table">
                <thead>
                    <tr>
                        <th><?php esc_html_e('Expected Row', 'vaysf'); ?></th>
                        <th><?php esc_html_e('Current Schedule', 'vaysf'); ?></th>
                        <th><?php esc_html_e('Preview Labels', 'vaysf'); ?></th>
                        <th><?php esc_html_e('Operator Note', 'vaysf'); ?></th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($preview['rows'] as $row) : ?>
                        <tr>
                            <td><strong><?php echo esc_html($row['game_key'] ?? ''); ?></strong><br><small><?php echo esc_html($row['stage'] ?? ''); ?></small></td>
                            <td><?php vaysf_render_results_desk_playoff_schedule_status($row['schedule_row'] ?? null); ?></td>
                            <td><?php vaysf_render_results_desk_playoff_suggestions($row['suggestion'] ?? array()); ?></td>
                            <td><?php echo esc_html($row['note'] ?? ''); ?></td>
                        </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
        <?php endif; ?>

        <?php if (($preview['mode'] ?? '') === 'bible_challenge' && !empty($preview['can_customize'])) : ?>
            <?php vaysf_render_results_desk_bible_challenge_apply_form($preview, $return_url); ?>
        <?php elseif (($preview['mode'] ?? '') === 'team_qf' && !empty($preview['can_customize'])) : ?>
            <?php vaysf_render_results_desk_team_qf_apply_form($preview, $return_url); ?>
        <?php endif; ?>
    </section>
    <?php
}

/**
 * Render the cross-pool QF-seeding review/confirm panel for one BB/VB event
 * (Issue #329): the live-computed ranking (recomputed fresh on every page
 * load, not just at confirm time, so the coordinator always sees current
 * standings), any confirmed/stale status, coin-toss prompts for any group
 * still tied after every deterministic tie-break, and the "Confirm All
 * Pools for QF Seeding" action itself — gated on every pool being complete
 * and every tie resolved. Replaces the need to individually confirm each of
 * this event's pools (per-pool "Confirm Pool Review" is suppressed for
 * BB/VB events in vaysf_render_results_desk_pool_progress_row()).
 *
 * @param string $event Schedule event name
 * @param int $schedule_version Published schedule version
 * @param string $return_url Current page URL to redirect back to
 * @return void
 */
function vaysf_render_results_desk_event_qf_seeding_panel($event, $schedule_version, $return_url) {
    $sport_type = vaysf_results_desk_seeding_sport_type($event);
    if ($sport_type === null) {
        return;
    }

    $seeding = vaysf_results_desk_get_event_seeding_rankings($event, $schedule_version);
    $pool_id = vaysf_results_desk_event_seeding_pool_id();
    $existing = vaysf_get_pool_advancement($event, $pool_id, $schedule_version);
    $is_stale = $existing ? vaysf_pool_advancement_is_stale($event, $pool_id, $schedule_version, $seeding['rankings']) : false;
    $diff_field = $sport_type === 'basketball' ? 'capped_diff' : 'diff';
    ?>
    <div class="vaysf-qf-seeding-panel">
        <h3>
            <?php esc_html_e('Cross-Pool QF Seeding', 'vaysf'); ?>
            <?php vaysf_render_results_desk_tooltip('?', __('Official 2026 rule: W-L record, then head-to-head, then difficulty of schedule, then point differential, then coin toss. Confirming here replaces confirming each pool individually for this event.', 'vaysf')); ?>
        </h3>

        <?php if (empty($seeding['complete'])) : ?>
            <div class="vaysf-results-desk-notice">
                <p><?php esc_html_e('Every pool for this event must be fully reported before QF seeding can be confirmed.', 'vaysf'); ?></p>
            </div>
        <?php endif; ?>

        <?php if ($existing) : ?>
            <?php $confirmer = get_userdata((int) $existing['confirmed_by_user_id']); ?>
            <p>
                <span class="<?php echo esc_attr($is_stale ? 'vaysf-results-desk-warning' : 'vaysf-results-desk-pill'); ?>" title="<?php echo esc_attr(vaysf_format_results_desk_datetime($existing['confirmed_at'] ?? '')); ?>">
                    <?php
                    if ($is_stale) {
                        esc_html_e('Needs re-confirm', 'vaysf');
                    } else {
                        printf(
                            /* translators: %s: user display name */
                            esc_html__('Confirmed by %s', 'vaysf'),
                            esc_html($confirmer ? $confirmer->display_name : __('a Sports Fest admin', 'vaysf'))
                        );
                    }
                    ?>
                </span>
            </p>
        <?php endif; ?>

        <?php if (!empty($seeding['rankings'])) : ?>
            <table class="vaysf-results-desk-table vaysf-qf-seeding-table">
                <thead>
                    <tr>
                        <th><?php esc_html_e('Seed', 'vaysf'); ?></th>
                        <th><?php esc_html_e('Team', 'vaysf'); ?></th>
                        <th><?php esc_html_e('W-L', 'vaysf'); ?></th>
                        <th>
                            <?php esc_html_e('SOS', 'vaysf'); ?>
                            <?php vaysf_render_results_desk_tooltip('?', __('Difficulty of schedule: sum of every opponent played\'s own final win-loss record.', 'vaysf')); ?>
                        </th>
                        <th><?php esc_html_e('Point Diff', 'vaysf'); ?></th>
                        <th><?php esc_html_e('Status', 'vaysf'); ?></th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($seeding['rankings'] as $team) : ?>
                        <tr>
                            <td><?php echo empty($team['needs_coin_toss']) ? esc_html((string) $team['rank']) : '—'; ?></td>
                            <td><?php echo esc_html((string) ($team['label'] ?? $team['team_key'])); ?></td>
                            <td><?php echo esc_html(((int) ($team['wins'] ?? 0)) . '-' . ((int) ($team['losses'] ?? 0))); ?></td>
                            <td><?php echo esc_html((string) ($team['sos'] ?? 0)); ?></td>
                            <td><?php echo esc_html((string) ($team[$diff_field] ?? 0)); ?></td>
                            <td>
                                <?php if (!empty($team['needs_coin_toss'])) : ?>
                                    <span class="vaysf-results-desk-warning"><?php esc_html_e('Tied — needs coin toss', 'vaysf'); ?></span>
                                <?php elseif (!empty($team['advances'])) : ?>
                                    <span class="vaysf-results-desk-pill"><?php esc_html_e('Advances', 'vaysf'); ?></span>
                                <?php endif; ?>
                            </td>
                        </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
        <?php endif; ?>

        <?php foreach ($seeding['unresolved_groups'] as $group_keys) : ?>
            <?php vaysf_render_results_desk_coin_toss_form($event, $schedule_version, $group_keys, $seeding['rankings'], $return_url); ?>
        <?php endforeach; ?>

        <?php if (!empty($seeding['complete']) && !empty($seeding['fully_resolved']) && !empty($seeding['rankings'])) : ?>
            <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                <input type="hidden" name="action" value="vaysf_confirm_event_qf_seeding">
                <input type="hidden" name="event" value="<?php echo esc_attr($event); ?>">
                <input type="hidden" name="schedule_version" value="<?php echo esc_attr($schedule_version); ?>">
                <input type="hidden" name="return_url" value="<?php echo esc_attr($return_url); ?>">
                <?php wp_nonce_field('vaysf_confirm_event_qf_seeding_' . $event . '_' . $schedule_version); ?>
                <button type="submit" class="button button-primary" title="<?php echo esc_attr__('Record this cross-pool seeding as reviewed for QF assignment below. This does not create schedule rows by itself.', 'vaysf'); ?>">
                    <?php echo esc_html($existing ? __('Re-confirm All Pools for QF Seeding', 'vaysf') : __('Confirm All Pools for QF Seeding', 'vaysf')); ?>
                </button>
            </form>
        <?php endif; ?>
    </div>
    <?php
}

/**
 * Render one coin-toss flip form per still-undecided pair within an
 * unresolved tied group (Issue #329). A group larger than 2 (rare — every
 * deterministic criterion including difficulty-of-schedule and point
 * differential would all have to tie) gets one form per pair; the
 * coordinator flips as many as needed, and the ranking recomputes after
 * each submit.
 *
 * @param string $event
 * @param int $schedule_version
 * @param array<int,string> $group_keys Team keys still tied together
 * @param array<int,array<string,mixed>> $rankings Full ranking rows, for labels
 * @param string $return_url
 * @return void
 */
function vaysf_render_results_desk_coin_toss_form($event, $schedule_version, $group_keys, $rankings, $return_url) {
    $by_key = array();
    foreach ($rankings as $team) {
        $by_key[$team['team_key']] = $team;
    }

    for ($i = 0; $i < count($group_keys); $i++) {
        for ($j = $i + 1; $j < count($group_keys); $j++) {
            $key_a = $group_keys[$i];
            $key_b = $group_keys[$j];
            $label_a = (string) ($by_key[$key_a]['label'] ?? $key_a);
            $label_b = (string) ($by_key[$key_b]['label'] ?? $key_b);
            ?>
            <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>" class="vaysf-coin-toss-form">
                <input type="hidden" name="action" value="vaysf_flip_coin_toss">
                <input type="hidden" name="event" value="<?php echo esc_attr($event); ?>">
                <input type="hidden" name="schedule_version" value="<?php echo esc_attr($schedule_version); ?>">
                <input type="hidden" name="team_a_key" value="<?php echo esc_attr($key_a); ?>">
                <input type="hidden" name="team_a_label" value="<?php echo esc_attr($label_a); ?>">
                <input type="hidden" name="team_b_key" value="<?php echo esc_attr($key_b); ?>">
                <input type="hidden" name="team_b_label" value="<?php echo esc_attr($label_b); ?>">
                <input type="hidden" name="return_url" value="<?php echo esc_attr($return_url); ?>">
                <?php wp_nonce_field('vaysf_flip_coin_toss_' . $event . '_' . $schedule_version . '_' . $key_a . '_' . $key_b); ?>
                <p class="vaysf-results-desk-warning">
                    <?php echo esc_html(sprintf(
                        /* translators: 1: first tied team, 2: second tied team */
                        __('%1$s vs %2$s tied after every deterministic tie-break.', 'vaysf'),
                        $label_a,
                        $label_b
                    )); ?>
                </p>
                <label>
                    <?php esc_html_e('Calling team', 'vaysf'); ?>
                    <select name="call_by_key">
                        <option value="<?php echo esc_attr($key_a); ?>"><?php echo esc_html($label_a); ?></option>
                        <option value="<?php echo esc_attr($key_b); ?>"><?php echo esc_html($label_b); ?></option>
                    </select>
                </label>
                <label>
                    <?php esc_html_e('Call', 'vaysf'); ?>
                    <select name="call">
                        <option value="heads"><?php esc_html_e('Heads', 'vaysf'); ?></option>
                        <option value="tails"><?php esc_html_e('Tails', 'vaysf'); ?></option>
                    </select>
                </label>
                <button type="submit" class="button" title="<?php echo esc_attr__('The server generates the flip result for fairness — the call is human, the flip is not.', 'vaysf'); ?>">
                    <?php esc_html_e('Flip coin', 'vaysf'); ?>
                </button>
            </form>
            <?php
        }
    }
}

/**
 * Render the dropdown-based semifinal reassignment form for the Bible
 * Challenge preview. Session-only: selections travel as GET params
 * (`bc_seed[<game_key>][]`) and are never persisted, per operator request —
 * reloading without those params returns to the top-seed-protection default.
 *
 * @param array<string,mixed> $preview Preview model from
 *        vaysf_results_desk_build_bible_challenge_preview()
 * @param array<string,mixed> $filters Current Results Desk filters
 * @return void
 */
function vaysf_render_results_desk_bible_challenge_reorder_form($preview, $filters) {
    if (empty($preview['can_customize'])) {
        return;
    }

    $teams_by_key = $preview['teams_by_key'] ?? array();
    $arrangement = $preview['arrangement'] ?? array();
    ?>
    <form method="get" class="vaysf-bc-reorder-form">
        <input type="hidden" name="event" value="<?php echo esc_attr($filters['event'] ?? ''); ?>">
        <?php if (!empty($filters['church'])) : ?>
            <input type="hidden" name="church" value="<?php echo esc_attr($filters['church']); ?>">
        <?php endif; ?>
        <p class="vaysf-results-desk-muted">
            <?php esc_html_e('Reassign which confirmed Top-9 team plays in each semifinal, then click Update preview. This only changes what you see in this browser.', 'vaysf'); ?>
        </p>
        <div class="vaysf-bc-reorder-grid">
            <?php foreach ($arrangement as $game_key => $team_keys) : ?>
                <fieldset>
                    <legend><?php echo esc_html($game_key); ?></legend>
                    <?php foreach ($team_keys as $selected_key) : ?>
                        <select name="bc_seed[<?php echo esc_attr($game_key); ?>][]">
                            <?php foreach ($teams_by_key as $team_key => $team) : ?>
                                <option value="<?php echo esc_attr($team_key); ?>" <?php selected($selected_key, $team_key); ?>>
                                    <?php echo esc_html(sprintf(__('#%1$d %2$s', 'vaysf'), (int) $team['seed'], $team['label'])); ?>
                                </option>
                            <?php endforeach; ?>
                        </select>
                    <?php endforeach; ?>
                </fieldset>
            <?php endforeach; ?>
        </div>
        <button type="submit" class="button"><?php esc_html_e('Update preview', 'vaysf'); ?></button>
        <?php if (!empty($preview['custom_active'])) : ?>
            <a class="button" href="<?php echo esc_url(remove_query_arg('bc_seed')); ?>"><?php esc_html_e('Reset to top-seed protection', 'vaysf'); ?></a>
        <?php endif; ?>
    </form>
    <?php
}

/**
 * Render the Apply action for the Bible Challenge semifinal preview. This is
 * the one control on this panel that writes to the database: it submits the
 * arrangement currently shown (top-seed-protection default or the operator's custom
 * pick) to vaysf_handle_apply_bible_challenge_preview_request(), which writes
 * team_a/b/c directly into the BC-Semi-1/2/3 schedule rows, creating them if
 * missing. This deliberately bypasses the normal publish-schedule pipeline
 * (docs/SCHEDULING.md) at the operator's explicit request, so a later
 * schedule publish could still overwrite these rows if it targets the same
 * game_keys — Applying does not mark them protected.
 *
 * @param array<string,mixed> $preview Preview model
 * @param string $return_url Current page URL to redirect back to
 * @return void
 */
function vaysf_render_results_desk_bible_challenge_apply_form($preview, $return_url) {
    $event = (string) ($preview['event'] ?? '');
    $schedule_version = absint($preview['schedule_version'] ?? 0);
    ?>
    <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>" class="vaysf-bc-apply-form">
        <input type="hidden" name="action" value="vaysf_apply_bible_challenge_preview">
        <input type="hidden" name="event" value="<?php echo esc_attr($event); ?>">
        <input type="hidden" name="schedule_version" value="<?php echo esc_attr($schedule_version); ?>">
        <input type="hidden" name="return_url" value="<?php echo esc_attr($return_url); ?>">
        <?php foreach ($preview['arrangement'] ?? array() as $game_key => $team_keys) : ?>
            <?php foreach ($team_keys as $team_key) : ?>
                <input type="hidden" name="bc_seed[<?php echo esc_attr($game_key); ?>][]" value="<?php echo esc_attr($team_key); ?>">
            <?php endforeach; ?>
        <?php endforeach; ?>
        <?php wp_nonce_field('vaysf_apply_bible_challenge_preview_' . $event . '_' . $schedule_version); ?>
        <button
            type="submit"
            class="button button-primary"
            onclick="return confirm('<?php echo esc_js(__('Write this exact matchup into BC-Semi-1, BC-Semi-2, and BC-Semi-3, then prewire BC-Final with semifinal winner placeholders? This writes directly to the schedule, bypassing the normal publish-schedule pipeline, and rows already reported/official are skipped rather than overwritten.', 'vaysf')); ?>');"
        >
            <?php esc_html_e('Apply matchup to schedule', 'vaysf'); ?>
        </button>
        <p class="vaysf-results-desk-muted"><?php esc_html_e('Writes the teams shown above directly into the BC-Semi-1/2/3 schedule rows (creating them if missing), then prewires BC-Final with semifinal winner placeholders. Rows already reported, official, under review, or already scored are skipped, never overwritten. Court and time are left untouched.', 'vaysf'); ?></p>
    </form>
    <?php
}

/**
 * Render the QF reassignment form for Basketball/Volleyball.
 *
 * @param array<string,mixed> $preview Preview model
 * @param array<string,mixed> $filters Current Results Desk filters
 * @return void
 */
function vaysf_render_results_desk_team_qf_reorder_form($preview, $filters) {
    if (empty($preview['can_customize'])) {
        return;
    }

    $teams_by_key = $preview['teams_by_key'] ?? array();
    $arrangement = $preview['arrangement'] ?? array();
    ?>
    <form method="get" class="vaysf-playoff-assignment-form">
        <input type="hidden" name="event" value="<?php echo esc_attr($filters['event'] ?? ''); ?>">
        <?php if (!empty($filters['church'])) : ?>
            <input type="hidden" name="church" value="<?php echo esc_attr($filters['church']); ?>">
        <?php endif; ?>
        <p class="vaysf-results-desk-muted">
            <?php esc_html_e('Assign confirmed pool-review teams into QF matchups, then click Update preview. This only changes what you see in this browser until Apply is clicked.', 'vaysf'); ?>
        </p>
        <div class="vaysf-playoff-assignment-grid">
            <?php foreach ($arrangement as $game_key => $team_keys) : ?>
                <fieldset>
                    <legend><?php echo esc_html($game_key); ?></legend>
                    <?php foreach ($team_keys as $slot_index => $selected_key) : ?>
                        <label>
                            <span class="vaysf-results-desk-muted"><?php echo esc_html($slot_index === 0 ? __('Slot A', 'vaysf') : __('Slot B', 'vaysf')); ?></span>
                            <select name="qf_seed[<?php echo esc_attr($game_key); ?>][]">
                                <?php foreach ($teams_by_key as $team_key => $team) : ?>
                                    <option value="<?php echo esc_attr($team_key); ?>" <?php selected($selected_key, $team_key); ?>>
                                        <?php echo esc_html(vaysf_results_desk_team_qf_option_label($team)); ?>
                                    </option>
                                <?php endforeach; ?>
                            </select>
                        </label>
                    <?php endforeach; ?>
                </fieldset>
            <?php endforeach; ?>
        </div>
        <button type="submit" class="button"><?php esc_html_e('Update preview', 'vaysf'); ?></button>
        <?php if (!empty($preview['custom_active'])) : ?>
            <a class="button" href="<?php echo esc_url(remove_query_arg('qf_seed')); ?>"><?php esc_html_e('Reset to default QF order', 'vaysf'); ?></a>
        <?php endif; ?>
    </form>
    <?php
}

/**
 * Render the Apply action for the Basketball/Volleyball QF preview.
 *
 * @param array<string,mixed> $preview Preview model
 * @param string $return_url Current page URL to redirect back to
 * @return void
 */
function vaysf_render_results_desk_team_qf_apply_form($preview, $return_url) {
    $event = (string) ($preview['event'] ?? '');
    $schedule_version = absint($preview['schedule_version'] ?? 0);
    ?>
    <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>" class="vaysf-playoff-apply-form">
        <input type="hidden" name="action" value="vaysf_apply_team_qf_preview">
        <input type="hidden" name="event" value="<?php echo esc_attr($event); ?>">
        <input type="hidden" name="schedule_version" value="<?php echo esc_attr($schedule_version); ?>">
        <input type="hidden" name="return_url" value="<?php echo esc_attr($return_url); ?>">
        <?php foreach ($preview['arrangement'] ?? array() as $game_key => $team_keys) : ?>
            <?php foreach ($team_keys as $team_key) : ?>
                <input type="hidden" name="qf_seed[<?php echo esc_attr($game_key); ?>][]" value="<?php echo esc_attr($team_key); ?>">
            <?php endforeach; ?>
        <?php endforeach; ?>
        <?php wp_nonce_field('vaysf_apply_team_qf_preview_' . $event . '_' . $schedule_version); ?>
        <button
            type="submit"
            class="button button-primary"
            onclick="return confirm('<?php echo esc_js(__('Write this exact QF matchup into the Basketball/Volleyball QF-1..4 schedule rows (creating them if missing), then prewire Semifinal/Final/3rd-Place placeholders? Rows already reported, official, or under review are skipped rather than overwritten.', 'vaysf')); ?>');"
        >
            <?php esc_html_e('Apply QF matchup to schedule', 'vaysf'); ?>
        </button>
        <p class="vaysf-results-desk-muted"><?php esc_html_e('Writes team A/team B into the QF-1..4 schedule rows (creating them if missing), then prewires Semifinal/Final/3rd-Place rows with winner/loser placeholders. Court and time are preserved when a row already exists.', 'vaysf'); ?></p>
    </form>
    <?php
}

/**
 * Render compact provisional rankings for one pool.
 *
 * @param array<int,array<string,mixed>> $rankings Ranking rows
 * @param string $event Schedule event name
 * @return void
 */
function vaysf_render_results_desk_pool_rankings($rankings, $event = '') {
    if (!$rankings) {
        echo '<span class="vaysf-results-desk-muted">' . esc_html__('No scored games yet.', 'vaysf') . '</span>';
        return;
    }
    $rule_note = vaysf_results_desk_pool_ranking_rule_note($event);
    ?>
    <?php if ($rule_note !== '') : ?>
        <p class="vaysf-results-desk-muted" style="margin: 0 0 8px;"><?php echo esc_html($rule_note); ?></p>
    <?php endif; ?>
    <ol class="vaysf-results-desk-rankings">
        <?php foreach ($rankings as $team) : ?>
            <?php
            $is_total_score_ranking = (($team['ranking_basis'] ?? '') === 'total_score');
            if ($is_total_score_ranking) {
                $record = sprintf(
                    /* translators: %d: cumulative Bible Challenge preliminary score */
                    __('Total %d', 'vaysf'),
                    (int) ($team['for'] ?? 0)
                );
                $metric = sprintf(
                    /* translators: %d: number of preliminary rows scored for this team */
                    _n('%d prelim scored', '%d prelims scored', (int) ($team['played'] ?? 0), 'vaysf'),
                    (int) ($team['played'] ?? 0)
                );
                $record_tooltip = __('Bible Challenge ranks by cumulative preliminary score. The top 9 advance.', 'vaysf');
                $metric_tooltip = __('Number of submitted preliminary score rows included in this team total.', 'vaysf');
            } else {
                $record = sprintf(
                    '%d-%d-%d',
                    (int) ($team['wins'] ?? 0),
                    (int) ($team['losses'] ?? 0),
                    (int) ($team['ties'] ?? 0)
                );
                $metric = sprintf(
                    'PF %d / PA %d / %+d',
                    (int) ($team['for'] ?? 0),
                    (int) ($team['against'] ?? 0),
                    (int) ($team['diff'] ?? 0)
                );
                $record_tooltip = __('Record is wins-losses-ties from scored pool games.', 'vaysf');
                $metric_tooltip = __('PF/PA are points for and points against from the score payload. For volleyball this uses match score units, usually sets won/lost.', 'vaysf');
            }
            $notes = !empty($team['notes']) && is_array($team['notes']) ? implode('; ', $team['notes']) : '';
            ?>
            <li value="<?php echo esc_attr((string) ($team['rank'] ?? 1)); ?>">
                <strong><?php echo esc_html($team['label'] ?? $team['team_key'] ?? ''); ?></strong>
                <span class="vaysf-results-desk-pill" title="<?php echo esc_attr($record_tooltip); ?>"><?php echo esc_html($record); ?></span>
                <?php if (!empty($team['advances'])) : ?>
                    <span class="vaysf-results-desk-pill" title="<?php echo esc_attr__('Top 9 by cumulative Bible Challenge preliminary score advance.', 'vaysf'); ?>"><?php esc_html_e('Advances', 'vaysf'); ?></span>
                <?php endif; ?>
                <span class="vaysf-results-desk-muted" title="<?php echo esc_attr($metric_tooltip); ?>"><?php echo esc_html($metric); ?></span>
                <?php if ($notes !== '') : ?>
                    <span class="vaysf-results-desk-warning" title="<?php echo esc_attr($notes); ?>"><?php echo esc_html__('note', 'vaysf'); ?></span>
                <?php endif; ?>
            </li>
        <?php endforeach; ?>
    </ol>
    <?php
}

/**
 * Render one pool progress row.
 *
 * @param array<string,mixed> $pool Pool progress row
 * @param string $return_url Results Desk URL to redirect back to after
 *        confirming advancement (Issue #207)
 * @return void
 */
function vaysf_render_results_desk_pool_progress_row($pool, $return_url = '') {
    if ($return_url === '') {
        $return_url = vaysf_results_desk_current_request_url();
    }

    $game_count = max(0, (int) ($pool['game_count'] ?? 0));
    $reported_count = max(0, (int) ($pool['reported_count'] ?? 0));
    $missing_count = max(0, (int) ($pool['missing_count'] ?? 0));
    $percent = $game_count > 0 ? round(($reported_count / $game_count) * 100) : 0;
    $pool_flags = !empty($pool['flags']) && is_array($pool['flags']) ? $pool['flags'] : array();
    $flag_messages = array_values($pool_flags);
    $flag_tooltip = $flag_messages ? implode(' ', $flag_messages) : __('No ranking flags for this pool.', 'vaysf');
    ?>
    <tr>
        <td>
            <strong><?php echo esc_html($pool['event'] ?? ''); ?></strong><br>
            <small><?php echo esc_html(trim(($pool['stage'] ?? '') . ' ' . ($pool['pool_id'] ?? ''))); ?></small>
        </td>
        <td>
            <div class="vaysf-results-desk-progress" title="<?php echo esc_attr__('Reported games divided by total published pool/prelim games. A complete pool is ready for human advancement review, not automatic advancement.', 'vaysf'); ?>">
                <span style="width: <?php echo esc_attr((string) $percent); ?>%;"></span>
            </div>
            <strong><?php echo esc_html(sprintf(__('%1$d / %2$d scored', 'vaysf'), $reported_count, $game_count)); ?></strong>
            <?php if ($missing_count > 0) : ?>
                <br><small><?php echo esc_html(sprintf(_n('%d missing result', '%d missing results', $missing_count, 'vaysf'), $missing_count)); ?></small>
            <?php else : ?>
                <br><small><?php echo esc_html__('complete', 'vaysf'); ?></small>
            <?php endif; ?>
        </td>
        <td>
            <?php vaysf_render_results_desk_pool_rankings($pool['rankings'] ?? array(), $pool['event'] ?? ''); ?>
        </td>
        <td>
            <span class="<?php echo esc_attr(!empty($pool['complete']) ? 'vaysf-results-desk-pill' : 'vaysf-results-desk-warning'); ?>" title="<?php echo esc_attr($flag_tooltip); ?>">
                <?php echo !empty($pool['complete']) ? esc_html__('Ready', 'vaysf') : esc_html__('In progress', 'vaysf'); ?>
            </span>
            <?php if ($pool_flags) : ?>
                <br>
                <?php foreach ($pool_flags as $flag_key => $flag_message) : ?>
                    <small class="vaysf-results-desk-warning vaysf-results-desk-flag" title="<?php echo esc_attr($flag_message); ?>">
                        <?php echo esc_html(vaysf_results_desk_pool_flag_label($flag_key)); ?>
                    </small>
                <?php endforeach; ?>
            <?php endif; ?>
        </td>
        <td><?php echo esc_html(vaysf_format_results_desk_datetime($pool['last_updated_at'] ?? '')); ?></td>
        <td>
            <?php
            $pool_event = (string) ($pool['event'] ?? '');
            $pool_id_value = (string) ($pool['pool_id'] ?? '');
            $pool_schedule_version = absint($pool['schedule_version'] ?? 0);
            $advancement = vaysf_get_pool_advancement($pool_event, $pool_id_value, $pool_schedule_version);
            $is_stale = $advancement ? vaysf_pool_advancement_is_stale($pool_event, $pool_id_value, $pool_schedule_version, $pool['rankings'] ?? array()) : false;
            ?>
            <?php if ($advancement && $is_stale) : ?>
                <span class="vaysf-results-desk-warning" title="<?php esc_attr_e('A result contributing to this pool was corrected after advancement was confirmed. Re-confirm after reviewing the standings.', 'vaysf'); ?>">
                    <?php esc_html_e('Needs re-confirm', 'vaysf'); ?>
                </span>
            <?php elseif ($advancement) : ?>
                <?php $confirmer = get_userdata((int) $advancement['confirmed_by_user_id']); ?>
                <span class="vaysf-results-desk-pill" title="<?php echo esc_attr(vaysf_format_results_desk_datetime($advancement['confirmed_at'] ?? '')); ?>">
                    <?php
                    printf(
                        /* translators: %s: user display name */
                        esc_html__('Confirmed by %s', 'vaysf'),
                        esc_html($confirmer ? $confirmer->display_name : __('a Sports Fest admin', 'vaysf'))
                    );
                    ?>
                </span>
                <?php if (!empty($advancement['review_note'])) : ?>
                    <br><small class="vaysf-results-desk-note-display" title="<?php echo esc_attr($advancement['review_note']); ?>">
                        <?php echo esc_html(sprintf(__('Note: %s', 'vaysf'), $advancement['review_note'])); ?>
                    </small>
                <?php endif; ?>
            <?php endif; ?>
            <?php if (vaysf_results_desk_seeding_sport_type($pool_event) !== null) : ?>
                <?php if (!empty($pool['complete'])) : ?>
                    <p class="vaysf-results-desk-muted"><?php esc_html_e('Confirmed together with the event\'s other pools via "Confirm All Pools for QF Seeding" below.', 'vaysf'); ?></p>
                <?php endif; ?>
            <?php elseif (!empty($pool['complete'])) : ?>
                <?php
                $has_unresolved_tie = !empty($pool['needs_manual_tiebreak']);
                $existing_review_note = is_array($advancement) && isset($advancement['review_note'])
                    ? (string) $advancement['review_note']
                    : '';
                $is_bible_challenge_pool = vaysf_results_desk_is_bible_challenge_event($pool_event);
                if ($is_bible_challenge_pool) {
                    $confirm_label = $advancement ? __('Re-confirm Top 9', 'vaysf') : __('Confirm Top 9', 'vaysf');
                    if ($has_unresolved_tie) {
                        $confirm_tooltip = $advancement
                            ? __('Update the saved Bible Challenge review note while the cutoff tie remains available for the next-page finalization step. This does not change scores or automatically populate semifinal/final games.', 'vaysf')
                            : __('Save the current Bible Challenge rankings and cutoff-tie note as reviewed for the next-page finalization step. This does not change scores or automatically populate semifinal/final games.', 'vaysf');
                    } else {
                        $confirm_tooltip = $advancement
                            ? __('Update the saved Bible Challenge advancement confirmation using the current top 9 teams by cumulative preliminary score. This does not change scores or automatically populate semifinal/final games.', 'vaysf')
                            : __('Save the current Bible Challenge top 9 teams by cumulative preliminary score as reviewed for advancement. This does not change scores or automatically populate semifinal/final games.', 'vaysf');
                    }
                } else {
                    $confirm_label = $advancement ? __('Re-confirm Pool Review', 'vaysf') : __('Confirm Pool Review', 'vaysf');
                    if ($has_unresolved_tie) {
                        $confirm_tooltip = $advancement
                            ? __('Update this pool review note and keep the unresolved tie available for the next-page QF/playoff finalization step. This does not choose wildcards, assign seeds, submit QF matchups, change scores, or populate schedule rows.', 'vaysf')
                            : __('Record this pool ranking and tie note as reviewed for the next-page QF/playoff finalization step. This does not choose wildcards, assign seeds, submit QF matchups, change scores, or populate schedule rows.', 'vaysf');
                    } else {
                        $confirm_tooltip = $advancement
                            ? __('Update this pool ranking as reviewed for event-level QF/playoff finalization. This does not choose wildcards, assign seeds, submit QF matchups, change scores, or populate schedule rows.', 'vaysf')
                            : __('Record this pool ranking as reviewed for event-level QF/playoff finalization. This does not choose wildcards, assign seeds, submit QF matchups, change scores, or populate schedule rows.', 'vaysf');
                    }
                }
                ?>
                <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                    <input type="hidden" name="action" value="vaysf_confirm_pool_advancement">
                    <input type="hidden" name="event" value="<?php echo esc_attr($pool_event); ?>">
                    <input type="hidden" name="pool_id" value="<?php echo esc_attr($pool_id_value); ?>">
                    <input type="hidden" name="return_url" value="<?php echo esc_attr($return_url); ?>">
                    <?php wp_nonce_field('vaysf_confirm_pool_advancement_' . $pool_event . '_' . $pool_id_value); ?>
                    <?php if ($has_unresolved_tie) : ?>
                        <label class="vaysf-pool-review-note-label">
                            <?php esc_html_e('Tie review note', 'vaysf'); ?>
                            <textarea class="vaysf-pool-review-note" name="review_note" rows="2" required placeholder="<?php echo esc_attr__('Example: FVC/NSD/RPC tied; resolve manually on QF page.', 'vaysf'); ?>"><?php echo esc_textarea($existing_review_note); ?></textarea>
                        </label>
                    <?php endif; ?>
                    <button type="submit" class="button button-primary button-small" title="<?php echo esc_attr($confirm_tooltip); ?>" aria-label="<?php echo esc_attr($confirm_tooltip); ?>">
                        <?php echo esc_html($confirm_label); ?>
                    </button>
                </form>
            <?php endif; ?>
        </td>
    </tr>
    <?php
}

/**
 * Render one schedule/result row in a Results Desk table.
 *
 * @param array<string,mixed> $row Row data
 * @param string $mode Display mode
 * @return void
 */
function vaysf_render_results_desk_game_row($row, $mode = 'default') {
    $teams = vaysf_format_schedule_teams($row);
    if ($teams === '') {
        $teams = __('Teams TBD', 'vaysf');
    }
    $scheduled = vaysf_format_schedule_display_time($row['scheduled_time'] ?? '', $row['scheduled_slot'] ?? '', 'D M j, g:i A');
    $result_url = !empty($row['result_id'])
        ? admin_url('admin.php?page=vaysf-results&action=edit&id=' . absint($row['result_id']))
        : admin_url('admin.php?page=vaysf-results&action=new');
    ?>
    <tr>
        <td><strong><?php echo esc_html($row['game_key'] ?? ''); ?></strong><br><small><?php echo esc_html($row['event'] ?? ''); ?></small></td>
        <td><?php echo esc_html($teams); ?></td>
        <td><?php echo esc_html($scheduled); ?><br><small><?php echo esc_html($row['scheduled_location'] ?? $row['resource_id'] ?? ''); ?></small></td>
        <td>
            <?php echo esc_html($row['public_status'] ?? $row['game_status'] ?? 'scheduled'); ?>
            <?php if (!empty($row['scan_status'])) : ?>
                <br><small><?php echo esc_html__('Scan:', 'vaysf'); ?> <?php echo esc_html($row['scan_status']); ?></small>
            <?php endif; ?>
            <?php if ($mode === 'correction' && !empty($row['verification_state'])) : ?>
                <br><small><?php echo esc_html__('Revision:', 'vaysf'); ?> <?php echo esc_html($row['revision_number']); ?> / <?php echo esc_html($row['verification_state']); ?></small>
            <?php endif; ?>
        </td>
        <td>
            <a class="button button-small" href="<?php echo esc_url($result_url); ?>">
                <?php echo !empty($row['result_id']) ? esc_html__('Review', 'vaysf') : esc_html__('Create Result', 'vaysf'); ?>
            </a>
        </td>
    </tr>
    <?php
}

/**
 * Render a Results Desk section table.
 *
 * @param string $title Section title
 * @param string $description Section description
 * @param array<int,array<string,mixed>> $rows Rows
 * @param string $empty_message Empty state
 * @param string $mode Display mode
 * @return void
 */
function vaysf_render_results_desk_section($title, $description, $rows, $empty_message, $mode = 'default') {
    ?>
    <section class="vaysf-results-desk-section">
        <h2><?php echo esc_html($title); ?></h2>
        <p><?php echo esc_html($description); ?></p>
        <?php if (!$rows) : ?>
            <div class="vaysf-results-desk-ok"><?php echo esc_html($empty_message); ?></div>
        <?php else : ?>
            <table class="vaysf-results-desk-table">
                <thead>
                    <tr>
                        <th><?php esc_html_e('Game', 'vaysf'); ?></th>
                        <th><?php esc_html_e('Matchup', 'vaysf'); ?></th>
                        <th><?php esc_html_e('Time / Location', 'vaysf'); ?></th>
                        <th><?php esc_html_e('Status', 'vaysf'); ?></th>
                        <th><?php esc_html_e('Action', 'vaysf'); ?></th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($rows as $row) : ?>
                        <?php vaysf_render_results_desk_game_row($row, $mode); ?>
                    <?php endforeach; ?>
                </tbody>
            </table>
        <?php endif; ?>
    </section>
    <?php
}

/**
 * Render the Results Desk dashboard.
 *
 * @param array<string,mixed> $atts Shortcode/template attributes
 * @return string HTML
 */
function vaysf_render_results_desk($atts = array()) {
    $filters = vaysf_sanitize_results_desk_filters($atts);
    $return_url = vaysf_results_desk_current_request_url();

    ob_start();
    ?>
    <div class="vaysf-results-desk">
        <style>
            .vaysf-results-desk * { box-sizing: border-box; }
            .vaysf-results-desk { max-width: 1180px; margin: 32px auto; padding: 20px; }
            .vaysf-results-desk h1 { margin: 0 0 8px; font-size: 2rem; line-height: 1.2; }
            .vaysf-results-desk-subtitle { margin: 0 0 20px; color: #50575e; }
            .vaysf-results-desk-notice { background: #fff8e5; border-left: 4px solid #dba617; margin: 20px 0; padding: 14px 16px; }
            .vaysf-results-desk-error { background: #fde8e8; border-left-color: #cc1818; }
            .vaysf-results-desk-toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: end; margin: 20px 0; padding: 14px; background: #f6f7f7; border: 1px solid #dcdcde; }
            .vaysf-results-desk-toolbar label { display: flex; flex-direction: column; gap: 4px; font-weight: 600; }
            .vaysf-results-desk-toolbar select { min-width: 240px; }
            .vaysf-results-desk-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 20px 0; }
            .vaysf-results-desk-card { background: #fff; border: 1px solid #dcdcde; border-radius: 8px; padding: 14px; box-shadow: 0 1px 2px rgba(0,0,0,.04); }
            .vaysf-results-desk-card strong { display: block; font-size: 1.6rem; line-height: 1.2; }
            .vaysf-results-desk-card span { color: #50575e; font-size: .9rem; }
            .vaysf-results-desk-section { margin: 28px 0; }
            .vaysf-results-desk-section h2 { margin-bottom: 4px; }
            .vaysf-results-desk-table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #dcdcde; }
            .vaysf-results-desk-table th, .vaysf-results-desk-table td { border-bottom: 1px solid #dcdcde; padding: 10px; text-align: left; vertical-align: top; }
            .vaysf-results-desk-table th { background: #f6f7f7; }
            .vaysf-results-desk-ok { background: #ecf7ed; border-left: 4px solid #46b450; padding: 12px 14px; }
            .vaysf-results-desk-heartbeat { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px; margin: 14px 0 24px; color: #50575e; }
            .vaysf-results-desk-help { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; background: #dcdcde; color: #1d2327; font-size: 12px; font-weight: 700; cursor: help; }
            .vaysf-results-desk-muted { color: #646970; font-size: .9em; }
            .vaysf-results-desk-warning { display: inline-block; border: 1px solid #dba617; border-radius: 4px; background: #fff8e5; color: #674e00; padding: 2px 6px; cursor: help; }
            .vaysf-results-desk-pill { display: inline-block; border: 1px solid #c3d9c8; border-radius: 4px; background: #ecf7ed; color: #1d5727; padding: 2px 6px; cursor: help; }
            .vaysf-results-desk-flag { margin: 4px 4px 0 0; font-size: .85em; }
            .vaysf-results-desk-progress { width: 160px; max-width: 100%; height: 10px; margin: 0 0 6px; overflow: hidden; border-radius: 999px; background: #dcdcde; cursor: help; }
            .vaysf-results-desk-progress span { display: block; height: 100%; background: #46b450; }
            .vaysf-results-desk-rankings { margin: 0; padding-left: 26px; }
            .vaysf-results-desk-rankings li { margin: 0 0 6px; }
            .vaysf-results-desk-rankings li:last-child { margin-bottom: 0; }
            .vaysf-pool-review-note-label { display: block; margin: 6px 0; max-width: 230px; font-size: .85em; color: #50575e; }
            .vaysf-pool-review-note { display: block; width: 100%; min-height: 44px; margin-top: 3px; font-size: 12px; }
            .vaysf-results-desk-note-display { display: inline-block; max-width: 260px; margin-top: 4px; color: #50575e; }
            .vaysf-playoff-preview-reviews { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 14px; }
            .vaysf-playoff-preview-list { margin: 0; padding-left: 22px; }
            .vaysf-playoff-preview-list li { margin: 0 0 5px; }
            .vaysf-playoff-preview-list li:last-child { margin-bottom: 0; }
            .vaysf-playoff-preview-table td:nth-child(3) { min-width: 220px; }
            .vaysf-bc-reorder-form { margin: 12px 0; padding: 10px; border: 1px solid #dcdcde; border-radius: 4px; background: #f9f9f9; }
            .vaysf-bc-reorder-grid { display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 10px; }
            .vaysf-bc-reorder-grid fieldset { display: flex; flex-direction: column; gap: 4px; min-width: 200px; padding: 8px; border: 1px solid #dcdcde; border-radius: 4px; }
            .vaysf-bc-reorder-grid legend { font-weight: 600; padding: 0 4px; }
            .vaysf-bc-apply-form { margin: 12px 0; padding: 10px; border: 1px solid #dba617; border-radius: 4px; background: #fff8e5; }
            .vaysf-playoff-assignment-form { margin: 12px 0; padding: 10px; border: 1px solid #dcdcde; border-radius: 4px; background: #f9f9f9; }
            .vaysf-playoff-assignment-grid { display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 10px; }
            .vaysf-playoff-assignment-grid fieldset { display: flex; flex-direction: column; gap: 6px; min-width: 220px; padding: 8px; border: 1px solid #dcdcde; border-radius: 4px; }
            .vaysf-playoff-assignment-grid label { display: flex; flex-direction: column; gap: 2px; }
            .vaysf-playoff-assignment-grid legend { font-weight: 600; padding: 0 4px; }
            .vaysf-playoff-apply-form { margin: 12px 0; padding: 10px; border: 1px solid #dba617; border-radius: 4px; background: #fff8e5; }
            .vaysf-qf-seeding-panel { margin: 12px 0; padding: 10px; border: 1px solid #dcdcde; border-radius: 4px; background: #f9f9f9; }
            .vaysf-qf-seeding-table { margin: 10px 0; }
            .vaysf-coin-toss-form { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 10px; margin: 10px 0; padding: 10px; border: 1px solid #dba617; border-radius: 4px; background: #fff8e5; }
            .vaysf-coin-toss-form p { flex-basis: 100%; margin: 0 0 4px; }
            .vaysf-coin-toss-form label { display: flex; flex-direction: column; gap: 2px; }
            @media (max-width: 768px) {
                .vaysf-results-desk-table { display: block; overflow-x: auto; }
            }
        </style>

        <h1><?php esc_html_e('Sports Fest Results Desk', 'vaysf'); ?></h1>
        <p class="vaysf-results-desk-subtitle"><?php esc_html_e('Read-only command center for missing, disputed, corrected, and scan-pending event-day results.', 'vaysf'); ?></p>

        <?php if (!is_user_logged_in()) : ?>
            <div class="vaysf-results-desk-notice">
                <p><?php esc_html_e('Please log in with a Sports Fest Manager or Admin account to view the Results Desk.', 'vaysf'); ?></p>
                <p><a href="<?php echo esc_url(wp_login_url($return_url)); ?>"><?php esc_html_e('Log in', 'vaysf'); ?></a></p>
            </div>
        <?php elseif (!vaysf_user_can_view_results_desk()) : ?>
            <div class="vaysf-results-desk-notice vaysf-results-desk-error">
                <p><?php esc_html_e('Your account is not authorized to view the Sports Fest Results Desk.', 'vaysf'); ?></p>
            </div>
        <?php else : ?>
            <?php
            $advancement_status = isset($_GET['vaysf_advancement_status']) ? sanitize_key(wp_unslash($_GET['vaysf_advancement_status'])) : '';
            $advancement_message = isset($_GET['vaysf_advancement_message']) ? sanitize_text_field(wp_unslash($_GET['vaysf_advancement_message'])) : '';
            if ($advancement_status !== '' && $advancement_message !== '') :
                $notice_class = $advancement_status === 'error' ? 'vaysf-results-desk-notice vaysf-results-desk-error' : 'vaysf-results-desk-notice vaysf-results-desk-ok';
                ?>
                <div class="<?php echo esc_attr($notice_class); ?>">
                    <p><?php echo esc_html($advancement_message); ?></p>
                </div>
            <?php endif; ?>
            <?php
            $summary = vaysf_get_results_desk_summary($filters);
            $events = vaysf_get_published_schedule_events($summary['schedule_version']);
            $churches = function_exists('vaysf_get_public_schedule_churches')
                ? vaysf_get_public_schedule_churches($summary['schedule_version'])
                : array();
            $manifest_url = wp_nonce_url(
                add_query_arg(
                    array_filter(
                        array(
                            'action' => 'vaysf_download_results_manifest',
                            'event' => $filters['event'],
                            'church' => $filters['church'],
                        )
                    ),
                    admin_url('admin-post.php')
                ),
                'vaysf_download_results_manifest'
            );
            ?>
            <form method="get" class="vaysf-results-desk-toolbar">
                <label>
                    <?php esc_html_e('Event', 'vaysf'); ?>
                    <select name="event">
                        <option value=""><?php esc_html_e('All events', 'vaysf'); ?></option>
                        <?php foreach ($events as $event) : ?>
                            <option value="<?php echo esc_attr($event); ?>" <?php selected($filters['event'], $event); ?>><?php echo esc_html($event); ?></option>
                        <?php endforeach; ?>
                    </select>
                </label>
                <?php if (!empty($churches)) : ?>
                    <label>
                        <?php esc_html_e('Church', 'vaysf'); ?>
                        <select name="church">
                            <option value=""><?php esc_html_e('All churches', 'vaysf'); ?></option>
                            <?php foreach ($churches as $code) : ?>
                                <option value="<?php echo esc_attr($code); ?>" <?php selected($filters['church'], $code); ?>><?php echo esc_html($code); ?></option>
                            <?php endforeach; ?>
                        </select>
                    </label>
                <?php endif; ?>
                <button type="submit" class="button button-primary"><?php esc_html_e('Filter', 'vaysf'); ?></button>
                <a class="button" href="<?php echo esc_url(vaysf_get_results_desk_url()); ?>"><?php esc_html_e('Reset', 'vaysf'); ?></a>
                <a class="button" href="<?php echo esc_url($manifest_url); ?>"><?php esc_html_e('Download Results Manifest CSV', 'vaysf'); ?></a>
            </form>

            <div class="vaysf-results-desk-cards">
                <div class="vaysf-results-desk-card"><strong><?php echo esc_html($summary['total_games']); ?></strong><span><?php esc_html_e('Published games', 'vaysf'); ?></span></div>
                <div class="vaysf-results-desk-card"><strong><?php echo esc_html($summary['reported_results']); ?></strong><span><?php esc_html_e('With score payloads', 'vaysf'); ?></span></div>
                <div class="vaysf-results-desk-card"><strong><?php echo esc_html($summary['late_missing']); ?></strong><span><?php esc_html_e('Late / missing', 'vaysf'); ?></span></div>
                <div class="vaysf-results-desk-card"><strong><?php echo esc_html($summary['attention']); ?></strong><span><?php esc_html_e('Need review', 'vaysf'); ?></span></div>
                <div class="vaysf-results-desk-card"><strong><?php echo esc_html($summary['missing_scans']); ?></strong><span><?php esc_html_e('Missing scans', 'vaysf'); ?></span></div>
                <div class="vaysf-results-desk-card"><strong><?php echo esc_html($summary['complete_pools']); ?></strong><span><?php esc_html_e('Ready pools', 'vaysf'); ?></span></div>
            </div>

            <div class="vaysf-results-desk-heartbeat">
                <div><strong><?php esc_html_e('Schedule version:', 'vaysf'); ?></strong> <?php echo esc_html($summary['schedule_version'] ?: '-'); ?></div>
                <div><strong><?php esc_html_e('Public data updated:', 'vaysf'); ?></strong> <?php echo esc_html(vaysf_format_results_desk_datetime($summary['public_data_updated_at'])); ?></div>
                <div><strong><?php esc_html_e('Sports Fest time:', 'vaysf'); ?></strong> <?php echo esc_html(vaysf_format_results_desk_datetime($summary['sports_fest_time'], vaysf_get_sports_fest_timezone())); ?></div>
            </div>

            <?php
            vaysf_render_results_desk_section(
                __('Late / Missing Results', 'vaysf'),
                sprintf(__('Games scheduled at least %d minutes ago with no score payload.', 'vaysf'), absint($filters['late_grace_minutes'])),
                vaysf_get_results_desk_rows('late_missing', $filters),
                __('No late missing results in this filter.', 'vaysf')
            );

            vaysf_render_results_desk_section(
                __('Recent Corrections', 'vaysf'),
                sprintf(__('Revision history from the last %d hours.', 'vaysf'), absint($filters['revision_hours'])),
                vaysf_get_results_desk_rows('recent_corrections', $filters),
                __('No recent corrections in this filter.', 'vaysf'),
                'correction'
            );

            vaysf_render_results_desk_section(
                __('Needs Review / Disputed', 'vaysf'),
                __('A first submission is accepted immediately; a game only lands here once a correction (a second, different score) has come in and needs a human to resolve the mismatch.', 'vaysf'),
                vaysf_get_results_desk_rows('attention', $filters),
                __('No results currently need review in this filter.', 'vaysf')
            );

            vaysf_render_results_desk_section(
                __('Missing Score Sheet Scans', 'vaysf'),
                __('Results with score payloads but no protected scan/photo attachment yet.', 'vaysf'),
                vaysf_get_results_desk_rows('missing_scans', $filters),
                __('No missing score sheet scans in this filter.', 'vaysf')
            );
            ?>

            <section class="vaysf-results-desk-section">
                <h2>
                    <?php esc_html_e('Pools Progress For Review', 'vaysf'); ?>
                    <?php vaysf_render_results_desk_tooltip('?', __('This section is a review aid. It summarizes pool/prelim progress and provisional ranking signals from submitted score payloads, but it does not confirm advancement automatically.', 'vaysf')); ?>
                </h2>
                <p><?php esc_html_e('Pool/prelim progress and provisional ranking signals from current score payloads. Use this to decide advancement manually.', 'vaysf'); ?></p>
                <?php $pool_progress = vaysf_get_results_desk_rows('pool_progress', $filters); ?>
                <?php if (!$pool_progress) : ?>
                    <div class="vaysf-results-desk-ok"><?php esc_html_e('No pool progress is available in this filter.', 'vaysf'); ?></div>
                <?php else : ?>
                    <table class="vaysf-results-desk-table">
                        <thead>
                            <tr>
                                <th><?php esc_html_e('Pool', 'vaysf'); ?></th>
                                <th>
                                    <?php esc_html_e('Progress', 'vaysf'); ?>
                                    <?php vaysf_render_results_desk_tooltip('?', __('Reported games divided by total published pool/prelim games.', 'vaysf')); ?>
                                </th>
                                <th>
                                    <?php esc_html_e('Provisional Rankings', 'vaysf'); ?>
                                    <?php vaysf_render_results_desk_tooltip('?', __('Default rankings sort by wins, then ties, point differential, and points for. Bible Challenge ranks by cumulative preliminary score, and the top 9 advance. Cutoff ties still require human review.', 'vaysf')); ?>
                                </th>
                                <th>
                                    <?php esc_html_e('Review Status', 'vaysf'); ?>
                                    <?php vaysf_render_results_desk_tooltip('?', __('Ready means all games in this pool have a score payload. It does not mean semifinal/final slots were confirmed.', 'vaysf')); ?>
                                </th>
                                <th><?php esc_html_e('Last Updated', 'vaysf'); ?></th>
                                <th>
                                    <?php esc_html_e('Advancement', 'vaysf'); ?>
                                    <?php vaysf_render_results_desk_tooltip('?', __('Confirming advancement records who confirmed it and when. It does not move teams into Semifinal/Final schedule rows for you — use the schedule editor for that once you trust the ranking shown here.', 'vaysf')); ?>
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            <?php foreach ($pool_progress as $pool) : ?>
                                <?php vaysf_render_results_desk_pool_progress_row($pool, $return_url); ?>
                            <?php endforeach; ?>
                        </tbody>
                    </table>
                <?php endif; ?>
            </section>

            <?php vaysf_render_results_desk_playoff_preview(vaysf_get_results_desk_playoff_preview($filters), $filters, $return_url); ?>
        <?php endif; ?>
    </div>
    <?php

    return ob_get_clean();
}

/**
 * Render a Results Desk link on user profile screens, for Sports Fest
 * Managers/Admins, right above the "Update Profile" button.
 *
 * @param WP_User $user User being viewed
 * @return void
 */
function vaysf_render_results_desk_profile_link($user) {
    if (!is_object($user) || !vaysf_user_can_view_results_desk($user->ID)) {
        return;
    }

    if ((int) get_current_user_id() !== (int) $user->ID && !current_user_can('edit_user', $user->ID)) {
        return;
    }

    ?>
    <h2><?php esc_html_e('Sports Fest Results Desk', 'vaysf'); ?></h2>
    <table class="form-table" role="presentation">
        <tr>
            <th scope="row"><?php esc_html_e('Results Desk', 'vaysf'); ?></th>
            <td>
                <p>
                    <a class="button button-primary" href="<?php echo esc_url(vaysf_get_results_desk_url()); ?>">
                        <?php esc_html_e('Open Results Desk', 'vaysf'); ?>
                    </a>
                </p>
                <p class="description">
                    <?php esc_html_e('Read-only command center for missing, disputed, corrected, and scan-pending event-day results.', 'vaysf'); ?>
                </p>
            </td>
        </tr>
    </table>
    <?php
}

/**
 * Register a wp-admin dashboard widget for Sports Fest Managers/Admins.
 *
 * @return void
 */
function vaysf_register_results_desk_dashboard_widget() {
    if (!vaysf_user_can_view_results_desk()) {
        return;
    }

    wp_add_dashboard_widget(
        'vaysf_results_desk',
        esc_html__('Sports Fest Results Desk', 'vaysf'),
        'vaysf_render_results_desk_dashboard_widget'
    );
}

/**
 * Render the wp-admin Results Desk dashboard widget.
 *
 * @return void
 */
function vaysf_render_results_desk_dashboard_widget() {
    $summary = vaysf_get_results_desk_summary();
    ?>
    <p><?php esc_html_e('Review event-day results that are missing, disputed, corrected, scan-pending, or ready for advancement review.', 'vaysf'); ?></p>
    <ul>
        <li><strong><?php echo esc_html($summary['late_missing']); ?></strong> <?php esc_html_e('late/missing results', 'vaysf'); ?></li>
        <li><strong><?php echo esc_html($summary['attention']); ?></strong> <?php esc_html_e('results needing review', 'vaysf'); ?></li>
        <li><strong><?php echo esc_html($summary['missing_scans']); ?></strong> <?php esc_html_e('missing score sheet scans', 'vaysf'); ?></li>
        <li><strong><?php echo esc_html($summary['complete_pools']); ?></strong> <?php esc_html_e('pools ready for human advancement review', 'vaysf'); ?></li>
    </ul>
    <p>
        <a class="button button-primary" href="<?php echo esc_url(vaysf_get_results_desk_url()); ?>">
            <?php esc_html_e('Open Results Desk', 'vaysf'); ?>
        </a>
    </p>
    <?php
}

/**
 * Download the current event-day result manifest as CSV.
 *
 * @return void
 */
function vaysf_download_results_manifest() {
    if (!vaysf_user_can_view_results_desk()) {
        wp_die(esc_html__('You are not authorized to download the Results Desk manifest.', 'vaysf'), 403);
    }

    if (empty($_GET['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_GET['_wpnonce'])), 'vaysf_download_results_manifest')) {
        wp_die(esc_html__('Security check failed. Please try again.', 'vaysf'), 403);
    }

    global $wpdb;
    $schedule_version = vaysf_get_current_published_schedule_version();
    $event = isset($_GET['event']) ? sanitize_text_field(wp_unslash($_GET['event'])) : '';
    $church = isset($_GET['church']) ? vaysf_sanitize_public_church_filter($_GET['church']) : '';
    $table_schedules = vaysf_get_table_name('schedules');
    $table_results = vaysf_get_table_name('results');
    $table_revisions = vaysf_get_table_name('result_revisions');
    $table_files = vaysf_get_table_name('result_files');

    $where = array(
        's.schedule_version = %d',
        's.published_at IS NOT NULL',
        "COALESCE(s.game_status, '') <> 'cancelled'",
    );
    $args = array($schedule_version);
    vaysf_results_desk_add_event_filter($where, $args, $event);
    vaysf_results_desk_add_church_filter($where, $args, $church);

    $sql = "SELECT s.game_key, s.schedule_version, s.event, s.stage, s.pool_id,
            s.scheduled_time, s.scheduled_location, s.resource_id,
            s.team_a_label, s.team_b_label, s.team_c_label, s.game_status,
            r.result_id, r.public_status, r.scan_status, r.current_revision,
            r.certified_at, r.verified_at, r.updated_at AS result_updated_at,
            r.score_json, r.winner_keys_json,
            COUNT(f.file_id) AS file_count
        FROM $table_schedules s
        LEFT JOIN $table_results r ON r.schedule_id = s.schedule_id
        LEFT JOIN $table_revisions rr ON rr.result_id = r.result_id
        LEFT JOIN $table_files f ON f.result_revision_id = rr.revision_id
        WHERE " . implode(' AND ', $where) . "
        GROUP BY s.schedule_id, r.result_id
        ORDER BY s.scheduled_time IS NULL, s.scheduled_time, s.event, s.game_key";

    $rows = $wpdb->get_results($wpdb->prepare($sql, $args), ARRAY_A);
    if (!is_array($rows)) {
        $rows = array();
    }

    nocache_headers();
    header('Content-Type: text/csv; charset=utf-8');
    header('Content-Disposition: attachment; filename=vaysf-results-manifest-' . date_i18n('Ymd-His') . '.csv');

    $output = fopen('php://output', 'w');
    fputcsv($output, array(
        'game_key',
        'schedule_version',
        'event',
        'stage',
        'pool_id',
        'scheduled_time',
        'location',
        'matchup',
        'game_status',
        'result_id',
        'public_status',
        'scan_status',
        'current_revision',
        'certified_at',
        'verified_at',
        'result_updated_at',
        'file_count',
        'score_json',
        'winner_keys_json',
    ));

    foreach ($rows as $row) {
        fputcsv($output, array(
            $row['game_key'],
            $row['schedule_version'],
            $row['event'],
            $row['stage'],
            $row['pool_id'],
            $row['scheduled_time'],
            $row['scheduled_location'] ?: $row['resource_id'],
            vaysf_format_schedule_teams($row),
            $row['game_status'],
            $row['result_id'],
            $row['public_status'],
            $row['scan_status'],
            $row['current_revision'],
            $row['certified_at'],
            $row['verified_at'],
            $row['result_updated_at'],
            $row['file_count'],
            $row['score_json'],
            $row['winner_keys_json'],
        ));
    }

    fclose($output);
    exit;
}

/**
 * Handle the Results Desk "Confirm Advancement" form submission (Issue #207).
 *
 * Registered as admin_post_vaysf_confirm_pool_advancement in vaysf.php.
 * Redirects back to the Results Desk with a flash message rather than
 * wp_die-ing on ordinary failures (unresolved tie, incomplete pool) — those
 * are expected operator states, not security errors.
 *
 * @return void
 */
function vaysf_handle_confirm_pool_advancement_request() {
    $return_url = isset($_POST['return_url']) ? esc_url_raw(wp_unslash($_POST['return_url'])) : '';
    if ($return_url === '') {
        $return_url = wp_get_referer();
    }
    if (!$return_url) {
        $return_url = vaysf_get_results_desk_url();
    }
    $return_url = remove_query_arg(array('vaysf_advancement_status', 'vaysf_advancement_message'), $return_url);

    if (!vaysf_user_can_view_results_desk()) {
        wp_die(esc_html__('You are not authorized to confirm pool advancement.', 'vaysf'), 403);
    }

    $event = isset($_POST['event']) ? sanitize_text_field(wp_unslash($_POST['event'])) : '';
    $pool_id = isset($_POST['pool_id']) ? sanitize_text_field(wp_unslash($_POST['pool_id'])) : '';
    $nonce_action = 'vaysf_confirm_pool_advancement_' . $event . '_' . $pool_id;

    if (empty($_POST['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'])), $nonce_action)) {
        wp_die(esc_html__('Security check failed. Please try again.', 'vaysf'), 403);
    }

    $review_note = isset($_POST['review_note']) ? sanitize_textarea_field(wp_unslash($_POST['review_note'])) : '';
    $result = vaysf_confirm_pool_advancement(get_current_user_id(), $event, $pool_id, $review_note);

    if (is_wp_error($result)) {
        $redirect = add_query_arg(
            array(
                'vaysf_advancement_status' => 'error',
                'vaysf_advancement_message' => rawurlencode($result->get_error_message()),
            ),
            $return_url
        );
    } else {
        $redirect = add_query_arg(
            array(
                'vaysf_advancement_status' => 'success',
                'vaysf_advancement_message' => rawurlencode(
                    sprintf(
                        /* translators: %s: event and pool label */
                        __('Pool review confirmed for %s.', 'vaysf'),
                        trim($event . ' ' . $pool_id)
                    )
                ),
            ),
            $return_url
        );
    }

    wp_safe_redirect($redirect);
    exit;
}

/**
 * admin-post handler for "Confirm All Pools for QF Seeding" (Issue #329) —
 * see vaysf_confirm_event_qf_seeding().
 *
 * @return void
 */
function vaysf_handle_confirm_event_qf_seeding_request() {
    $return_url = isset($_POST['return_url']) ? esc_url_raw(wp_unslash($_POST['return_url'])) : '';
    if ($return_url === '') {
        $return_url = wp_get_referer();
    }
    if (!$return_url) {
        $return_url = vaysf_get_results_desk_url();
    }
    $return_url = remove_query_arg(array('vaysf_advancement_status', 'vaysf_advancement_message'), $return_url);

    if (!vaysf_user_can_view_results_desk()) {
        wp_die(esc_html__('You are not authorized to confirm QF seeding.', 'vaysf'), 403);
    }

    $event = isset($_POST['event']) ? sanitize_text_field(wp_unslash($_POST['event'])) : '';
    $schedule_version = isset($_POST['schedule_version']) ? absint($_POST['schedule_version']) : 0;
    $nonce_action = 'vaysf_confirm_event_qf_seeding_' . $event . '_' . $schedule_version;

    if (empty($_POST['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'])), $nonce_action)) {
        wp_die(esc_html__('Security check failed. Please try again.', 'vaysf'), 403);
    }

    $result = vaysf_confirm_event_qf_seeding(get_current_user_id(), $event, $schedule_version);

    if (is_wp_error($result)) {
        $redirect = add_query_arg(
            array(
                'vaysf_advancement_status' => 'error',
                'vaysf_advancement_message' => rawurlencode($result->get_error_message()),
            ),
            $return_url
        );
    } else {
        $redirect = add_query_arg(
            array(
                'vaysf_advancement_status' => 'success',
                'vaysf_advancement_message' => rawurlencode(
                    sprintf(
                        /* translators: %s: event label */
                        __('QF seeding confirmed for %s.', 'vaysf'),
                        $event
                    )
                ),
            ),
            $return_url
        );
    }

    wp_safe_redirect($redirect);
    exit;
}

/**
 * admin-post handler for one coin-toss flip (Issue #329) — see
 * vaysf_record_coin_toss_flip().
 *
 * @return void
 */
function vaysf_handle_flip_coin_toss_request() {
    $return_url = isset($_POST['return_url']) ? esc_url_raw(wp_unslash($_POST['return_url'])) : '';
    if ($return_url === '') {
        $return_url = wp_get_referer();
    }
    if (!$return_url) {
        $return_url = vaysf_get_results_desk_url();
    }
    $return_url = remove_query_arg(array('vaysf_advancement_status', 'vaysf_advancement_message'), $return_url);

    if (!vaysf_user_can_view_results_desk()) {
        wp_die(esc_html__('You are not authorized to flip a coin toss.', 'vaysf'), 403);
    }

    $event = isset($_POST['event']) ? sanitize_text_field(wp_unslash($_POST['event'])) : '';
    $schedule_version = isset($_POST['schedule_version']) ? absint($_POST['schedule_version']) : 0;
    $team_a_key = isset($_POST['team_a_key']) ? sanitize_text_field(wp_unslash($_POST['team_a_key'])) : '';
    $team_b_key = isset($_POST['team_b_key']) ? sanitize_text_field(wp_unslash($_POST['team_b_key'])) : '';
    $nonce_action = 'vaysf_flip_coin_toss_' . $event . '_' . $schedule_version . '_' . $team_a_key . '_' . $team_b_key;

    if (empty($_POST['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'])), $nonce_action)) {
        wp_die(esc_html__('Security check failed. Please try again.', 'vaysf'), 403);
    }

    $team_a_label = isset($_POST['team_a_label']) ? sanitize_text_field(wp_unslash($_POST['team_a_label'])) : $team_a_key;
    $team_b_label = isset($_POST['team_b_label']) ? sanitize_text_field(wp_unslash($_POST['team_b_label'])) : $team_b_key;
    $call_by_key = isset($_POST['call_by_key']) ? sanitize_text_field(wp_unslash($_POST['call_by_key'])) : '';
    $call = isset($_POST['call']) ? sanitize_text_field(wp_unslash($_POST['call'])) : '';

    $result = vaysf_record_coin_toss_flip(
        get_current_user_id(),
        $event,
        $schedule_version,
        $team_a_key,
        $team_a_label,
        $team_b_key,
        $team_b_label,
        $call_by_key,
        $call
    );

    if (is_wp_error($result)) {
        $redirect = add_query_arg(
            array(
                'vaysf_advancement_status' => 'error',
                'vaysf_advancement_message' => rawurlencode($result->get_error_message()),
            ),
            $return_url
        );
    } else {
        $redirect = add_query_arg(
            array(
                'vaysf_advancement_status' => 'success',
                'vaysf_advancement_message' => rawurlencode(
                    sprintf(
                        /* translators: 1: coin toss result, 2: winning team label */
                        __('Coin toss: %1$s. %2$s wins the tiebreak.', 'vaysf'),
                        $result['result'],
                        $result['winner_label']
                    )
                ),
            ),
            $return_url
        );
    }

    wp_safe_redirect($redirect);
    exit;
}

/**
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

/**
 * admin-post handler for the Bible Challenge "Apply matchup to schedule"
 * button (see vaysf_render_results_desk_bible_challenge_apply_form()).
 *
 * @return void
 */
function vaysf_handle_apply_bible_challenge_preview_request() {
    $return_url = isset($_POST['return_url']) ? esc_url_raw(wp_unslash($_POST['return_url'])) : '';
    if ($return_url === '') {
        $return_url = wp_get_referer();
    }
    if (!$return_url) {
        $return_url = vaysf_get_results_desk_url();
    }
    $return_url = remove_query_arg(array('vaysf_advancement_status', 'vaysf_advancement_message'), $return_url);

    if (!vaysf_user_can_view_results_desk()) {
        wp_die(esc_html__('You are not authorized to apply the Bible Challenge semifinal matchup.', 'vaysf'), 403);
    }

    $event = isset($_POST['event']) ? sanitize_text_field(wp_unslash($_POST['event'])) : '';
    $schedule_version = isset($_POST['schedule_version']) ? absint($_POST['schedule_version']) : 0;
    $nonce_action = 'vaysf_apply_bible_challenge_preview_' . $event . '_' . $schedule_version;

    if (empty($_POST['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'])), $nonce_action)) {
        wp_die(esc_html__('Security check failed. Please try again.', 'vaysf'), 403);
    }

    $arrangement = array();
    if (isset($_POST['bc_seed']) && is_array($_POST['bc_seed'])) {
        $submitted = wp_unslash($_POST['bc_seed']);
        foreach ($submitted as $game_key => $picks) {
            $game_key = sanitize_text_field($game_key);
            $arrangement[$game_key] = is_array($picks) ? array_map('sanitize_text_field', $picks) : array();
        }
    }

    $result = vaysf_apply_bible_challenge_playoff_preview($event, $schedule_version, $arrangement);

    if (is_wp_error($result)) {
        $redirect = add_query_arg(
            array(
                'vaysf_advancement_status' => 'error',
                'vaysf_advancement_message' => rawurlencode($result->get_error_message()),
            ),
            $return_url
        );
    } else {
        $skipped = 0;
        foreach ($result as $row) {
            if (($row['action'] ?? '') === 'skipped_protected') {
                $skipped++;
            }
        }
        $message = $skipped > 0
            ? sprintf(
                /* translators: %d: number of schedule rows left unchanged because they already had a protected result */
                __('Applied Bible Challenge semifinal matchup; %d row(s) already had a protected result and were left unchanged.', 'vaysf'),
                $skipped
            )
            : __('Applied Bible Challenge semifinal matchup to BC-Semi-1, BC-Semi-2, and BC-Semi-3.', 'vaysf');
        $redirect = add_query_arg(
            array(
                'vaysf_advancement_status' => 'success',
                'vaysf_advancement_message' => rawurlencode($message),
            ),
            $return_url
        );
    }

    wp_safe_redirect($redirect);
    exit;
}

/**
 * admin-post handler for Basketball/Volleyball QF Apply.
 *
 * @return void
 */
function vaysf_handle_apply_team_qf_preview_request() {
    $return_url = isset($_POST['return_url']) ? esc_url_raw(wp_unslash($_POST['return_url'])) : '';
    if ($return_url === '') {
        $return_url = wp_get_referer();
    }
    if (!$return_url) {
        $return_url = vaysf_get_results_desk_url();
    }
    $return_url = remove_query_arg(array('vaysf_advancement_status', 'vaysf_advancement_message'), $return_url);

    if (!vaysf_user_can_manage_team_qf_schedule()) {
        wp_die(esc_html__('You are not authorized to apply QF matchups.', 'vaysf'), 403);
    }

    $event = isset($_POST['event']) ? sanitize_text_field(wp_unslash($_POST['event'])) : '';
    $schedule_version = isset($_POST['schedule_version']) ? absint($_POST['schedule_version']) : 0;

    // Results Desk roles (sf2025_write/admin) implicitly cover every event;
    // a coordinator (no Results Desk access) is restricted to their own
    // authorized events — the same scoping already used for score
    // submission — so a Volleyball-only coordinator can't Apply Basketball's
    // bracket just by guessing the right POST fields.
    if (!vaysf_user_can_view_results_desk() && !in_array($event, vaysf_get_user_score_entry_events(get_current_user_id()), true)) {
        wp_die(esc_html__('You are not authorized to apply QF matchups for this event.', 'vaysf'), 403);
    }

    $nonce_action = 'vaysf_apply_team_qf_preview_' . $event . '_' . $schedule_version;

    if (empty($_POST['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'])), $nonce_action)) {
        wp_die(esc_html__('Security check failed. Please try again.', 'vaysf'), 403);
    }

    $arrangement = array();
    if (isset($_POST['qf_seed']) && is_array($_POST['qf_seed'])) {
        $submitted = wp_unslash($_POST['qf_seed']);
        foreach ($submitted as $game_key => $picks) {
            $game_key = sanitize_text_field($game_key);
            $arrangement[$game_key] = is_array($picks) ? array_map('sanitize_text_field', $picks) : array();
        }
    }

    $result = vaysf_apply_team_qf_playoff_preview($event, $schedule_version, $arrangement);

    if (is_wp_error($result)) {
        $redirect = add_query_arg(
            array(
                'vaysf_advancement_status' => 'error',
                'vaysf_advancement_message' => rawurlencode($result->get_error_message()),
            ),
            $return_url
        );
    } else {
        $skipped = 0;
        foreach ($result as $row) {
            if (($row['action'] ?? '') === 'skipped_protected') {
                $skipped++;
            }
        }
        $message = $skipped > 0
            ? sprintf(
                /* translators: %d: number of QF schedule rows left unchanged */
                __('Applied QF matchup; %d row(s) already had a protected result and were left unchanged.', 'vaysf'),
                $skipped
            )
            : __('Applied QF matchup and prewired Semifinal/Final/3rd-Place placeholders.', 'vaysf');
        $redirect = add_query_arg(
            array(
                'vaysf_advancement_status' => 'success',
                'vaysf_advancement_message' => rawurlencode($message),
            ),
            $return_url
        );
    }

    wp_safe_redirect($redirect);
    exit;
}

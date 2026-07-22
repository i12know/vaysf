<?php
/**
 * File: includes/results-desk/access.php
 * Description: Results Desk access checks and shared query/date helpers.
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
 * Check whether a user may confirm/re-confirm a pool's advancement review
 * (Bible Challenge "Confirm Top 9" or any other event's "Confirm Pool
 * Review") — broader than vaysf_user_can_view_results_desk(), since the
 * shared Pools Progress table renders this same form on the Coordinator
 * Score Entry dashboard for coordinators (sf2025_submit_results, no Results
 * Desk access), not just on the Results Desk.
 *
 * @param int|null $user_id WordPress user id; defaults to current user
 * @return bool
 */
function vaysf_user_can_confirm_pool_review($user_id = null) {
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

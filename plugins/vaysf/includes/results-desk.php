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
 * Build the Results Desk route URL.
 *
 * @return string
 */
function vaysf_get_results_desk_url() {
    return site_url('results-desk');
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
            $pool = vaysf_get_pool_progress_row($event, $pool_id);
            $current_rankings = is_array($pool) ? ($pool['rankings'] ?? array()) : array();
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
 * pool is incomplete or any team is in an unresolved tie, and upserts the
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
 * @return array<int,array<string,mixed>>|WP_Error Standings snapshot on success
 */
function vaysf_confirm_pool_advancement($user_id, $event, $pool_id) {
    global $wpdb;

    $user_id = absint($user_id);
    $event = sanitize_text_field($event);
    $pool_id = sanitize_text_field($pool_id);
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
    if (!empty($pool['needs_manual_tiebreak'])) {
        return new WP_Error('vaysf_advancement_unresolved_tiebreak', __('Standings have a tie that head-to-head results cannot resolve. Decide the order manually before confirming.', 'vaysf'));
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
                'updated_at' => $now,
            ),
            array('advancement_id' => absint($existing['advancement_id'])),
            array('%d', '%d', '%s', '%s', '%s', '%s'),
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
                'created_at' => $now,
                'updated_at' => $now,
            ),
            array('%s', '%s', '%d', '%d', '%s', '%s', '%s', '%s', '%s')
        );
        if ($created === false) {
            return new WP_Error('vaysf_advancement_create_failed', __('Could not create the advancement confirmation.', 'vaysf'));
        }
    }

    return $pool['rankings'];
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
    if ($return_url === '' && isset($_SERVER['REQUEST_URI'])) {
        $return_url = home_url(wp_unslash($_SERVER['REQUEST_URI']));
    }
    if ($return_url === '') {
        $return_url = vaysf_get_results_desk_url();
    }

    $game_count = max(0, (int) ($pool['game_count'] ?? 0));
    $reported_count = max(0, (int) ($pool['reported_count'] ?? 0));
    $missing_count = max(0, (int) ($pool['missing_count'] ?? 0));
    $percent = $game_count > 0 ? round(($reported_count / $game_count) * 100) : 0;
    $flags = !empty($pool['flags']) && is_array($pool['flags']) ? array_values($pool['flags']) : array();
    $flag_tooltip = $flags ? implode(' ', $flags) : __('No ranking flags for this pool.', 'vaysf');
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
            <?php if ($flags) : ?>
                <br><small><?php echo esc_html(implode(' ', array_keys($pool['flags']))); ?></small>
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
            <?php endif; ?>
            <?php if (!empty($pool['complete']) && empty($pool['needs_manual_tiebreak'])) : ?>
                <?php
                $is_bible_challenge_pool = vaysf_results_desk_is_bible_challenge_event($pool_event);
                if ($is_bible_challenge_pool) {
                    $confirm_label = $advancement ? __('Re-confirm Top 9', 'vaysf') : __('Confirm Top 9', 'vaysf');
                    $confirm_tooltip = $advancement
                        ? __('Update the saved Bible Challenge advancement confirmation using the current top 9 teams by cumulative preliminary score. This does not change scores or automatically populate semifinal/final games.', 'vaysf')
                        : __('Save the current Bible Challenge top 9 teams by cumulative preliminary score as reviewed for advancement. This does not change scores or automatically populate semifinal/final games.', 'vaysf');
                } else {
                    $confirm_label = $advancement ? __('Re-confirm Pool Review', 'vaysf') : __('Confirm Pool Review', 'vaysf');
                    $confirm_tooltip = $advancement
                        ? __('Update this pool ranking as reviewed for event-level QF/playoff finalization. This does not choose wildcards, assign seeds, submit QF matchups, change scores, or populate schedule rows.', 'vaysf')
                        : __('Record this pool ranking as reviewed for event-level QF/playoff finalization. This does not choose wildcards, assign seeds, submit QF matchups, change scores, or populate schedule rows.', 'vaysf');
                }
                ?>
                <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                    <input type="hidden" name="action" value="vaysf_confirm_pool_advancement">
                    <input type="hidden" name="event" value="<?php echo esc_attr($pool_event); ?>">
                    <input type="hidden" name="pool_id" value="<?php echo esc_attr($pool_id_value); ?>">
                    <input type="hidden" name="return_url" value="<?php echo esc_attr($return_url); ?>">
                    <?php wp_nonce_field('vaysf_confirm_pool_advancement_' . $pool_event . '_' . $pool_id_value); ?>
                    <button type="submit" class="button button-primary button-small" title="<?php echo esc_attr($confirm_tooltip); ?>" aria-label="<?php echo esc_attr($confirm_tooltip); ?>">
                        <?php echo esc_html($confirm_label); ?>
                    </button>
                </form>
            <?php elseif (!empty($pool['needs_manual_tiebreak'])) : ?>
                <br><small><?php esc_html_e('Resolve the tie above before confirming.', 'vaysf'); ?></small>
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
    $return_url = isset($_SERVER['REQUEST_URI'])
        ? esc_url_raw(home_url(wp_unslash($_SERVER['REQUEST_URI'])))
        : vaysf_get_results_desk_url();

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
            .vaysf-results-desk-progress { width: 160px; max-width: 100%; height: 10px; margin: 0 0 6px; overflow: hidden; border-radius: 999px; background: #dcdcde; cursor: help; }
            .vaysf-results-desk-progress span { display: block; height: 100%; background: #46b450; }
            .vaysf-results-desk-rankings { margin: 0; padding-left: 26px; }
            .vaysf-results-desk-rankings li { margin: 0 0 6px; }
            .vaysf-results-desk-rankings li:last-child { margin-bottom: 0; }
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

    $result = vaysf_confirm_pool_advancement(get_current_user_id(), $event, $pool_id);

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
                        __('Advancement confirmed for %s.', 'vaysf'),
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

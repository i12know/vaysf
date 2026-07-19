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
 * @return void
 */
function vaysf_results_desk_apply_pool_result(&$teams, &$flags, $row) {
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
    if ($is_tie) {
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

/**
 * Sort provisional pool rankings with conservative shared metrics.
 *
 * @param array<string,array<string,mixed>> $teams Ranking map
 * @return array<int,array<string,mixed>>
 */
function vaysf_results_desk_sort_pool_rankings($teams) {
    $rankings = array_values($teams);
    usort($rankings, function ($a, $b) {
        foreach (array('wins', 'ties', 'diff', 'for') as $metric) {
            $a_value = isset($a[$metric]) ? (int) $a[$metric] : 0;
            $b_value = isset($b[$metric]) ? (int) $b[$metric] : 0;
            if ($a_value !== $b_value) {
                return $a_value > $b_value ? -1 : 1;
            }
        }

        return strcasecmp((string) ($a['label'] ?? ''), (string) ($b['label'] ?? ''));
    });

    $rank = 1;
    $previous = null;
    foreach ($rankings as $index => $team) {
        $signature = array(
            (int) $team['wins'],
            (int) $team['ties'],
            (int) $team['diff'],
            (int) $team['for'],
        );
        if ($previous !== null && $signature !== $previous) {
            $rank = $index + 1;
        }
        $rankings[$index]['rank'] = $rank;
        $previous = $signature;
    }

    return $rankings;
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

        vaysf_results_desk_apply_pool_result($pool_teams[$key], $pools[$key]['flags'], $row);
    }

    foreach ($pools as $key => $pool) {
        if ($filters['church'] !== '' && empty($pool['matches_church_filter'])) {
            unset($pools[$key], $pool_teams[$key]);
            continue;
        }

        $pools[$key]['complete'] = ((int) $pool['game_count'] > 0 && (int) $pool['missing_count'] === 0);
        $pools[$key]['rankings'] = vaysf_results_desk_sort_pool_rankings($pool_teams[$key] ?? array());
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
 * @return void
 */
function vaysf_render_results_desk_pool_rankings($rankings) {
    if (!$rankings) {
        echo '<span class="vaysf-results-desk-muted">' . esc_html__('No scored games yet.', 'vaysf') . '</span>';
        return;
    }
    ?>
    <ol class="vaysf-results-desk-rankings">
        <?php foreach ($rankings as $team) : ?>
            <?php
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
            $notes = !empty($team['notes']) && is_array($team['notes']) ? implode('; ', $team['notes']) : '';
            ?>
            <li value="<?php echo esc_attr((string) ($team['rank'] ?? 1)); ?>">
                <strong><?php echo esc_html($team['label'] ?? $team['team_key'] ?? ''); ?></strong>
                <span class="vaysf-results-desk-pill" title="<?php echo esc_attr__('Record is wins-losses-ties from scored pool games.', 'vaysf'); ?>"><?php echo esc_html($record); ?></span>
                <span class="vaysf-results-desk-muted" title="<?php echo esc_attr__('PF/PA are points for and points against from the score payload. For volleyball this uses match score units, usually sets won/lost.', 'vaysf'); ?>"><?php echo esc_html($metric); ?></span>
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
 * @return void
 */
function vaysf_render_results_desk_pool_progress_row($pool) {
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
            <?php vaysf_render_results_desk_pool_rankings($pool['rankings'] ?? array()); ?>
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
                                    <?php vaysf_render_results_desk_tooltip('?', __('Rankings sort by wins, then ties, point differential, and points for. Ties and sport-specific tiebreakers still require human review.', 'vaysf')); ?>
                                </th>
                                <th>
                                    <?php esc_html_e('Review Status', 'vaysf'); ?>
                                    <?php vaysf_render_results_desk_tooltip('?', __('Ready means all games in this pool have a score payload. It does not mean semifinal/final slots were confirmed.', 'vaysf')); ?>
                                </th>
                                <th><?php esc_html_e('Last Updated', 'vaysf'); ?></th>
                            </tr>
                        </thead>
                        <tbody>
                            <?php foreach ($pool_progress as $pool) : ?>
                                <?php vaysf_render_results_desk_pool_progress_row($pool); ?>
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

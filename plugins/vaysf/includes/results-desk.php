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
 * in SQL so it works across the GROUP BY aggregate used by complete_pools.
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
        $where = $base_where;
        $args = $base_args;
        $where[] = 's.scheduled_time IS NOT NULL';
        $where[] = 's.scheduled_time <= %s';
        $where[] = "(r.result_id IS NULL OR COALESCE(r.score_json, '') = '')";
        $args[] = date('Y-m-d H:i:s', current_time('timestamp') - (absint($filters['late_grace_minutes']) * MINUTE_IN_SECONDS));
        $args[] = $limit;

        $sql = "SELECT s.*, r.result_id, r.public_status, r.scan_status, r.updated_at AS result_updated_at
            FROM $table_schedules s
            LEFT JOIN $table_results r ON r.schedule_id = s.schedule_id
            WHERE " . implode(' AND ', $where) . "
            ORDER BY s.scheduled_time, s.event, s.game_key
            LIMIT %d";

        $rows = $wpdb->get_results($wpdb->prepare($sql, $args), ARRAY_A);
        return is_array($rows) ? $rows : array();
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
        $args[] = date('Y-m-d H:i:s', current_time('timestamp') - (absint($filters['revision_hours']) * HOUR_IN_SECONDS));
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

    if ($section === 'complete_pools') {
        $where = $base_where;
        $args = $base_args;
        $where[] = "COALESCE(s.pool_id, '') <> ''";
        $where[] = "LOWER(COALESCE(s.stage, '')) IN ('pool', 'prelim', 'preliminary')";
        $args[] = $limit;

        $sql = "SELECT s.event, s.stage, s.pool_id,
                COUNT(*) AS game_count,
                SUM(CASE WHEN r.result_id IS NULL OR COALESCE(r.score_json, '') = '' THEN 1 ELSE 0 END) AS missing_count,
                MAX(COALESCE(r.updated_at, s.updated_at)) AS last_updated_at
            FROM $table_schedules s
            LEFT JOIN $table_results r ON r.schedule_id = s.schedule_id
            WHERE " . implode(' AND ', $where) . "
            GROUP BY s.event, s.stage, s.pool_id
            HAVING game_count > 0 AND missing_count = 0
            ORDER BY last_updated_at DESC, s.event, s.pool_id
            LIMIT %d";

        $rows = $wpdb->get_results($wpdb->prepare($sql, $args), ARRAY_A);
        return is_array($rows) ? $rows : array();
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
        'server_time' => current_time('mysql'),
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
            SUM(CASE WHEN s.scheduled_time IS NOT NULL AND s.scheduled_time <= %s AND (r.result_id IS NULL OR COALESCE(r.score_json, '') = '') THEN 1 ELSE 0 END) AS late_missing,
            SUM(CASE WHEN r.result_id IS NOT NULL AND (r.current_revision > 1 OR r.public_status IN ('in_progress', 'under_review')) THEN 1 ELSE 0 END) AS attention,
            MAX(s.updated_at) AS last_schedule_update,
            MAX(r.updated_at) AS last_result_update
        FROM $table_schedules s
        LEFT JOIN $table_results r ON r.schedule_id = s.schedule_id
        WHERE $where_clause";

    $summary_args = array_merge(
        array(date('Y-m-d H:i:s', current_time('timestamp') - (absint($filters['late_grace_minutes']) * MINUTE_IN_SECONDS))),
        $args
    );
    $summary = $wpdb->get_row($wpdb->prepare($summary_sql, $summary_args), ARRAY_A);
    if (!is_array($summary)) {
        $summary = array();
    }

    $last_schedule_update = isset($summary['last_schedule_update']) ? (string) $summary['last_schedule_update'] : '';
    $last_result_update = isset($summary['last_result_update']) ? (string) $summary['last_result_update'] : '';
    $public_data_updated_at = max($last_schedule_update, $last_result_update);

    return array_merge($empty, array(
        'schedule_version' => $schedule_version,
        'total_games' => isset($summary['total_games']) ? (int) $summary['total_games'] : 0,
        'reported_results' => isset($summary['reported_results']) ? (int) $summary['reported_results'] : 0,
        'late_missing' => isset($summary['late_missing']) ? (int) $summary['late_missing'] : 0,
        'attention' => isset($summary['attention']) ? (int) $summary['attention'] : 0,
        'missing_scans' => count(vaysf_get_results_desk_rows('missing_scans', array_merge($filters, array('limit' => 200)))),
        'recent_corrections' => count(vaysf_get_results_desk_rows('recent_corrections', array_merge($filters, array('limit' => 200)))),
        'complete_pools' => count(vaysf_get_results_desk_rows('complete_pools', array_merge($filters, array('limit' => 200)))),
        'last_schedule_update' => $last_schedule_update,
        'last_result_update' => $last_result_update,
        'public_data_updated_at' => $public_data_updated_at,
    ));
}

/**
 * Format a Results Desk timestamp for display.
 *
 * @param string $mysql_datetime MySQL datetime
 * @return string
 */
function vaysf_format_results_desk_datetime($mysql_datetime) {
    $mysql_datetime = trim((string) $mysql_datetime);
    if ($mysql_datetime === '') {
        return '-';
    }

    $timestamp = strtotime($mysql_datetime);
    if (!$timestamp) {
        return $mysql_datetime;
    }

    return date_i18n('D M j, g:i A', $timestamp);
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
                <div class="vaysf-results-desk-card"><strong><?php echo esc_html($summary['complete_pools']); ?></strong><span><?php esc_html_e('Complete pools', 'vaysf'); ?></span></div>
            </div>

            <div class="vaysf-results-desk-heartbeat">
                <div><strong><?php esc_html_e('Schedule version:', 'vaysf'); ?></strong> <?php echo esc_html($summary['schedule_version'] ?: '-'); ?></div>
                <div><strong><?php esc_html_e('Public data updated:', 'vaysf'); ?></strong> <?php echo esc_html(vaysf_format_results_desk_datetime($summary['public_data_updated_at'])); ?></div>
                <div><strong><?php esc_html_e('Server time:', 'vaysf'); ?></strong> <?php echo esc_html(vaysf_format_results_desk_datetime($summary['server_time'])); ?></div>
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
                <h2><?php esc_html_e('Complete Pools Ready For Human Review', 'vaysf'); ?></h2>
                <p><?php esc_html_e('Pools where every published pool/prelim game has a score payload. This does not auto-confirm advancement.', 'vaysf'); ?></p>
                <?php $complete_pools = vaysf_get_results_desk_rows('complete_pools', $filters); ?>
                <?php if (!$complete_pools) : ?>
                    <div class="vaysf-results-desk-ok"><?php esc_html_e('No complete pools are waiting in this filter.', 'vaysf'); ?></div>
                <?php else : ?>
                    <table class="vaysf-results-desk-table">
                        <thead>
                            <tr>
                                <th><?php esc_html_e('Event', 'vaysf'); ?></th>
                                <th><?php esc_html_e('Stage / Pool', 'vaysf'); ?></th>
                                <th><?php esc_html_e('Games', 'vaysf'); ?></th>
                                <th><?php esc_html_e('Last Updated', 'vaysf'); ?></th>
                            </tr>
                        </thead>
                        <tbody>
                            <?php foreach ($complete_pools as $pool) : ?>
                                <tr>
                                    <td><?php echo esc_html($pool['event']); ?></td>
                                    <td><?php echo esc_html(trim(($pool['stage'] ?? '') . ' ' . ($pool['pool_id'] ?? ''))); ?></td>
                                    <td><?php echo esc_html($pool['game_count']); ?></td>
                                    <td><?php echo esc_html(vaysf_format_results_desk_datetime($pool['last_updated_at'] ?? '')); ?></td>
                                </tr>
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
        <li><strong><?php echo esc_html($summary['complete_pools']); ?></strong> <?php esc_html_e('complete pools ready for human review', 'vaysf'); ?></li>
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

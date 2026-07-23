<?php
/**
 * File: includes/results-desk/actions.php
 * Description: Results Desk admin-post and download handlers.
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

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
 * wp_die-ing on ordinary failures (unresolved tie, incomplete pool) â€” those
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

    if (!vaysf_user_can_confirm_pool_review()) {
        wp_die(esc_html__('You are not authorized to confirm pool advancement.', 'vaysf'), 403);
    }

    $event = isset($_POST['event']) ? sanitize_text_field(wp_unslash($_POST['event'])) : '';
    $pool_id = isset($_POST['pool_id']) ? sanitize_text_field(wp_unslash($_POST['pool_id'])) : '';

    // Results Desk roles (sf2025_write/admin) implicitly cover every event;
    // a coordinator (no Results Desk access) is restricted to their own
    // authorized events — the same scoping already used for QF Apply — so a
    // Volleyball-only coordinator can't confirm Basketball's pool review just
    // by guessing the right POST fields.
    if (!vaysf_user_can_view_results_desk() && !in_array($event, vaysf_get_user_score_entry_events(get_current_user_id()), true)) {
        wp_die(esc_html__('You are not authorized to confirm pool advancement for this event.', 'vaysf'), 403);
    }

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
 * admin-post handler for "Confirm All Pools for QF Seeding" (Issue #329) â€”
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

    $event = isset($_POST['event']) ? sanitize_text_field(wp_unslash($_POST['event'])) : '';
    $schedule_version = isset($_POST['schedule_version']) ? absint($_POST['schedule_version']) : 0;

    if (!vaysf_user_can_confirm_event_qf_seeding($event)) {
        wp_die(esc_html__('You are not authorized to confirm QF seeding for this event.', 'vaysf'), 403);
    }

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
 * admin-post handler for one coin-toss flip (Issue #329) â€” see
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

    $event = isset($_POST['event']) ? sanitize_text_field(wp_unslash($_POST['event'])) : '';
    $schedule_version = isset($_POST['schedule_version']) ? absint($_POST['schedule_version']) : 0;
    $team_a_key = isset($_POST['team_a_key']) ? sanitize_text_field(wp_unslash($_POST['team_a_key'])) : '';
    $team_b_key = isset($_POST['team_b_key']) ? sanitize_text_field(wp_unslash($_POST['team_b_key'])) : '';

    if (!vaysf_user_can_confirm_event_qf_seeding($event)) {
        wp_die(esc_html__('You are not authorized to flip a coin toss for this event.', 'vaysf'), 403);
    }

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
 * `game_status = 'scheduled'`, i.e. NOT protected â€” a later schedule publish
 * that targets the same game_keys can still silently overwrite what this
 * writes.
 *
 * @param string $event
 * @param int $schedule_version
 * @param array<string,array<int,string>> $arrangement game_key => 3 team_keys
 * @return array<int,array<string,mixed>>|WP_Error Per-row outcomes on success
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
    // authorized events â€” the same scoping already used for score
    // submission â€” so a Volleyball-only coordinator can't Apply Basketball's
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

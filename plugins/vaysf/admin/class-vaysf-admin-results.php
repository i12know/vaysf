<?php
/**
 * File: admin/class-vaysf-admin-results.php
 * Description: Results admin page - corrections with revision history,
 *              verify/certify actions (Issues #203/#229)
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_Admin_Results extends VAYSF_Admin_Page {

    private function result_payload_from_post() {
        return array(
            'schedule_id' => isset($_POST['schedule_id']) ? absint($_POST['schedule_id']) : 0,
            'score_json' => isset($_POST['score_json']) ? wp_unslash($_POST['score_json']) : '',
            'winner_keys_json' => isset($_POST['winner_keys_json']) ? wp_unslash($_POST['winner_keys_json']) : '',
            'correction_reason' => isset($_POST['correction_reason']) ? sanitize_textarea_field(wp_unslash($_POST['correction_reason'])) : '',
            'public_status' => isset($_POST['public_status']) ? sanitize_text_field(wp_unslash($_POST['public_status'])) : 'pending',
            'scan_status' => isset($_POST['scan_status']) ? sanitize_text_field(wp_unslash($_POST['scan_status'])) : 'pending',
            'notes' => isset($_POST['notes']) ? sanitize_textarea_field(wp_unslash($_POST['notes'])) : '',
            'verification_state' => isset($_POST['verification_state']) ? sanitize_text_field(wp_unslash($_POST['verification_state'])) : 'unverified',
        );
    }

    /**
     * A blank value is allowed (score_json/winner_keys_json are nullable and
     * legitimately empty before a result is submitted); a non-blank value must
     * be valid JSON so sf_results never persists a string a downstream reader
     * (public display, middleware) would fail to json_decode().
     */
    private function validate_json_field($value, $label) {
        $value = trim((string) $value);
        if ($value === '') {
            return null;
        }
        json_decode($value);
        if (json_last_error() !== JSON_ERROR_NONE) {
            return new WP_Error(
                'vaysf_result_invalid_json',
                sprintf('%s must be valid JSON: %s', $label, json_last_error_msg())
            );
        }
        return null;
    }

    private function save_result_correction_from_post($result_id = 0) {
        global $wpdb;

        if (!current_user_can('sf2025_admin')) {
            return new WP_Error('vaysf_forbidden', 'You are not allowed to modify results.');
        }

        $table_results = vaysf_get_table_name('results');
        $table_revisions = vaysf_get_table_name('result_revisions');
        $table_schedules = vaysf_get_table_name('schedules');
        $payload = $this->result_payload_from_post();
        $result_id = absint($result_id);

        if (!$payload['schedule_id']) {
            return new WP_Error('vaysf_result_schedule_required', 'Schedule row is required.');
        }
        if (!in_array($payload['public_status'], $this->public_status_options(), true)) {
            return new WP_Error('vaysf_result_public_status', 'Invalid public status.');
        }
        if (!in_array($payload['scan_status'], $this->scan_status_options(), true)) {
            return new WP_Error('vaysf_result_scan_status', 'Invalid scan status.');
        }
        if (!in_array($payload['verification_state'], $this->revision_state_options(), true)) {
            return new WP_Error('vaysf_result_revision_state', 'Invalid revision state.');
        }

        foreach (array('score_json' => 'Score JSON', 'winner_keys_json' => 'Winner Keys JSON') as $json_field => $json_label) {
            $json_error = $this->validate_json_field($payload[$json_field], $json_label);
            if (is_wp_error($json_error)) {
                return $json_error;
            }
        }

        $schedule_exists = $wpdb->get_var(
            $wpdb->prepare("SELECT COUNT(*) FROM $table_schedules WHERE schedule_id = %d", $payload['schedule_id'])
        );
        if (!$schedule_exists) {
            return new WP_Error('vaysf_result_schedule_missing', 'Schedule row not found.');
        }

        $existing = null;
        if ($result_id) {
            $existing = $wpdb->get_row(
                $wpdb->prepare("SELECT * FROM $table_results WHERE result_id = %d", $result_id),
                ARRAY_A
            );
            if (!$existing) {
                return new WP_Error('vaysf_result_missing', 'Result row not found.');
            }
        } else {
            $existing = $wpdb->get_row(
                $wpdb->prepare("SELECT * FROM $table_results WHERE schedule_id = %d", $payload['schedule_id']),
                ARRAY_A
            );
            if ($existing) {
                return new WP_Error('vaysf_result_duplicate', 'A result already exists for this schedule row. Edit the existing result instead.');
            }
        }

        $now = current_time('mysql');
        $user_id = get_current_user_id();
        $wpdb->query('START TRANSACTION');

        if ($existing) {
            $result_id = absint($existing['result_id']);
            $next_revision = absint($existing['current_revision']) + 1;
        } else {
            $inserted = $wpdb->insert(
                $table_results,
                array(
                    'schedule_id' => $payload['schedule_id'],
                    'score_json' => $payload['score_json'],
                    'winner_keys_json' => $payload['winner_keys_json'],
                    'submitted_by_user_id' => $user_id,
                    'current_revision' => 0,
                    'correction_reason' => $payload['correction_reason'],
                    'public_status' => $payload['public_status'],
                    'scan_status' => $payload['scan_status'],
                    'notes' => $payload['notes'],
                    'created_at' => $now,
                    'updated_at' => $now,
                ),
                array('%d', '%s', '%s', '%d', '%d', '%s', '%s', '%s', '%s', '%s', '%s')
            );
            if ($inserted === false) {
                $wpdb->query('ROLLBACK');
                return new WP_Error('vaysf_result_create_failed', 'Could not create result row.');
            }
            $result_id = absint($wpdb->insert_id);
            $next_revision = 1;
        }

        $revision_inserted = $wpdb->insert(
            $table_revisions,
            array(
                'result_id' => $result_id,
                'revision_number' => $next_revision,
                'score_json' => $payload['score_json'],
                'winner_keys_json' => $payload['winner_keys_json'],
                'notes' => $payload['notes'],
                'correction_reason' => $payload['correction_reason'],
                'submitted_by_user_id' => $user_id,
                'submitted_at' => $now,
                'verification_state' => $payload['verification_state'],
                'source_ip' => isset($_SERVER['REMOTE_ADDR']) ? sanitize_text_field(wp_unslash($_SERVER['REMOTE_ADDR'])) : '',
                'request_metadata' => wp_json_encode(array('source' => 'wp-admin', 'user_id' => $user_id)),
            ),
            array('%d', '%d', '%s', '%s', '%s', '%s', '%d', '%s', '%s', '%s', '%s')
        );

        if ($revision_inserted === false) {
            $wpdb->query('ROLLBACK');
            return new WP_Error('vaysf_revision_create_failed', 'Could not append result revision.');
        }

        $updated = $wpdb->update(
            $table_results,
            array(
                'schedule_id' => $payload['schedule_id'],
                'score_json' => $payload['score_json'],
                'winner_keys_json' => $payload['winner_keys_json'],
                'submitted_by_user_id' => $user_id,
                'current_revision' => $next_revision,
                'correction_reason' => $payload['correction_reason'],
                'public_status' => $payload['public_status'],
                'scan_status' => $payload['scan_status'],
                'notes' => $payload['notes'],
                'updated_at' => $now,
            ),
            array('result_id' => $result_id),
            array('%d', '%s', '%s', '%d', '%d', '%s', '%s', '%s', '%s', '%s'),
            array('%d')
        );

        if ($updated === false) {
            $wpdb->query('ROLLBACK');
            return new WP_Error('vaysf_result_update_failed', 'Could not update current result row.');
        }

        $wpdb->query('COMMIT');
        return true;
    }

    private function verify_result_from_post($result_id, $mode) {
        global $wpdb;

        if (!current_user_can('sf2025_admin')) {
            return new WP_Error('vaysf_forbidden', 'You are not allowed to verify results.');
        }

        $data = array('updated_at' => current_time('mysql'));
        $formats = array('%s');
        if ($mode === 'verify') {
            $data['verified_by_user_id'] = get_current_user_id();
            $data['verified_at'] = current_time('mysql');
            $formats[] = '%d';
            $formats[] = '%s';
        } elseif ($mode === 'certify') {
            $data['certified_at'] = current_time('mysql');
            $formats[] = '%s';
        } else {
            return new WP_Error('vaysf_bad_result_action', 'Invalid result action.');
        }

        $updated = $wpdb->update(
            vaysf_get_table_name('results'),
            $data,
            array('result_id' => absint($result_id)),
            $formats,
            array('%d')
        );

        if ($updated === false) {
            return new WP_Error('vaysf_result_verify_failed', 'Could not update result verification state.');
        }

        return true;
    }

    private function render_result_form($result = array()) {
        global $wpdb;

        $result_id = isset($result['result_id']) ? absint($result['result_id']) : 0;
        $action = $result_id ? 'save_result' : 'create_result';
        $nonce_action = $action . '_' . $result_id;
        $schedules = $wpdb->get_results(
            "SELECT schedule_id, game_key, event, team_a_label, team_b_label, team_c_label FROM " . vaysf_get_table_name('schedules') . " ORDER BY schedule_version DESC, game_key LIMIT 500",
            ARRAY_A
        );
        ?>
        <form method="post" class="vaysf-admin-form">
            <?php wp_nonce_field($nonce_action); ?>
            <input type="hidden" name="vaysf_action" value="<?php echo esc_attr($action); ?>">
            <input type="hidden" name="result_id" value="<?php echo esc_attr($result_id); ?>">
            <table class="form-table" role="presentation">
                <tr>
                    <th><label for="schedule_id">Schedule Row</label></th>
                    <td>
                        <select name="schedule_id" id="schedule_id" required>
                            <option value="">Choose a game</option>
                            <?php foreach ($schedules as $schedule) : ?>
                                <?php $label = $schedule['game_key'] . ' - ' . $schedule['event'] . ' - ' . $this->format_game_teams($schedule); ?>
                                <option value="<?php echo esc_attr($schedule['schedule_id']); ?>" <?php selected($result['schedule_id'] ?? '', $schedule['schedule_id']); ?>><?php echo esc_html($label); ?></option>
                            <?php endforeach; ?>
                        </select>
                    </td>
                </tr>
                <tr>
                    <th><label for="score_json">Score JSON</label></th>
                    <td><textarea name="score_json" id="score_json" rows="5" class="large-text code"><?php echo esc_textarea($this->textarea_json_value($result['score_json'] ?? '')); ?></textarea></td>
                </tr>
                <tr>
                    <th><label for="winner_keys_json">Winner Keys JSON</label></th>
                    <td><textarea name="winner_keys_json" id="winner_keys_json" rows="3" class="large-text code"><?php echo esc_textarea($this->textarea_json_value($result['winner_keys_json'] ?? '')); ?></textarea></td>
                </tr>
                <tr>
                    <th>Status</th>
                    <td>
                        <select name="public_status">
                            <?php foreach ($this->public_status_options() as $status) : ?>
                                <option value="<?php echo esc_attr($status); ?>" <?php selected($result['public_status'] ?? 'pending', $status); ?>><?php echo esc_html($status); ?></option>
                            <?php endforeach; ?>
                        </select>
                        <select name="scan_status">
                            <?php foreach ($this->scan_status_options() as $status) : ?>
                                <option value="<?php echo esc_attr($status); ?>" <?php selected($result['scan_status'] ?? 'pending', $status); ?>><?php echo esc_html($status); ?></option>
                            <?php endforeach; ?>
                        </select>
                        <select name="verification_state">
                            <?php foreach ($this->revision_state_options() as $state) : ?>
                                <option value="<?php echo esc_attr($state); ?>"><?php echo esc_html($state); ?></option>
                            <?php endforeach; ?>
                        </select>
                    </td>
                </tr>
                <tr>
                    <th><label for="correction_reason">Correction Reason</label></th>
                    <td><textarea name="correction_reason" id="correction_reason" rows="3" class="large-text"><?php echo esc_textarea($result['correction_reason'] ?? ''); ?></textarea></td>
                </tr>
                <tr>
                    <th><label for="notes">Notes</label></th>
                    <td><textarea name="notes" id="notes" rows="3" class="large-text"><?php echo esc_textarea($result['notes'] ?? ''); ?></textarea></td>
                </tr>
            </table>
            <?php submit_button($result_id ? 'Save Correction' : 'Create Result'); ?>
        </form>
        <?php
    }

    /**
     * Display event-day results and revision history admin page.
     */
    public function display_results_page() {
        global $wpdb;

        $table_results = vaysf_get_table_name('results');
        $table_schedules = vaysf_get_table_name('schedules');
        $table_revisions = vaysf_get_table_name('result_revisions');
        $table_files = vaysf_get_table_name('result_files');
        $vaysf_action = isset($_POST['vaysf_action']) ? sanitize_text_field(wp_unslash($_POST['vaysf_action'])) : '';
        $result_id = isset($_POST['result_id'])
            ? absint($_POST['result_id'])
            : (isset($_REQUEST['id']) ? absint($_REQUEST['id']) : 0);

        if ($vaysf_action === 'save_result' || $vaysf_action === 'create_result') {
            $nonce_action = $vaysf_action . '_' . $result_id;
            if (!isset($_POST['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'])), $nonce_action)) {
                $this->print_admin_notice(new WP_Error('vaysf_bad_nonce', 'Invalid result request.'), '');
            } else {
                $this->print_admin_notice($this->save_result_correction_from_post($result_id), $result_id ? 'Result correction saved and revision appended.' : 'Result created and revision appended.');
            }
        } elseif ($vaysf_action === 'verify_result' || $vaysf_action === 'certify_result') {
            $mode = $vaysf_action === 'verify_result' ? 'verify' : 'certify';
            if (!isset($_POST['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'])), $vaysf_action . '_' . $result_id)) {
                $this->print_admin_notice(new WP_Error('vaysf_bad_nonce', 'Invalid verification request.'), '');
            } else {
                $this->print_admin_notice($this->verify_result_from_post($result_id, $mode), ucfirst($mode) . ' action saved.');
            }
        }

        $action = isset($_GET['action']) ? sanitize_text_field(wp_unslash($_GET['action'])) : '';
        if ($action === 'new' || ($action === 'edit' && $result_id)) {
            $result = array();
            if ($result_id) {
                $result = $wpdb->get_row(
                    $wpdb->prepare("SELECT * FROM $table_results WHERE result_id = %d", $result_id),
                    ARRAY_A
                );
            }
            ?>
            <div class="wrap">
                <h1><?php echo $result_id ? 'Edit Result' : 'Create Result'; ?></h1>
                <p><a class="button" href="<?php echo esc_url(admin_url('admin.php?page=vaysf-results')); ?>">Back to Results</a></p>
                <?php
                if ($result_id && !$result) {
                    echo '<div class="notice notice-error"><p>Result row not found.</p></div>';
                } else {
                    $this->render_result_form($result);
                }
                ?>
            </div>
            <?php
            return;
        }

        if ($action === 'revisions' && $result_id) {
            $result = $wpdb->get_row(
                $wpdb->prepare(
                    "SELECT r.*, s.game_key, s.event FROM $table_results r LEFT JOIN $table_schedules s ON r.schedule_id = s.schedule_id WHERE r.result_id = %d",
                    $result_id
                ),
                ARRAY_A
            );
            $revisions = $wpdb->get_results(
                $wpdb->prepare("SELECT * FROM $table_revisions WHERE result_id = %d ORDER BY revision_number DESC", $result_id),
                ARRAY_A
            );
            $files = $wpdb->get_results(
                $wpdb->prepare(
                    "SELECT f.*, rr.revision_id, rr.revision_number
                    FROM $table_files f
                    INNER JOIN $table_revisions rr ON rr.revision_id = f.result_revision_id
                    WHERE rr.result_id = %d
                    ORDER BY rr.revision_number DESC, f.uploaded_at DESC",
                    $result_id
                ),
                ARRAY_A
            );
            $files_by_revision = array();
            if (is_array($files)) {
                foreach ($files as $file) {
                    $revision_key = absint($file['revision_id']);
                    if (!isset($files_by_revision[$revision_key])) {
                        $files_by_revision[$revision_key] = array();
                    }
                    $files_by_revision[$revision_key][] = $file;
                }
            }
            ?>
            <div class="wrap">
                <h1>Result Revision History</h1>
                <p><a class="button" href="<?php echo esc_url(admin_url('admin.php?page=vaysf-results')); ?>">Back to Results</a></p>
                <?php if (!$result) : ?>
                    <div class="notice notice-error"><p>Result row not found.</p></div>
                <?php else : ?>
                    <h2><?php echo esc_html($result['game_key'] . ' - ' . $result['event']); ?></h2>
                    <table class="wp-list-table widefat fixed striped">
                        <thead>
                            <tr>
                                <th>Revision</th>
                                <th>Score</th>
                                <th>Winner Keys</th>
                                <th>State</th>
                                <th>Reason / Notes</th>
                                <th>Files</th>
                                <th>Submitted</th>
                            </tr>
                        </thead>
                        <tbody>
                            <?php if (!$revisions) : ?>
                                <tr><td colspan="7">No revisions found.</td></tr>
                            <?php else : ?>
                                <?php foreach ($revisions as $revision) : ?>
                                    <tr>
                                        <td><?php echo esc_html($revision['revision_number']); ?></td>
                                        <td><pre><?php echo esc_html($revision['score_json']); ?></pre></td>
                                        <td><pre><?php echo esc_html($revision['winner_keys_json']); ?></pre></td>
                                        <td><?php echo esc_html($revision['verification_state']); ?></td>
                                        <td><?php echo esc_html($revision['correction_reason']); ?><br><small><?php echo esc_html($revision['notes']); ?></small></td>
                                        <td>
                                            <?php $revision_files = $files_by_revision[absint($revision['revision_id'])] ?? array(); ?>
                                            <?php if (!$revision_files) : ?>
                                                -
                                            <?php else : ?>
                                                <?php foreach ($revision_files as $file) : ?>
                                                    <div>
                                                        <?php echo esc_html($file['original_filename']); ?><br>
                                                        <small><?php echo esc_html(size_format(absint($file['byte_size']))); ?></small>
                                                        <a href="<?php echo esc_url(vaysf_get_result_file_view_url($file['file_id'])); ?>" target="_blank" rel="noopener noreferrer">View</a>
                                                        |
                                                        <a href="<?php echo esc_url(vaysf_get_result_file_download_url($file['file_id'])); ?>">Download</a>
                                                    </div>
                                                <?php endforeach; ?>
                                            <?php endif; ?>
                                        </td>
                                        <td><?php echo esc_html($revision['submitted_at']); ?><br><small>User <?php echo esc_html($revision['submitted_by_user_id']); ?></small></td>
                                    </tr>
                                <?php endforeach; ?>
                            <?php endif; ?>
                        </tbody>
                    </table>
                <?php endif; ?>
            </div>
            <?php
            return;
        }

        $public_filter = isset($_GET['public_status']) ? sanitize_text_field(wp_unslash($_GET['public_status'])) : '';
        $event_filter = isset($_GET['event']) ? sanitize_text_field(wp_unslash($_GET['event'])) : '';
        $where = array();
        $args = array();
        if ($public_filter !== '') {
            $where[] = 'r.public_status = %s';
            $args[] = $public_filter;
        }
        if ($event_filter !== '') {
            $where[] = 's.event = %s';
            $args[] = $event_filter;
        }
        $where_clause = $where ? 'WHERE ' . implode(' AND ', $where) : '';
        $query_sql = "SELECT r.*, s.game_key, s.event, s.stage, s.team_a_label, s.team_b_label, s.team_c_label FROM $table_results r LEFT JOIN $table_schedules s ON r.schedule_id = s.schedule_id $where_clause ORDER BY r.updated_at DESC, r.result_id DESC LIMIT 200";
        $results = $args ? $wpdb->get_results($wpdb->prepare($query_sql, $args), ARRAY_A) : $wpdb->get_results($query_sql, ARRAY_A);
        $events = $wpdb->get_col("SELECT DISTINCT event FROM $table_schedules WHERE event IS NOT NULL AND event <> '' ORDER BY event");
        ?>
        <div class="wrap">
            <h1>Results <a href="<?php echo esc_url(admin_url('admin.php?page=vaysf-results&action=new')); ?>" class="page-title-action">Add New</a></h1>
            <form method="get" class="tablenav top">
                <input type="hidden" name="page" value="vaysf-results">
                <select name="event">
                    <option value="">All events</option>
                    <?php foreach ($events as $event) : ?>
                        <option value="<?php echo esc_attr($event); ?>" <?php selected($event_filter, $event); ?>><?php echo esc_html($event); ?></option>
                    <?php endforeach; ?>
                </select>
                <select name="public_status">
                    <option value="">All statuses</option>
                    <?php foreach ($this->public_status_options() as $status) : ?>
                        <option value="<?php echo esc_attr($status); ?>" <?php selected($public_filter, $status); ?>><?php echo esc_html($status); ?></option>
                    <?php endforeach; ?>
                </select>
                <input type="submit" class="button" value="Filter">
            </form>
            <table class="wp-list-table widefat fixed striped">
                <thead>
                    <tr>
                        <th>Game</th>
                        <th>Teams</th>
                        <th>Status</th>
                        <th>Revision</th>
                        <th>Certified / Verified</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    <?php if (!$results) : ?>
                        <tr><td colspan="6">No results found.</td></tr>
                    <?php else : ?>
                        <?php foreach ($results as $result) : ?>
                            <tr>
                                <td><strong><?php echo esc_html($result['game_key']); ?></strong><br><small><?php echo esc_html($result['event']); ?></small></td>
                                <td><?php echo esc_html($this->format_game_teams($result)); ?></td>
                                <td><?php echo esc_html($result['public_status']); ?><br><small>Scan: <?php echo esc_html($result['scan_status']); ?></small></td>
                                <td><?php echo esc_html($result['current_revision']); ?></td>
                                <td><?php echo esc_html($result['certified_at'] ?: '-'); ?><br><small><?php echo esc_html($result['verified_at'] ?: '-'); ?></small></td>
                                <td>
                                    <a class="button button-small" href="<?php echo esc_url(admin_url('admin.php?page=vaysf-results&action=edit&id=' . $result['result_id'])); ?>">Correct</a>
                                    <a class="button button-small" href="<?php echo esc_url(admin_url('admin.php?page=vaysf-results&action=revisions&id=' . $result['result_id'])); ?>">Revisions</a>
                                    <form method="post" style="display:inline;">
                                        <?php wp_nonce_field('certify_result_' . $result['result_id']); ?>
                                        <input type="hidden" name="vaysf_action" value="certify_result">
                                        <input type="hidden" name="id" value="<?php echo esc_attr($result['result_id']); ?>">
                                        <button class="button button-small" type="submit">Certify</button>
                                    </form>
                                    <form method="post" style="display:inline;">
                                        <?php wp_nonce_field('verify_result_' . $result['result_id']); ?>
                                        <input type="hidden" name="vaysf_action" value="verify_result">
                                        <input type="hidden" name="id" value="<?php echo esc_attr($result['result_id']); ?>">
                                        <button class="button button-small" type="submit">Verify</button>
                                    </form>
                                </td>
                            </tr>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </tbody>
            </table>
        </div>
        <?php
    }
}

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
        ?>
        <div class="wrap">
            <h1>Schedules <a href="<?php echo esc_url(admin_url('admin.php?page=vaysf-schedules&action=new')); ?>" class="page-title-action">Add New</a></h1>
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

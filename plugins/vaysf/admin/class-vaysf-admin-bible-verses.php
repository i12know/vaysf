<?php
/**
 * File: admin/class-vaysf-admin-bible-verses.php
 * Description: Scoped Bible verse editor backed by a WordPress option.
 * Author: Bumble Ho
 */

if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_Admin_Bible_Verses extends VAYSF_Admin_Page {

    private function handle_actions($allowed_events) {
        if (!current_user_can(VAYSF_BIBLE_VERSE_CAPABILITY)) {
            return null;
        }

        if (empty($_POST['vaysf_bible_verse_action'])) {
            return null;
        }

        $action = sanitize_key(wp_unslash($_POST['vaysf_bible_verse_action']));
        if (
            empty($_POST['vaysf_bible_verse_nonce'])
            || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['vaysf_bible_verse_nonce'])), 'vaysf_bible_verse_editor')
        ) {
            return new WP_Error('vaysf_bible_verse_bad_nonce', __('Security check failed.', 'vaysf'));
        }

        if ($action === 'save') {
            $row_id = isset($_POST['row_id']) ? sanitize_key(wp_unslash($_POST['row_id'])) : '';
            return vaysf_save_bible_verse_row($_POST, $row_id);
        }

        if ($action === 'deactivate') {
            $row_id = isset($_POST['row_id']) ? sanitize_key(wp_unslash($_POST['row_id'])) : '';
            return vaysf_deactivate_bible_verse_row($row_id);
        }

        if ($action === 'delete') {
            $row_id = isset($_POST['row_id']) ? sanitize_key(wp_unslash($_POST['row_id'])) : '';
            return vaysf_delete_bible_verse_row($row_id);
        }

        if ($action === 'import_json') {
            return $this->import_json($allowed_events);
        }

        return null;
    }

    private function import_json($allowed_events) {
        $json = isset($_POST['import_json']) ? trim((string) wp_unslash($_POST['import_json'])) : '';
        if ($json === '') {
            return new WP_Error('vaysf_bible_verse_import_empty', __('Paste JSON before importing.', 'vaysf'));
        }

        $payload = json_decode($json, true);
        if (!is_array($payload) || !isset($payload['verse_sets']) || !is_array($payload['verse_sets'])) {
            return new WP_Error('vaysf_bible_verse_import_bad_json', __('Import JSON must contain a verse_sets array.', 'vaysf'));
        }

        $allowed_lookup = array_fill_keys($allowed_events, true);
        $existing_rows = vaysf_get_bible_verse_rows();
        $kept_rows = array_values(array_filter($existing_rows, function ($row) use ($allowed_lookup) {
            return empty($row['event']) || !isset($allowed_lookup[$row['event']]);
        }));

        $imported_rows = array();
        foreach ($payload['verse_sets'] as $index => $raw_row) {
            if (!is_array($raw_row)) {
                return new WP_Error('vaysf_bible_verse_import_row', sprintf(__('Import row %d must be an object.', 'vaysf'), $index + 1));
            }
            $event = isset($raw_row['event']) ? sanitize_text_field((string) $raw_row['event']) : '';
            if ($event === '' || !isset($allowed_lookup[$event])) {
                continue;
            }
            $row = vaysf_sanitize_bible_verse_payload($raw_row, null);
            $validation = vaysf_validate_bible_verse_row($row, array_merge($kept_rows, $imported_rows));
            if (is_wp_error($validation)) {
                return $validation;
            }
            $imported_rows[] = $row;
        }

        vaysf_update_bible_verse_rows(array_merge($kept_rows, $imported_rows));
        return count($imported_rows);
    }

    private function selected_event($allowed_events) {
        $requested = isset($_GET['event']) ? sanitize_text_field(wp_unslash($_GET['event'])) : '';
        return in_array($requested, $allowed_events, true) ? $requested : '';
    }

    private function selected_edit_row($visible_rows) {
        $row_id = isset($_GET['edit']) ? sanitize_key(wp_unslash($_GET['edit'])) : '';
        if ($row_id === '') {
            return null;
        }
        foreach ($visible_rows as $row) {
            if (!empty($row['row_id']) && $row['row_id'] === $row_id) {
                return $row;
            }
        }
        return null;
    }

    private function row_value($row, $field, $default = '') {
        return isset($row[$field]) ? $row[$field] : $default;
    }

    public function display_bible_verses_page() {
        if (!current_user_can(VAYSF_BIBLE_VERSE_CAPABILITY)) {
            wp_die(esc_html__('You are not authorized to manage Bible verses.', 'vaysf'));
        }

        $allowed_events = vaysf_get_user_bible_verse_events(get_current_user_id());
        $action_result = $this->handle_actions($allowed_events);
        $selected_event = $this->selected_event($allowed_events);
        $all_rows = vaysf_get_bible_verse_rows();
        $visible_rows = vaysf_filter_bible_verse_rows_for_user($all_rows, get_current_user_id(), false);
        if ($selected_event !== '') {
            $visible_rows = array_values(array_filter($visible_rows, function ($row) use ($selected_event) {
                return (string) ($row['event'] ?? '') === $selected_event;
            }));
        }
        $edit_row = $this->selected_edit_row($visible_rows);
        $export_payload = vaysf_bible_verse_rows_to_export_payload($visible_rows);
        ?>
        <div class="wrap">
            <h1><?php esc_html_e('Bible Verse Editor', 'vaysf'); ?></h1>
            <?php
            if (is_wp_error($action_result)) {
                echo '<div class="notice notice-error"><p>' . esc_html($action_result->get_error_message()) . '</p></div>';
            } elseif ($action_result !== null) {
                $message = is_int($action_result)
                    ? sprintf(__('Imported %d verse row(s).', 'vaysf'), $action_result)
                    : __('Bible verse changes saved.', 'vaysf');
                echo '<div class="notice notice-success"><p>' . esc_html($message) . '</p></div>';
            }
            ?>
            <?php if (!$allowed_events) : ?>
                <div class="notice notice-warning">
                    <p><?php esc_html_e('No published schedule events are assigned to this account. Assign event authorization before editing verses.', 'vaysf'); ?></p>
                </div>
            <?php else : ?>
                <p class="description">
                    <?php esc_html_e('Access follows the Coordinator Score Entry event-scope model. Admins/managers see all published events; ordinary verse editors see only assigned events.', 'vaysf'); ?>
                </p>

                <form method="get" style="margin: 16px 0;">
                    <input type="hidden" name="page" value="vaysf-bible-verses">
                    <label for="vaysf-bible-verse-event-filter"><?php esc_html_e('Event filter', 'vaysf'); ?></label>
                    <select id="vaysf-bible-verse-event-filter" name="event">
                        <option value=""><?php esc_html_e('All authorized events', 'vaysf'); ?></option>
                        <?php foreach ($allowed_events as $event) : ?>
                            <option value="<?php echo esc_attr($event); ?>" <?php selected($selected_event, $event); ?>>
                                <?php echo esc_html($event); ?>
                            </option>
                        <?php endforeach; ?>
                    </select>
                    <button class="button"><?php esc_html_e('Filter', 'vaysf'); ?></button>
                </form>

                <?php $this->render_editor_form($edit_row, $allowed_events); ?>
                <?php $this->render_rows_table($visible_rows); ?>
                <?php $this->render_json_tools($export_payload); ?>
            <?php endif; ?>
        </div>
        <?php
    }

    private function render_editor_form($row, $allowed_events) {
        $is_edit = is_array($row);
        ?>
        <h2><?php echo esc_html($is_edit ? __('Edit Verse Row', 'vaysf') : __('Add Verse Row', 'vaysf')); ?></h2>
        <form method="post">
            <?php wp_nonce_field('vaysf_bible_verse_editor', 'vaysf_bible_verse_nonce'); ?>
            <input type="hidden" name="vaysf_bible_verse_action" value="save">
            <input type="hidden" name="row_id" value="<?php echo esc_attr($this->row_value($row, 'row_id')); ?>">
            <table class="form-table" role="presentation">
                <tr>
                    <th scope="row"><label for="set_key"><?php esc_html_e('Set key', 'vaysf'); ?></label></th>
                    <td><input name="set_key" id="set_key" class="regular-text" required value="<?php echo esc_attr($this->row_value($row, 'set_key', 'bc_2026')); ?>"></td>
                </tr>
                <tr>
                    <th scope="row"><label for="event"><?php esc_html_e('Event', 'vaysf'); ?></label></th>
                    <td>
                        <select name="event" id="event" required>
                            <?php foreach ($allowed_events as $event) : ?>
                                <option value="<?php echo esc_attr($event); ?>" <?php selected($this->row_value($row, 'event'), $event); ?>>
                                    <?php echo esc_html($event); ?>
                                </option>
                            <?php endforeach; ?>
                        </select>
                    </td>
                </tr>
                <tr>
                    <th scope="row"><label for="season"><?php esc_html_e('Season', 'vaysf'); ?></label></th>
                    <td><input name="season" id="season" type="number" min="2000" required value="<?php echo esc_attr($this->row_value($row, 'season', date_i18n('Y'))); ?>"></td>
                </tr>
                <tr>
                    <th scope="row"><label for="sort_order"><?php esc_html_e('Sort order', 'vaysf'); ?></label></th>
                    <td><input name="sort_order" id="sort_order" type="number" min="1" required value="<?php echo esc_attr($this->row_value($row, 'sort_order', 1)); ?>"></td>
                </tr>
                <tr>
                    <th scope="row"><label for="reference"><?php esc_html_e('Reference', 'vaysf'); ?></label></th>
                    <td><input name="reference" id="reference" class="regular-text" required value="<?php echo esc_attr($this->row_value($row, 'reference')); ?>"></td>
                </tr>
                <tr>
                    <th scope="row"><label for="verse_text"><?php esc_html_e('Verse text', 'vaysf'); ?></label></th>
                    <td><textarea name="verse_text" id="verse_text" class="large-text" rows="4" required><?php echo esc_textarea($this->row_value($row, 'verse_text')); ?></textarea></td>
                </tr>
                <tr>
                    <th scope="row"><label for="translation"><?php esc_html_e('Translation', 'vaysf'); ?></label></th>
                    <td><input name="translation" id="translation" class="regular-text" value="<?php echo esc_attr($this->row_value($row, 'translation')); ?>"></td>
                </tr>
                <tr>
                    <th scope="row"><?php esc_html_e('Flags', 'vaysf'); ?></th>
                    <td>
                        <label><input type="checkbox" name="active" value="1" <?php checked((int) $this->row_value($row, 'active', 1), 1); ?>> <?php esc_html_e('Active', 'vaysf'); ?></label><br>
                        <label><input type="checkbox" name="event_locked" value="1" <?php checked((int) $this->row_value($row, 'event_locked', 1), 1); ?>> <?php esc_html_e('Locked to this event', 'vaysf'); ?></label><br>
                        <label><input type="checkbox" name="general_pool" value="1" <?php checked((int) $this->row_value($row, 'general_pool', 0), 1); ?>> <?php esc_html_e('Reusable general-pool verse', 'vaysf'); ?></label>
                    </td>
                </tr>
                <tr>
                    <th scope="row"><label for="allowed_events"><?php esc_html_e('Allowed events', 'vaysf'); ?></label></th>
                    <td>
                        <select name="allowed_events[]" id="allowed_events" multiple size="5">
                            <?php $selected_allowed = vaysf_parse_bible_verse_allowed_events($this->row_value($row, 'allowed_events', array())); ?>
                            <?php foreach ($allowed_events as $event) : ?>
                                <option value="<?php echo esc_attr($event); ?>" <?php selected(in_array($event, $selected_allowed, true)); ?>>
                                    <?php echo esc_html($event); ?>
                                </option>
                            <?php endforeach; ?>
                        </select>
                        <p class="description"><?php esc_html_e('Locked rows automatically use only their own event.', 'vaysf'); ?></p>
                    </td>
                </tr>
            </table>
            <?php submit_button($is_edit ? __('Update Verse', 'vaysf') : __('Add Verse', 'vaysf')); ?>
        </form>
        <?php
    }

    private function render_rows_table($rows) {
        ?>
        <h2><?php esc_html_e('Verse Rows', 'vaysf'); ?></h2>
        <table class="widefat striped">
            <thead>
                <tr>
                    <th><?php esc_html_e('Set', 'vaysf'); ?></th>
                    <th><?php esc_html_e('Event', 'vaysf'); ?></th>
                    <th><?php esc_html_e('Order', 'vaysf'); ?></th>
                    <th><?php esc_html_e('Reference', 'vaysf'); ?></th>
                    <th><?php esc_html_e('Active', 'vaysf'); ?></th>
                    <th><?php esc_html_e('Scope', 'vaysf'); ?></th>
                    <th><?php esc_html_e('CRUD Actions', 'vaysf'); ?></th>
                </tr>
            </thead>
            <tbody>
                <?php if (!$rows) : ?>
                    <tr><td colspan="7"><?php esc_html_e('No verse rows are available for your authorized events.', 'vaysf'); ?></td></tr>
                <?php else : ?>
                    <?php foreach ($rows as $row) : ?>
                        <tr>
                            <td><?php echo esc_html($row['set_key'] ?? ''); ?></td>
                            <td><?php echo esc_html($row['event'] ?? ''); ?></td>
                            <td><?php echo esc_html($row['sort_order'] ?? ''); ?></td>
                            <td><?php echo esc_html($row['reference'] ?? ''); ?></td>
                            <td><?php echo !empty($row['active']) ? esc_html__('Yes', 'vaysf') : esc_html__('No', 'vaysf'); ?></td>
                            <td><?php echo !empty($row['event_locked']) ? esc_html__('Event locked', 'vaysf') : esc_html__('Reusable', 'vaysf'); ?></td>
                            <td>
                                <a class="button button-small" href="<?php echo esc_url(add_query_arg(array('page' => 'vaysf-bible-verses', 'edit' => $row['row_id'] ?? ''), admin_url('admin.php'))); ?>"><?php esc_html_e('Edit', 'vaysf'); ?></a>
                                <?php if (!empty($row['active'])) : ?>
                                    <form method="post" style="display:inline;">
                                        <?php wp_nonce_field('vaysf_bible_verse_editor', 'vaysf_bible_verse_nonce'); ?>
                                        <input type="hidden" name="vaysf_bible_verse_action" value="deactivate">
                                        <input type="hidden" name="row_id" value="<?php echo esc_attr($row['row_id'] ?? ''); ?>">
                                        <button class="button button-small"><?php esc_html_e('Deactivate', 'vaysf'); ?></button>
                                    </form>
                                <?php endif; ?>
                                <form method="post" style="display:inline;" onsubmit="return confirm('<?php echo esc_js(__('Delete this verse row permanently? No revision history is kept.', 'vaysf')); ?>');">
                                    <?php wp_nonce_field('vaysf_bible_verse_editor', 'vaysf_bible_verse_nonce'); ?>
                                    <input type="hidden" name="vaysf_bible_verse_action" value="delete">
                                    <input type="hidden" name="row_id" value="<?php echo esc_attr($row['row_id'] ?? ''); ?>">
                                    <button class="button button-small button-link-delete"><?php esc_html_e('Delete', 'vaysf'); ?></button>
                                </form>
                            </td>
                        </tr>
                    <?php endforeach; ?>
                <?php endif; ?>
            </tbody>
        </table>
        <?php
    }

    private function render_json_tools($export_payload) {
        ?>
        <h2><?php esc_html_e('Middleware JSON', 'vaysf'); ?></h2>
        <p class="description"><?php esc_html_e('Export is compatible with middleware/config/bible_verse_sets.json. Import replaces rows only for events this account is authorized to manage.', 'vaysf'); ?></p>
        <textarea class="large-text code" rows="10" readonly><?php echo esc_textarea(wp_json_encode($export_payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)); ?></textarea>

        <h3><?php esc_html_e('Import JSON', 'vaysf'); ?></h3>
        <form method="post">
            <?php wp_nonce_field('vaysf_bible_verse_editor', 'vaysf_bible_verse_nonce'); ?>
            <input type="hidden" name="vaysf_bible_verse_action" value="import_json">
            <textarea name="import_json" class="large-text code" rows="8" placeholder="<?php esc_attr_e('Paste JSON with a verse_sets array', 'vaysf'); ?>"></textarea>
            <?php submit_button(__('Import Authorized Rows', 'vaysf'), 'secondary'); ?>
        </form>
        <?php
    }
}

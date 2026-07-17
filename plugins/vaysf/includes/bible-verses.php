<?php
/**
 * File: includes/bible-verses.php
 * Description: Option-backed, event-scoped Bible verse editor helpers.
 * Author: Bumble Ho
 */

if (!defined('ABSPATH')) {
    exit;
}

if (!defined('VAYSF_BIBLE_VERSE_CAPABILITY')) {
    define('VAYSF_BIBLE_VERSE_CAPABILITY', 'sf2025_manage_bible_verses');
}

if (!defined('VAYSF_BIBLE_VERSE_OPTION')) {
    define('VAYSF_BIBLE_VERSE_OPTION', 'vaysf_bible_verse_sets');
}

if (!defined('VAYSF_BIBLE_VERSE_SEEDED_OPTION')) {
    define('VAYSF_BIBLE_VERSE_SEEDED_OPTION', 'vaysf_bible_verse_seeded');
}

if (!defined('VAYSF_BIBLE_VERSE_BUNDLED_PATH')) {
    define('VAYSF_BIBLE_VERSE_BUNDLED_PATH', dirname(__DIR__) . '/data/bible_verse_sets.seed.json');
}

function vaysf_user_has_all_bible_verse_events($user_id) {
    $user_id = absint($user_id);
    if (!$user_id || !user_can($user_id, VAYSF_BIBLE_VERSE_CAPABILITY)) {
        return false;
    }

    return user_can($user_id, 'manage_options')
        || user_can($user_id, 'sf2025_admin')
        || user_can($user_id, 'sf2025_write');
}

function vaysf_get_user_bible_verse_events($user_id) {
    $user_id = absint($user_id);
    if (!$user_id || !user_can($user_id, VAYSF_BIBLE_VERSE_CAPABILITY)) {
        return array();
    }

    if (vaysf_user_has_all_bible_verse_events($user_id)) {
        return vaysf_get_published_schedule_events();
    }

    return vaysf_get_user_authorized_events($user_id);
}

function vaysf_user_can_manage_bible_verse_event($user_id, $event) {
    $event = sanitize_text_field((string) $event);
    return $event !== '' && in_array($event, vaysf_get_user_bible_verse_events($user_id), true);
}

function vaysf_parse_bible_verse_allowed_events($value) {
    if (is_array($value)) {
        return vaysf_normalize_authorized_events($value);
    }

    $value = trim((string) $value);
    if ($value === '') {
        return array();
    }

    $decoded = json_decode($value, true);
    if (is_array($decoded)) {
        return vaysf_normalize_authorized_events($decoded);
    }

    return vaysf_normalize_authorized_events(array_map('trim', explode(',', $value)));
}

function vaysf_get_bible_verse_rows() {
    $rows = get_option(VAYSF_BIBLE_VERSE_OPTION, array());
    return is_array($rows) ? array_values($rows) : array();
}

function vaysf_update_bible_verse_rows($rows) {
    update_option(VAYSF_BIBLE_VERSE_OPTION, array_values($rows), false);
    return true;
}

function vaysf_get_bundled_bible_verse_payload() {
    if (!file_exists(VAYSF_BIBLE_VERSE_BUNDLED_PATH)) {
        return new WP_Error('vaysf_bible_verse_seed_missing', __('Bundled Bible verse seed file not found.', 'vaysf'));
    }

    $json = file_get_contents(VAYSF_BIBLE_VERSE_BUNDLED_PATH);
    if (!is_string($json) || trim($json) === '') {
        return new WP_Error('vaysf_bible_verse_seed_empty', __('Bundled Bible verse seed file is empty.', 'vaysf'));
    }

    $payload = json_decode($json, true);
    if (!is_array($payload) || !isset($payload['verse_sets']) || !is_array($payload['verse_sets'])) {
        return new WP_Error('vaysf_bible_verse_seed_invalid', __('Bundled Bible verse seed file is invalid.', 'vaysf'));
    }

    return $payload;
}

function vaysf_import_bible_verse_payload_for_events($payload, $allowed_events) {
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

function vaysf_seed_bible_verse_rows_if_empty() {
    if (get_option(VAYSF_BIBLE_VERSE_SEEDED_OPTION)) {
        return false;
    }

    $rows = vaysf_get_bible_verse_rows();
    if (!empty($rows)) {
        update_option(VAYSF_BIBLE_VERSE_SEEDED_OPTION, 1, false);
        return false;
    }

    $payload = vaysf_get_bundled_bible_verse_payload();
    if (is_wp_error($payload)) {
        return $payload;
    }

    $seed_rows = array();
    foreach ($payload['verse_sets'] as $raw_row) {
        if (!is_array($raw_row)) {
            continue;
        }
        $seed_rows[] = vaysf_sanitize_bible_verse_payload($raw_row, null);
    }

    if (empty($seed_rows)) {
        return new WP_Error('vaysf_bible_verse_seed_empty', __('Bundled Bible verse seed file did not contain any rows.', 'vaysf'));
    }

    vaysf_update_bible_verse_rows($seed_rows);
    update_option(VAYSF_BIBLE_VERSE_SEEDED_OPTION, 1, false);
    return true;
}

function vaysf_filter_bible_verse_rows_for_user($rows, $user_id, $active_only = false) {
    $allowed_events = vaysf_get_user_bible_verse_events($user_id);
    if (!$allowed_events) {
        return array();
    }

    return array_values(array_filter($rows, function ($row) use ($allowed_events, $active_only) {
        if ($active_only && empty($row['active'])) {
            return false;
        }
        return !empty($row['event']) && in_array((string) $row['event'], $allowed_events, true);
    }));
}

function vaysf_get_bible_verse_row($row_id) {
    $row_id = sanitize_key($row_id);
    foreach (vaysf_get_bible_verse_rows() as $row) {
        if (!empty($row['row_id']) && $row['row_id'] === $row_id) {
            return $row;
        }
    }
    return null;
}

function vaysf_sanitize_bible_verse_payload($raw, $existing = null) {
    $allowed_events = isset($raw['allowed_events']) ? wp_unslash($raw['allowed_events']) : array();
    $event_locked = !empty($raw['event_locked']);
    $event = isset($raw['event']) ? sanitize_text_field(wp_unslash($raw['event'])) : '';

    $row = array(
        'row_id' => !empty($existing['row_id']) ? sanitize_key($existing['row_id']) : 'verse_' . wp_generate_uuid4(),
        'set_key' => isset($raw['set_key']) ? sanitize_key(wp_unslash($raw['set_key'])) : '',
        'event' => $event,
        'season' => isset($raw['season']) ? absint($raw['season']) : absint(date_i18n('Y')),
        'sort_order' => isset($raw['sort_order']) ? absint($raw['sort_order']) : 0,
        'reference' => isset($raw['reference']) ? sanitize_text_field(wp_unslash($raw['reference'])) : '',
        'verse_text' => isset($raw['verse_text']) ? sanitize_textarea_field(wp_unslash($raw['verse_text'])) : '',
        'translation' => isset($raw['translation']) ? sanitize_text_field(wp_unslash($raw['translation'])) : '',
        'active' => !empty($raw['active']) ? 1 : 0,
        'event_locked' => $event_locked ? 1 : 0,
        'general_pool' => !empty($raw['general_pool']) ? 1 : 0,
        'allowed_events' => vaysf_parse_bible_verse_allowed_events($allowed_events),
        'created_by_user_id' => !empty($existing['created_by_user_id']) ? absint($existing['created_by_user_id']) : get_current_user_id(),
        'created_at' => !empty($existing['created_at']) ? (string) $existing['created_at'] : current_time('mysql'),
        'updated_by_user_id' => get_current_user_id(),
        'updated_at' => current_time('mysql'),
    );

    if ($row['event_locked']) {
        $row['general_pool'] = 0;
        $row['allowed_events'] = $event ? array($event) : array();
    }

    return $row;
}

function vaysf_validate_bible_verse_row($row, $rows, $current_row_id = '') {
    foreach (array('set_key', 'event', 'reference', 'verse_text') as $field) {
        if (empty($row[$field])) {
            return new WP_Error('vaysf_bible_verse_required', sprintf(__('Missing required Bible verse field: %s', 'vaysf'), $field));
        }
    }

    if (empty($row['season']) || empty($row['sort_order'])) {
        return new WP_Error('vaysf_bible_verse_required_number', __('Season and sort order are required.', 'vaysf'));
    }

    if (!vaysf_user_can_manage_bible_verse_event(get_current_user_id(), $row['event'])) {
        return new WP_Error('vaysf_bible_verse_forbidden_event', __('You are not allowed to manage verses for this event.', 'vaysf'));
    }

    foreach ($rows as $existing) {
        if (!empty($existing['row_id']) && $existing['row_id'] === $current_row_id) {
            continue;
        }
        if (
            (string) ($existing['set_key'] ?? '') === (string) $row['set_key']
            && (string) ($existing['event'] ?? '') === (string) $row['event']
            && absint($existing['season'] ?? 0) === absint($row['season'])
            && absint($existing['sort_order'] ?? 0) === absint($row['sort_order'])
        ) {
            return new WP_Error('vaysf_bible_verse_duplicate_order', __('Another verse in this set already uses that sort order.', 'vaysf'));
        }
    }

    return true;
}

function vaysf_save_bible_verse_row($raw, $row_id = '') {
    $row_id = sanitize_key($row_id);
    $rows = vaysf_get_bible_verse_rows();
    $existing = $row_id ? vaysf_get_bible_verse_row($row_id) : null;

    if ($row_id && !$existing) {
        return new WP_Error('vaysf_bible_verse_missing', __('Bible verse row not found.', 'vaysf'));
    }
    if ($existing && !vaysf_user_can_manage_bible_verse_event(get_current_user_id(), $existing['event'])) {
        return new WP_Error('vaysf_bible_verse_forbidden_event', __('You are not allowed to edit this event.', 'vaysf'));
    }

    $row = vaysf_sanitize_bible_verse_payload($raw, $existing);
    $validation = vaysf_validate_bible_verse_row($row, $rows, $row_id);
    if (is_wp_error($validation)) {
        return $validation;
    }

    $saved = false;
    foreach ($rows as $index => $existing_row) {
        if (!empty($existing_row['row_id']) && $existing_row['row_id'] === $row_id) {
            $rows[$index] = $row;
            $saved = true;
            break;
        }
    }
    if (!$saved) {
        $rows[] = $row;
    }

    vaysf_update_bible_verse_rows($rows);
    return $row['row_id'];
}

function vaysf_deactivate_bible_verse_row($row_id) {
    $row_id = sanitize_key($row_id);
    $rows = vaysf_get_bible_verse_rows();

    foreach ($rows as $index => $row) {
        if (!empty($row['row_id']) && $row['row_id'] === $row_id) {
            if (!vaysf_user_can_manage_bible_verse_event(get_current_user_id(), $row['event'])) {
                return new WP_Error('vaysf_bible_verse_forbidden_event', __('You are not allowed to edit this event.', 'vaysf'));
            }
            $rows[$index]['active'] = 0;
            $rows[$index]['updated_by_user_id'] = get_current_user_id();
            $rows[$index]['updated_at'] = current_time('mysql');
            vaysf_update_bible_verse_rows($rows);
            return true;
        }
    }

    return new WP_Error('vaysf_bible_verse_missing', __('Bible verse row not found.', 'vaysf'));
}

function vaysf_delete_bible_verse_row($row_id) {
    $row_id = sanitize_key($row_id);
    $rows = vaysf_get_bible_verse_rows();

    foreach ($rows as $index => $row) {
        if (!empty($row['row_id']) && $row['row_id'] === $row_id) {
            if (!vaysf_user_can_manage_bible_verse_event(get_current_user_id(), $row['event'])) {
                return new WP_Error('vaysf_bible_verse_forbidden_event', __('You are not allowed to delete this event.', 'vaysf'));
            }
            unset($rows[$index]);
            vaysf_update_bible_verse_rows($rows);
            return true;
        }
    }

    return new WP_Error('vaysf_bible_verse_missing', __('Bible verse row not found.', 'vaysf'));
}

function vaysf_bible_verse_rows_to_export_payload($rows) {
    $verse_sets = array();
    foreach ($rows as $row) {
        $verse_sets[] = array(
            'set_key' => (string) ($row['set_key'] ?? ''),
            'event' => (string) ($row['event'] ?? ''),
            'season' => absint($row['season'] ?? 0),
            'sort_order' => absint($row['sort_order'] ?? 0),
            'reference' => (string) ($row['reference'] ?? ''),
            'verse_text' => (string) ($row['verse_text'] ?? ''),
            'translation' => (string) ($row['translation'] ?? ''),
            'active' => !empty($row['active']),
            'event_locked' => !empty($row['event_locked']),
            'general_pool' => !empty($row['general_pool']),
            'allowed_events' => array_values(vaysf_parse_bible_verse_allowed_events($row['allowed_events'] ?? array())),
        );
    }

    usort($verse_sets, function ($a, $b) {
        return array($a['event'], $a['set_key'], $a['season'], $a['sort_order'])
            <=> array($b['event'], $b['set_key'], $b['season'], $b['sort_order']);
    });

    return array('verse_sets' => $verse_sets);
}

function vaysf_get_bible_verse_export_payload_for_user($user_id, $selected_event = '') {
    $rows = vaysf_filter_bible_verse_rows_for_user(vaysf_get_bible_verse_rows(), $user_id, false);
    $selected_event = sanitize_text_field((string) $selected_event);
    if ($selected_event !== '') {
        $rows = array_values(array_filter($rows, function ($row) use ($selected_event) {
            return (string) ($row['event'] ?? '') === $selected_event;
        }));
    }

    return vaysf_bible_verse_rows_to_export_payload($rows);
}

function vaysf_download_bible_verses_json() {
    if (!current_user_can(VAYSF_BIBLE_VERSE_CAPABILITY)) {
        wp_die(esc_html__('You are not authorized to export Bible verses.', 'vaysf'));
    }

    if (
        empty($_POST['vaysf_bible_verse_download_nonce'])
        || !wp_verify_nonce(
            sanitize_text_field(wp_unslash($_POST['vaysf_bible_verse_download_nonce'])),
            'vaysf_bible_verse_download'
        )
    ) {
        wp_die(esc_html__('Security check failed.', 'vaysf'));
    }

    $selected_event = isset($_POST['event_filter']) ? sanitize_text_field(wp_unslash($_POST['event_filter'])) : '';
    $allowed_events = vaysf_get_user_bible_verse_events(get_current_user_id());
    if ($selected_event !== '' && !in_array($selected_event, $allowed_events, true)) {
        $selected_event = '';
    }

    $payload = vaysf_get_bible_verse_export_payload_for_user(get_current_user_id(), $selected_event);
    $filename = 'vaysf-bible-verses';
    if ($selected_event !== '') {
        $filename .= '-' . sanitize_title($selected_event);
    }
    $filename .= '.json';

    nocache_headers();
    header('Content-Type: application/json; charset=' . get_option('blog_charset'));
    header('Content-Disposition: attachment; filename="' . $filename . '"');
    echo wp_json_encode($payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
    exit;
}

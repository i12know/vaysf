<?php
/**
 * File: admin/class-vaysf-admin-page.php
 * Description: Shared base for VAYSF admin pages - schedule/result status
 *              vocabularies, team formatting, and admin notices
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

abstract class VAYSF_Admin_Page {

    protected function schedule_status_options() {
        return array('scheduled', 'in_progress', 'reported', 'official', 'under_review', 'cancelled');
    }

    protected function public_status_options() {
        return array('pending', 'in_progress', 'reported', 'official', 'under_review');
    }

    protected function scan_status_options() {
        return array('pending', 'uploaded', 'missing', 'not_required');
    }

    protected function revision_state_options() {
        return array('unverified', 'verified', 'rejected');
    }

    protected function is_protected_schedule_status($status) {
        return in_array($status, array('reported', 'official', 'under_review'), true);
    }

    protected function format_game_teams($row) {
        $teams = array();
        foreach (array('team_a_label', 'team_b_label', 'team_c_label') as $field) {
            if (!empty($row[$field])) {
                $teams[] = $row[$field];
            }
        }
        return implode(' vs ', $teams);
    }

    protected function textarea_json_value($value) {
        if (is_array($value) || is_object($value)) {
            return wp_json_encode($value, JSON_PRETTY_PRINT);
        }
        return (string) $value;
    }

    protected function print_admin_notice($result, $success_message) {
        if (is_wp_error($result)) {
            echo '<div class="notice notice-error"><p>' . esc_html($result->get_error_message()) . '</p></div>';
        } elseif ($result) {
            echo '<div class="notice notice-success"><p>' . esc_html($success_message) . '</p></div>';
        }
    }
}

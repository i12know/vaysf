<?php
/**
 * File: includes/functions.php
 * Description: Helper functions for VAYSF Integration
 * Version: 1.0.4
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

/**
 * Get table name
 * 
 * @param string $table Table name without prefix
 * @return string Full table name with prefix
 */
function vaysf_get_table_name($table) {
    global $wpdb;
    return $wpdb->prefix . 'sf_' . $table;
}

/**
 * Log sync request for churches
 * 
 * @return bool Success status
 */
 // In functions.php:
function vaysf_sync_churches() {
    global $wpdb;
    $table_name = vaysf_get_table_name('sync_log');
    
    return $wpdb->insert($table_name, array(
        'sync_type' => 'churches',
        'direction' => 'to_wp',
        'records_processed' => 0,
        'success_count' => 0,
        'error_count' => 0,
        'error_details' => 'Middleware sync requested via admin UI',
        'started_at' => current_time('mysql'),
        'completed_at' => null,
        'status' => 'pending'
    ));
}

/**
 * Log sync request for participants
 * 
 * @return bool Success status
 */
function vaysf_sync_participants() {
    global $wpdb;
    $table_name = vaysf_get_table_name('sync_log');
    
    return $wpdb->insert($table_name, array(
        'sync_type' => 'participants',
        'direction' => 'to_wp',
        'records_processed' => 0,
        'success_count' => 0,
        'error_count' => 0,
        'error_details' => 'Middleware sync requested via admin UI',
        'started_at' => current_time('mysql'),
        'completed_at' => null
    ));
}

/**
 * Log sync request for approvals
 * 
 * @return bool Success status
 */
function vaysf_generate_approvals() {
    global $wpdb;
    $table_name = vaysf_get_table_name('sync_log');
    
    return $wpdb->insert($table_name, array(
        'sync_type' => 'approvals',
        'direction' => 'to_wp',
        'records_processed' => 0,
        'success_count' => 0,
        'error_count' => 0,
        'error_details' => 'Approval token generation requested via admin UI',
        'started_at' => current_time('mysql'),
        'completed_at' => null
    ));
}

/**
 * Log validation request
 * 
 * @return bool Success status
 */
function vaysf_validate_data() {
    global $wpdb;
    $table_name = vaysf_get_table_name('sync_log');
    
    return $wpdb->insert($table_name, array(
        'sync_type' => 'validation',
        'direction' => 'to_wp',
        'records_processed' => 0,
        'success_count' => 0,
        'error_count' => 0,
        'error_details' => 'Data validation requested via admin UI',
        'started_at' => current_time('mysql'),
        'completed_at' => null
    ));
}

/**
 * Format validation severity
 * 
 * @param string $severity Validation severity
 * @return string Formatted severity
 */
function vaysf_format_validation_severity($severity) {
    switch ($severity) {
        case 'ERROR':
            return '<span class="validation-severity severity-error">' . esc_html__('Error', 'vaysf') . '</span>';
        case 'WARNING':
            return '<span class="validation-severity severity-warning">' . esc_html__('Warning', 'vaysf') . '</span>';
        case 'INFO':
            return '<span class="validation-severity severity-info">' . esc_html__('Info', 'vaysf') . '</span>';
        default:
            return '<span class="validation-severity severity-error">' . esc_html__('Error', 'vaysf') . '</span>';
    }
}

/**
 * Format validation status
 * 
 * @param string $status Validation status
 * @return string Formatted status
 */
function vaysf_format_validation_status($status) {
    switch ($status) {
        case 'resolved':
            return '<span class="validation-status status-resolved">' . esc_html__('Resolved', 'vaysf') . '</span>';
        case 'open':
        default:
            return '<span class="validation-status status-open">' . esc_html__('Open', 'vaysf') . '</span>';
    }
}

/**
 * Format approval status
 * 
 * @param string $status Approval status
 * @return string Formatted status
 */
function vaysf_format_approval_status($status) {
    switch ($status) {
        case 'approved':
            return '<span class="approval-status status-approved">' . esc_html__('Approved', 'vaysf') . '</span>';
        case 'denied':
            return '<span class="approval-status status-denied">' . esc_html__('Denied', 'vaysf') . '</span>';
        case 'validated':
            return '<span class="approval-status status-validated">' . esc_html__('Validated', 'vaysf') . '</span>';
        case 'pending_approval':
            return '<span class="approval-status status-pending-approval">' . esc_html__('Pending Approval', 'vaysf') . '</span>';
        case 'pending':
        default:
            return '<span class="approval-status status-pending">' . esc_html__('Pending', 'vaysf') . '</span>';
    }
}

/**
 * Get church by ID
 * 
 * @param int $church_id Church ID
 * @return object|false Church object or false if not found
 */
function vaysf_get_church($church_id) {
    global $wpdb;
    
    $table_name = vaysf_get_table_name('churches');
    
    return $wpdb->get_row(
        $wpdb->prepare("SELECT * FROM $table_name WHERE church_id = %d", $church_id)
    );
}

/**
 * Get participant by ID
 * 
 * @param int $participant_id Participant ID
 * @return object|false Participant object or false if not found
 */
function vaysf_get_participant($participant_id) {
    global $wpdb;
    
    $table_name = vaysf_get_table_name('participants');
    
    return $wpdb->get_row(
        $wpdb->prepare("SELECT * FROM $table_name WHERE participant_id = %d", $participant_id)
    );
}

/**
 * Get participant link
 * 
 * @param int $participant_id Participant ID
 * @param string $text Link text (optional)
 * @return string HTML link
 */
function vaysf_get_participant_link($participant_id, $text = '') {
    $participant = vaysf_get_participant($participant_id);
    
    if (!$participant) {
        return esc_html__('Unknown', 'vaysf');
    }
    
    if (empty($text)) {
        $text = esc_html($participant->first_name . ' ' . $participant->last_name);
    }
    
    $url = admin_url('admin.php?page=vaysf-participants&action=edit&id=' . $participant_id);
    
    return '<a href="' . esc_url($url) . '">' . $text . '</a>';
}

/**
 * Get church link
 * 
 * @param int $church_id Church ID
 * @param string $text Link text (optional)
 * @return string HTML link
 */
function vaysf_get_church_link($church_id, $text = '') {
    $church = vaysf_get_church($church_id);
    
    if (!$church) {
        return esc_html__('Unknown', 'vaysf');
    }
    
    if (empty($text)) {
        $text = esc_html($church->church_name);
    }
    
    $url = admin_url('admin.php?page=vaysf-churches&action=edit&id=' . $church_id);
    
    return '<a href="' . esc_url($url) . '">' . $text . '</a>';
}

/**
 * Sanitize and validate age
 * 
 * @param mixed $age Age value
 * @return int Sanitized age
 */
function vaysf_sanitize_age($age) {
    $age = intval($age);
    
    if ($age < 0) {
        $age = 0;
    }
    
    if ($age > 120) {
        $age = 120;
    }
    
    return $age;
}

/**
 * Calculate age from birthdate
 * 
 * @param string $birthdate Birthdate in Y-m-d format
 * @return int Age
 */
function vaysf_calculate_age($birthdate) {
    $birth_date = new DateTime($birthdate);
    $today = new DateTime();
    $age = $birth_date->diff($today)->y;
    
    return $age;
}

/**
 * Check if sport has an age exception
 * 
 * @param string $sport Sport name
 * @param int $age Age to check
 * @return bool True if age exception applies
 */
function vaysf_has_age_exception($sport, $age) {
    // Sports with age exceptions
    $exceptions = array(
        'Scripture Memorization' => true,
        'Tug-O-War' => true,
    );
    
    // Special case for 35+ Pickleball
    if ($sport === 'Pickleball' && $age > 35) {
        return true;
    }
    
    return isset($exceptions[$sport]) && $exceptions[$sport];
}

/**
 * Get roster by ID
 * 
 * @param int $roster_id Roster ID
 * @return object|false Roster object or false if not found
 */
function vaysf_get_roster($roster_id) {
    global $wpdb;
    
    $table_name = vaysf_get_table_name('rosters');
    
    return $wpdb->get_row(
        $wpdb->prepare("SELECT * FROM $table_name WHERE roster_id = %d", $roster_id)
    );
}

/**
 * Get rosters by participant ID
 * 
 * @param int $participant_id Participant ID
 * @return array Array of roster objects
 */
function vaysf_get_rosters_by_participant($participant_id) {
    global $wpdb;
    
    $table_name = vaysf_get_table_name('rosters');
    
    return $wpdb->get_results(
        $wpdb->prepare("SELECT * FROM $table_name WHERE participant_id = %d", $participant_id),
        ARRAY_A
    );
}

/**
 * Get rosters by church code
 * 
 * @param string $church_code Church code
 * @return array Array of roster objects
 */
function vaysf_get_rosters_by_church($church_code) {
    global $wpdb;
    
    $table_name = vaysf_get_table_name('rosters');
    
    return $wpdb->get_results(
        $wpdb->prepare("SELECT * FROM $table_name WHERE church_code = %s", $church_code),
        ARRAY_A
    );
}

/**
 * Get sport options
 * 
 * @return array Sport options
 */
function vaysf_get_sport_options() {
    return array(
        '' => __('None', 'vaysf'),
        'Basketball' => __('Basketball', 'vaysf'),
        'Men Volleyball' => __('Men Volleyball', 'vaysf'),
        'Women Volleyball' => __('Women Volleyball', 'vaysf'),
        'Bible Challenge' => __('Bible Challenge', 'vaysf'),
        'Track and Field' => __('Track and Field', 'vaysf'),
        'Tennis' => __('Tennis', 'vaysf'),
        'Pickleball' => __('Pickleball', 'vaysf'),
        'Table Tennis' => __('Table Tennis', 'vaysf'),
        'Badminton' => __('Badminton', 'vaysf'),
        'Scripture Memorization' => __('Scripture Memorization', 'vaysf'),
        'Tug-O-War' => __('Tug-O-War', 'vaysf'),
    );
}

/**
 * Get format options for racquet sports
 * 
 * @param string $sport Sport name
 * @return array Format options
 */
function vaysf_get_format_options($sport) {
    switch ($sport) {
        case 'Tennis':
        case 'Pickleball':
        case 'Table Tennis':
        case 'Badminton':
            return array(
                'Singles' => __('Singles', 'vaysf'),
                'Doubles' => __('Doubles', 'vaysf'),
                'Mixed Doubles' => __('Mixed Doubles', 'vaysf'),
            );
        default:
            return array();
    }
}

/**
 * Get team sports
 * 
 * @return array Team sports
 */
function vaysf_get_team_sports() {
    return array(
        'Basketball',
        'Men Volleyball',
        'Women Volleyball',
        'Bible Challenge',
    );
}

/**
 * Get individual sports
 * 
 * @return array Individual sports
 */
function vaysf_get_individual_sports() {
    return array(
        'Track and Field',
        'Tennis',
        'Pickleball',
        'Table Tennis',
        'Badminton',
        'Scripture Memorization',
        'Tug-O-War',
    );
}

/**
 * Check if sport is a team sport
 * 
 * @param string $sport Sport name
 * @return bool True if team sport
 */
function vaysf_is_team_sport($sport) {
    return in_array($sport, vaysf_get_team_sports());
}

/**
 * Check if sport is an individual sport
 * 
 * @param string $sport Sport name
 * @return bool True if individual sport
 */
function vaysf_is_individual_sport($sport) {
    return in_array($sport, vaysf_get_individual_sports());
}

/**
 * Check if sport is a racquet sport
 * 
 * @param string $sport Sport name
 * @return bool True if racquet sport
 */
function vaysf_is_racquet_sport($sport) {
    return in_array($sport, array('Tennis', 'Pickleball', 'Table Tennis', 'Badminton'));
}

/**
 * Send an email and optionally log it in the database
 *
 * @param string $to      Recipient email address
 * @param string $subject Email subject line
 * @param string $message HTML email body
 * @param array  $args    Optional arguments (from => sender email)
 * @return bool True if email was sent successfully
 */
function vaysf_send_email($to, $subject, $message, $args = array()) {
    $to = sanitize_email($to);
    $subject = sanitize_text_field($subject);
    $message = wp_kses_post($message);

    $headers = array('Content-Type: text/html; charset=UTF-8');
    if (!empty($args['from'])) {
        $from_email = sanitize_email($args['from']);
        $headers[] = 'From: ' . $from_email;
    } else {
        $from_email = get_option('vaysf_email_from', get_option('admin_email'));
        $headers[] = 'From: Sports Fest <' . $from_email . '>';
    }

    $sent = wp_mail($to, $subject, $message, $headers);

    if (get_option('vaysf_log_emails', false)) {
        global $wpdb;
        $table_name = $wpdb->prefix . 'sf_email_log';
        $wpdb->insert($table_name, array(
            'to_email' => $to,
            'subject'  => $subject,
            'message'  => $message,
            'sent_at'  => current_time('mysql'),
            'status'   => $sent ? 'sent' : 'failed'
        ));
    }

    return $sent;
}

/**
 * Resend pastor approval email for a given approval record
 *
 * @param array $approval Approval record with participant and church info
 * @return bool True if email sent
 */
function vaysf_resend_approval_email($approval) {
    $participant_name = $approval['first_name'] . ' ' . $approval['last_name'];
    $subject_base     = get_option('vaysf_approval_email_subject', 'Sports Fest 2025: Approval Request');
    $subject          = $subject_base . ' for ' . $participant_name;

    $approve_link = site_url('pastor-approval') . '?token=' . urlencode($approval['approval_token']) . '&decision=approve';
    $deny_link    = site_url('pastor-approval') . '?token=' . urlencode($approval['approval_token']) . '&decision=deny';
    $expiry       = date_i18n('F j, Y g:i a', strtotime($approval['token_expiry']));

    $message = '<h2>Sports Fest Participant Approval for ' . esc_html($participant_name) . '</h2>';
    $message .= '<p>Dear Pastor,</p>';
    $message .= '<p>A participant, <strong>' . esc_html($participant_name) . '</strong>, has registered for Sports Fest and listed under your church. Please review and approve or deny their participation.</p>';
    $message .= '<p>';
    $message .= '<a href="' . esc_url($approve_link) . '" style="padding:10px 15px;background:#4CAF50;color:white;text-decoration:none;margin-right:10px;">Approve</a>';
    $message .= '<a href="' . esc_url($deny_link) . '" style="padding:10px 15px;background:#f44336;color:white;text-decoration:none;">Deny</a>';
    $message .= '</p>';
    $message .= '<p><strong>Note:</strong> This approval link will expire on ' . esc_html($expiry) . '.</p>';
    $message .= '<p>Thank you for your help with Sports Fest!</p>';

    return vaysf_send_email($approval['pastor_email'], $subject, $message);
}

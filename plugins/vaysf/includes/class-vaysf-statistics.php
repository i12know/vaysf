<?php
/**
 * File: includes/class-vaysf-statistics.php
 * Description: Utility class for generating VAYSF statistics
 * Version: 1.0.0
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_Statistics {
    
    /**
     * Get overall statistics
     * 
     * @return array Array of statistics
     */
    public static function get_overall_stats() {
        global $wpdb;
        
        return array(
            'churches' => array(
                'count' => $wpdb->get_var("SELECT COUNT(*) FROM {$wpdb->prefix}sf_churches"),
                'label' => 'Churches',
                'icon'  => 'church'
            ),
            'participants' => array(
                'count' => $wpdb->get_var("SELECT COUNT(*) FROM {$wpdb->prefix}sf_participants"),
                'label' => 'Participants',
                'icon'  => 'person'
            ),
            'pending_approvals' => array(
                'count' => $wpdb->get_var("SELECT COUNT(*) FROM {$wpdb->prefix}sf_approvals WHERE approval_status = 'pending'"),
                'label' => 'Pending Approvals',
                'icon'  => 'clock'
            ),
            'approved' => array(
                'count' => $wpdb->get_var("SELECT COUNT(*) FROM {$wpdb->prefix}sf_approvals WHERE approval_status = 'approved'"),
                'label' => 'Approved Participants',
                'icon'  => 'yes'
            ),
            'denied' => array(
                'count' => $wpdb->get_var("SELECT COUNT(*) FROM {$wpdb->prefix}sf_approvals WHERE approval_status = 'denied'"),
                'label' => 'Denied Participants',
                'icon'  => 'no'
            ),
            'validation_issues' => array(
                'count' => $wpdb->get_var("SELECT COUNT(*) FROM {$wpdb->prefix}sf_validation_issues WHERE status = 'open'"),
                'label' => 'Validation Issues',
                'icon'  => 'warning'
            )
        );
    }
    
    /**
     * Get churches data
     * 
     * @param array $args Query arguments
     * @return array Array of churches
     */
    public static function get_churches($args = array()) {
        global $wpdb;
        
        // Default arguments
        $defaults = array(
            'limit' => 10,
            'orderby' => 'church_name',
            'order' => 'ASC',
            'status' => '',
            'insurance_status' => '',
            'include_stats' => false,
        );
        
        $args = wp_parse_args($args, $defaults);

        $table_churches = $wpdb->prefix . 'sf_churches';
        $table_participants = $wpdb->prefix . 'sf_participants';

        $include_stats = !empty($args['include_stats']);

        $allowed_orderby = array(
            'church_name' => 'c.church_name',
            'church_code' => 'c.church_code',
            'registration_status' => 'c.registration_status',
            'insurance_status' => 'c.insurance_status',
            'insurance_uploaded_at' => 'c.insurance_uploaded_at',
        );

        if ($include_stats) {
            $allowed_orderby['total_participants'] = 'total_participants';
            $allowed_orderby['approved_participants'] = 'approved_participants';
            $allowed_orderby['approval_percentage'] = 'approval_percentage';
            $allowed_orderby['consented_participants'] = 'consented_participants';
            $allowed_orderby['consent_percentage'] = 'consent_percentage';
        }

        $orderby = isset($allowed_orderby[$args['orderby']]) ? $allowed_orderby[$args['orderby']] : $allowed_orderby['church_name'];
        $order = strtoupper($args['order']) === 'DESC' ? 'DESC' : 'ASC';
        
        // Build query
        $query = "SELECT c.*";

        if ($include_stats) {
            $query .= ",
                COALESCE(ps.total_participants, 0) AS total_participants,
                COALESCE(ps.approved_participants, 0) AS approved_participants,
                CASE
                    WHEN COALESCE(ps.total_participants, 0) > 0
                    THEN ROUND((COALESCE(ps.approved_participants, 0) / ps.total_participants) * 100, 1)
                    ELSE 0
                END AS approval_percentage,
                COALESCE(ps.consented_participants, 0) AS consented_participants,
                CASE
                    WHEN COALESCE(ps.total_participants, 0) > 0
                    THEN ROUND((COALESCE(ps.consented_participants, 0) / ps.total_participants) * 100, 1)
                    ELSE 0
                END AS consent_percentage";
        }

        $query .= " FROM $table_churches c";

        if ($include_stats) {
            $query .= " LEFT JOIN (
                SELECT
                    church_code,
                    COUNT(*) AS total_participants,
                    SUM(CASE WHEN approval_status = 'approved' THEN 1 ELSE 0 END) AS approved_participants,
                    SUM(CASE WHEN consent_status = 1 THEN 1 ELSE 0 END) AS consented_participants
                FROM $table_participants
                GROUP BY church_code
            ) ps ON ps.church_code = c.church_code";
        }

        $where = array();
        $where_args = array();
        
        if (!empty($args['status'])) {
            $where[] = "c.registration_status = %s";
            $where_args[] = $args['status'];
        }

        if (!empty($args['insurance_status'])) {
            $where[] = "c.insurance_status = %s";
            $where_args[] = $args['insurance_status'];
        }
        
        if (!empty($where)) {
            $query .= " WHERE " . implode(' AND ', $where);
        }
        
        $query .= " ORDER BY $orderby $order LIMIT %d";
        $where_args[] = (int) $args['limit'];
        
        // Get churches
        return $wpdb->get_results(
            $wpdb->prepare($query, $where_args),
            ARRAY_A
        );
    }
    
    /**
     * Get participants data
     * 
     * @param array $args Query arguments
     * @return array Array of participants
     */
    public static function get_participants($args = array()) {
        global $wpdb;
        
        // Default arguments
        $defaults = array(
            'limit' => 10,
            'orderby' => 'last_name',
            'order' => 'ASC',
            'church_code' => '',
            'status' => '',
            'sport' => '',
        );
        
        $args = wp_parse_args($args, $defaults);
        
        // Build query
        $query = "SELECT p.*, c.church_name 
                 FROM {$wpdb->prefix}sf_participants p
                 JOIN {$wpdb->prefix}sf_churches c ON p.church_code = c.church_code";
        
        $where = array();
        $where_args = array();
        
        if (!empty($args['church_code'])) {
            $where[] = "p.church_code = %s";
            $where_args[] = $args['church_code'];
        }
        
        if (!empty($args['status'])) {
            $where[] = "p.approval_status = %s";
            $where_args[] = $args['status'];
        }
        
        if (!empty($args['sport'])) {
            $where[] = "(p.primary_sport = %s OR p.secondary_sport = %s)";
            $where_args[] = $args['sport'];
            $where_args[] = $args['sport'];
        }
        
        if (!empty($where)) {
            $query .= " WHERE " . implode(' AND ', $where);
        }
        
        $query .= " ORDER BY p.{$args['orderby']} {$args['order']} LIMIT %d";
        $where_args[] = (int) $args['limit'];
        
        // Get participants
        return $wpdb->get_results(
            $wpdb->prepare($query, $where_args),
            ARRAY_A
        );
    }
    
    /**
     * Get validation issues data
     * 
     * @param array $args Query arguments
     * @return array Array of validation issues
     */
    public static function get_validation_issues($args = array()) {
        global $wpdb;
        
        // Default arguments
        $defaults = array(
            'limit' => 10,
            'status' => 'open',
            'church_id' => 0,
            'participant_id' => 0,
            'severity' => '',
        );
        
        $args = wp_parse_args($args, $defaults);
        
        $table_issues = $wpdb->prefix . 'sf_validation_issues';
        $table_churches = $wpdb->prefix . 'sf_churches';
        $table_participants = $wpdb->prefix . 'sf_participants';
        
        // Build query
        $query = "SELECT i.*, c.church_name, p.first_name, p.last_name 
                 FROM $table_issues i 
                 LEFT JOIN $table_churches c ON i.church_id = c.church_id 
                 LEFT JOIN $table_participants p ON i.participant_id = p.participant_id";
        
        $where = array();
        $where_args = array();
        
        if (!empty($args['status'])) {
            $where[] = "i.status = %s";
            $where_args[] = $args['status'];
        }
        
        if (!empty($args['church_id'])) {
            $where[] = "i.church_id = %d";
            $where_args[] = (int) $args['church_id'];
        }
        
        if (!empty($args['participant_id'])) {
            $where[] = "i.participant_id = %d";
            $where_args[] = (int) $args['participant_id'];
        }
        
        if (!empty($args['severity'])) {
            $where[] = "i.severity = %s";
            $where_args[] = $args['severity'];
        }
        
        if (!empty($where)) {
            $query .= " WHERE " . implode(' AND ', $where);
        }
        
        $query .= " ORDER BY i.created_at DESC LIMIT %d";
        $where_args[] = (int) $args['limit'];
        
        // Get issues
        return $wpdb->get_results(
            $wpdb->prepare($query, $where_args),
            ARRAY_A
        );
    }
}

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
        );
        
        $args = wp_parse_args($args, $defaults);
        
        // Build query
        $query = "SELECT * FROM {$wpdb->prefix}sf_churches";
        $where = array();
        $where_args = array();
        
        if (!empty($args['status'])) {
            $where[] = "registration_status = %s";
            $where_args[] = $args['status'];
        }
        
        if (!empty($where)) {
            $query .= " WHERE " . implode(' AND ', $where);
        }
        
        $query .= " ORDER BY {$args['orderby']} {$args['order']} LIMIT %d";
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
<?php
/**
 * File: admin/class-vaysf-admin-dashboard.php
 * Description: Sports Fest admin dashboard page (overview stats + quick actions)
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_Admin_Dashboard extends VAYSF_Admin_Page {

// We could: require_once plugin_dir_path(dirname(__FILE__)) . 'includes/class-vaysf-statistics.php'; $stats = VAYSF_Statistics::get_overall_stats();
// But replacing "Churches" with $stats['churches']['label'] and $church_count with $stats['churches']['count'] doesn't yield economic sense right now
    /**
     * Display dashboard page
     */
    public function display_dashboard_page() {
        global $wpdb;

        // Ensure VAYSF_Statistics class is available
        if (!class_exists('VAYSF_Statistics')) {
            // Adjust path if VAYSF_Admin and VAYSF_Statistics are in different directory levels relative to plugin root
            require_once plugin_dir_path(dirname(__FILE__)) . 'includes/class-vaysf-statistics.php';
        }
        $stats = VAYSF_Statistics::get_overall_stats();
        // Use stats from the VAYSF_Statistics class
        $church_count = $stats['churches']['count'];
        $participant_count = $stats['participants']['count'];
        $pending_approvals = $stats['pending_approvals']['count'];
        $approved_participants = $stats['approved']['count']; // Now uses the corrected logic
        // $denied_participants = $stats['denied']['count']; // Also uses corrected logic
        $validation_issues = $stats['validation_issues']['count'];

        // Get stats the old ways
        // $church_count = $wpdb->get_var("SELECT COUNT(*) FROM {$wpdb->prefix}sf_churches");
        // $participant_count = $wpdb->get_var("SELECT COUNT(*) FROM {$wpdb->prefix}sf_participants");
        // $pending_approvals = $wpdb->get_var("SELECT COUNT(*) FROM {$wpdb->prefix}sf_approvals WHERE approval_status = 'pending'");
        // $approved_participants = $wpdb->get_var("SELECT COUNT(*) FROM {$wpdb->prefix}sf_approvals WHERE approval_status = 'approved'");
        // $denied_participants = $wpdb->get_var("SELECT COUNT(*) FROM {$wpdb->prefix}sf_approvals WHERE approval_status = 'denied'");
        // $validation_issues = $wpdb->get_var("SELECT COUNT(*) FROM {$wpdb->prefix}sf_validation_issues WHERE status = 'open'");
        
        ?>
        <div class="wrap">
            <h1>Sports Fest Integration</h1>
            
            <div class="vaysf-dashboard">
                <div class="vaysf-stats">
                    <h2>Overview</h2>
                    <div class="vaysf-stat-grid">
                        <div class="vaysf-stat-box">
                            <h3><?php echo esc_html($stats['churches']['label']); ?></h3>
                            <div class="vaysf-stat-number"><?php echo esc_html($church_count); ?></div>
                            <a href="<?php echo admin_url('admin.php?page=vaysf-churches'); ?>" class="button">View Churches</a>
                        </div>
                        
                        <div class="vaysf-stat-box">
                            <h3><?php echo esc_html($stats['participants']['label']); ?></h3>
                            <div class="vaysf-stat-number"><?php echo esc_html($participant_count); ?></div>
                            <a href="<?php echo admin_url('admin.php?page=vaysf-participants'); ?>" class="button">View Participants</a>
                        </div>
                        
                        <div class="vaysf-stat-box">
                            <h3><?php echo esc_html($stats['pending_approvals']['label']); ?></h3>
                            <div class="vaysf-stat-number"><?php echo esc_html($pending_approvals); ?></div>
                            <a href="<?php echo admin_url('admin.php?page=vaysf-approvals'); ?>" class="button">View Approvals</a>
                        </div>
                        
                        <div class="vaysf-stat-box">
                            <h3><?php echo esc_html($stats['approved']['label']); ?></h3>
                            <div class="vaysf-stat-number"><?php echo esc_html($approved_participants); ?></div>
                            <a href="<?php echo admin_url('admin.php?page=vaysf-participants'); ?>" class="button">View Participants</a>
                        </div>

                        <?php // If we want to display denied participants on the admin dashboard:
                        /*
                        <div class="vaysf-stat-box">
                            <h3><?php echo esc_html($stats['denied']['label']); ?></h3>
                            <div class="vaysf-stat-number"><?php echo esc_html($stats['denied']['count']); ?></div>
                            <a href="<?php echo admin_url('admin.php?page=vaysf-participants'); // Link appropriately ?>" class="button">View Participants</a>
                        </div>
                        */
                        ?>                        

                        <div class="vaysf-stat-box">
                            <h3><?php echo esc_html($stats['validation_issues']['label']); ?></h3>
                            <div class="vaysf-stat-number"><?php echo esc_html($validation_issues); ?></div>
                            <a href="<?php echo admin_url('admin.php?page=vaysf-validation'); ?>" class="button">View Issues</a>
                        </div>
                    </div>
                </div>
                
                <div class="vaysf-actions">
                    <h2>Quick Actions</h2>
                    <div class="vaysf-action-buttons">
                        <a href="<?php echo admin_url('admin.php?page=vaysf-churches&action=sync'); ?>" class="button button-primary">Sync Churches</a>
                        <a href="<?php echo admin_url('admin.php?page=vaysf-participants&action=sync'); ?>" class="button button-primary">Sync Participants</a>
                        <a href="<?php echo admin_url('admin.php?page=vaysf-approvals&action=generate'); ?>" class="button button-primary">Generate Approval Tokens</a>
                        <a href="<?php echo admin_url('admin.php?page=vaysf-validation&action=validate'); ?>" class="button button-primary">Validate Data</a>
                    </div>
                </div>
            </div>
        </div>
        
        <style>
            .vaysf-stat-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }
            
            .vaysf-stat-box {
                background: #fff;
                border: 1px solid #ccd0d4;
                box-shadow: 0 1px 1px rgba(0, 0, 0, 0.04);
                padding: 20px;
                text-align: center;
                border-radius: 5px;
            }
            
            .vaysf-stat-number {
                font-size: 36px;
                font-weight: bold;
                margin: 10px 0 20px;
            }
            
            .vaysf-action-buttons {
                margin-top: 20px;
            }
            
            .vaysf-action-buttons .button {
                margin-right: 10px;
                margin-bottom: 10px;
            }
        </style>
        <?php
    }
}

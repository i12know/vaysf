<?php
/**
 * File: admin/class-vaysf-admin-participants.php
 * Description: Participants admin page - listing, church filter, sync request
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_Admin_Participants extends VAYSF_Admin_Page {

/**
 * Display participants page
 */
public function display_participants_page() {
    global $wpdb;
    
    $table_name = $wpdb->prefix . 'sf_participants';
    $table_churches = $wpdb->prefix . 'sf_churches';
    
    if (isset($_GET['action']) && $_GET['action'] === 'sync') {
        if (vaysf_sync_participants()) {
            echo '<div class="notice notice-info"><p>Sync request for participants has been logged. The middleware will process this request during its next scheduled run.</p></div>';
        } else {
            echo '<div class="notice notice-error"><p>Error logging sync request for participants.</p></div>';
        }
    }
    
    $church_filter = isset($_GET['church_id']) ? (int) $_GET['church_id'] : 0;
    $where_clause = $church_filter ? "WHERE c.church_id = $church_filter" : '';
    
    $participants = $wpdb->get_results(
        "SELECT p.*, c.church_name 
         FROM $table_name p 
         JOIN $table_churches c ON p.church_code = c.church_code 
         $where_clause 
         ORDER BY p.last_name, p.first_name",
        ARRAY_A
    );
    
    $churches = $wpdb->get_results("SELECT church_id, church_name FROM $table_churches ORDER BY church_name", ARRAY_A);
    
    ?>
    <div class="wrap">
        <h1>Participants</h1>
        
        <div class="tablenav top">
            <div class="alignleft actions">
                <form method="get">
                    <input type="hidden" name="page" value="vaysf-participants">
                    <select name="church_id">
                        <option value="">All Churches</option>
                        <?php foreach ($churches as $church) : ?>
                            <option value="<?php echo esc_attr($church['church_id']); ?>" <?php selected($church_filter, $church['church_id']); ?>>
                                <?php echo esc_html($church['church_name']); ?>
                            </option>
                        <?php endforeach; ?>
                    </select>
                    <input type="submit" class="button" value="Filter">
                </form>
            </div>
            <div class="alignleft actions">
                <a href="<?php echo admin_url('admin.php?page=vaysf-participants&action=sync'); ?>" class="button">Sync Participants</a>
            </div>
            <br class="clear">
        </div>
        
        <table class="wp-list-table widefat fixed striped">
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Church</th>
                    <th>Contact</th>
                    <th>Primary Sport</th>
                    <th>Secondary Sport</th>
                    <th>Status</th> <!-- Changed from Approval Status -->
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                <?php if (empty($participants)) : ?>
                    <tr>
                        <td colspan="7">No participants found.</td>
                    </tr>
                <?php else : ?>
                    <?php foreach ($participants as $participant) : ?>
                        <tr>
                            <td>
                                <?php echo esc_html($participant['first_name'] . ' ' . $participant['last_name']); ?>
                                <?php if (!$participant['is_church_member']) : ?>
                                    <span class="dashicons dashicons-warning" title="Non-member"></span>
                                <?php endif; ?>
                            </td>
                            <td><?php echo esc_html($participant['church_name']); ?></td>
                            <td>
                                <?php echo esc_html($participant['email']); ?><br>
                                <small><?php echo esc_html($participant['phone']); ?></small>
                            </td>
                            <td><?php echo esc_html($participant['primary_sport']); ?></td>
                            <td><?php echo esc_html($participant['secondary_sport']); ?></td>
                            <td>
                                <?php 
                                $status_class = '';
                                switch ($participant['approval_status']) {
                                    case 'approved':
                                        $status_class = 'status-approved';
                                        break;
                                    case 'denied':
                                        $status_class = 'status-denied';
                                        break;
                                    case 'validated':
                                        $status_class = 'status-validated';
                                        break;
                                    case 'pending_approval':
                                        $status_class = 'status-pending-approval';
                                        break;
                                    case 'pending':
                                    default:
                                        $status_class = 'status-pending';
                                        break;
                                }
                                ?>
                                <span class="approval-status <?php echo $status_class; ?>">
                                    <?php echo esc_html(ucwords(str_replace('_', ' ', $participant['approval_status']))); ?>
                                </span>
                            </td>
                            <td>
                                <a href="<?php echo admin_url('admin.php?page=vaysf-participants&action=edit&id=' . $participant['participant_id']); ?>" class="button button-small">Edit</a>
                                <a href="<?php echo admin_url('admin.php?page=vaysf-approvals&participant_id=' . $participant['participant_id']); ?>" class="button button-small">Approvals</a>
                            </td>
                        </tr>
                    <?php endforeach; ?>
                <?php endif; ?>
            </tbody>
        </table>
    </div>
    
    <style>
        .approval-status {
            display: inline-block;
            padding: 5px 10px;
            border-radius: 3px;
            font-weight: bold;
        }
        .status-approved {
            background-color: #d4edda;
            color: #155724;
        }
        .status-denied {
            background-color: #f8d7da;
            color: #721c24;
        }
        .status-validated {
            background-color: #cce5ff;
            color: #004085;
        }
        .status-pending-approval {
            background-color: #fff3cd;
            color: #856404;
        }
        .status-pending {
            background-color: #e2e3e5;
            color: #383d41;
        }
    </style>
    <?php
}
}

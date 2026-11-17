<?php
/**
 * File: admin/class-vaysf-admin-approvals.php
 * Description: Approvals admin page - listing, token generation, resend email
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_Admin_Approvals extends VAYSF_Admin_Page {

    /**
     * Display approvals page
     */
    public function display_approvals_page() {
        global $wpdb;
        
        $table_approvals = $wpdb->prefix . 'sf_approvals';
        $table_participants = $wpdb->prefix . 'sf_participants';
        $table_churches = $wpdb->prefix . 'sf_churches';
        
		// Handle actions. Each one arrives as a GET link signed with
		// nonce_action_url() and is verified before anything is written or
		// sent (Issue #406).
                $action = isset($_GET['action']) ? sanitize_key(wp_unslash($_GET['action'])) : '';

                if ($action === 'generate') {
                        if (!$this->verify_get_action_nonce('vaysf_generate_approvals')) {
                                echo '<div class="notice notice-error"><p>Invalid or expired request. Please click Generate Approval Tokens again.</p></div>';
                        } elseif (vaysf_generate_approvals()) {
                                // Log approval token generation request
                                echo '<div class="notice notice-info"><p>Approval token generation has been logged. The middleware will process this request during its next scheduled run.</p></div>';
                        } else {
                                echo '<div class="notice notice-error"><p>Error logging approval token generation request.</p></div>';
                        }
                } elseif ($action === 'resend' && !empty($_GET['id'])) {
                        $resend_id = absint($_GET['id']);
                        $approval = null;
                        $resend_nonce_ok = $resend_id && $this->verify_get_action_nonce('vaysf_resend_approval_' . $resend_id);
                        if ($resend_nonce_ok) {
                                $approval = $wpdb->get_row(
                                        $wpdb->prepare(
                                                "SELECT a.*, p.first_name, p.last_name, p.approval_status AS participant_approval_status, c.church_name FROM $table_approvals a JOIN $table_participants p ON a.participant_id = p.participant_id JOIN $table_churches c ON a.church_id = c.church_id WHERE a.approval_id = %d",
                                                $resend_id
                                        ),
                                        ARRAY_A
                                );
                        }
                        if (!$resend_nonce_ok) {
                                echo '<div class="notice notice-error"><p>Invalid or expired resend request. Please use the Resend Email button in the list again.</p></div>';
                        } elseif (!$approval) {
                                echo '<div class="notice notice-error"><p>Approval record not found.</p></div>';
                        } elseif ($approval['approval_status'] === 'merged' || $approval['participant_approval_status'] === 'merged') {
                                echo '<div class="notice notice-error"><p>Cannot resend an approval for a merged participant.</p></div>';
                        } else {
                                if (vaysf_resend_approval_email($approval)) {
                                        echo '<div class="notice notice-success"><p>Approval email resent successfully.</p></div>';
                                } else {
                                        echo '<div class="notice notice-error"><p>Failed to resend approval email.</p></div>';
                                }
                        }
                }
        
        // Filter by participant
        $participant_filter = isset($_GET['participant_id']) ? (int) $_GET['participant_id'] : 0;
        $where_clause = $participant_filter ? "WHERE a.participant_id = $participant_filter" : '';
        
        // Get approvals
        $approvals = $wpdb->get_results(
            "SELECT a.*, p.first_name, p.last_name, p.approval_status AS participant_approval_status, c.church_name
            FROM $table_approvals a 
            JOIN $table_participants p ON a.participant_id = p.participant_id 
            JOIN $table_churches c ON a.church_id = c.church_id 
            $where_clause 
            ORDER BY a.created_at DESC",
            ARRAY_A
        );
        
        ?>
        <div class="wrap">
            <h1>Approvals</h1>
            
            <div class="tablenav top">
                <div class="alignleft actions">
                    <a href="<?php echo esc_url($this->nonce_action_url('vaysf-approvals', 'generate', 'vaysf_generate_approvals')); ?>" class="button">Generate Approval Tokens</a>
                </div>
                <br class="clear">
            </div>
            
            <table class="wp-list-table widefat fixed striped">
                <thead>
                    <tr>
                        <th>Participant</th>
                        <th>Church</th>
                        <th>Pastor Email</th>
                        <th>Status</th>
                        <th>Created</th>
                        <th>Expires</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    <?php if (empty($approvals)) : ?>
                        <tr>
                            <td colspan="7">No approvals found.</td>
                        </tr>
                    <?php else : ?>
                        <?php foreach ($approvals as $approval) : ?>
                            <tr>
                                <td><?php echo esc_html($approval['first_name'] . ' ' . $approval['last_name']); ?></td>
                                <td><?php echo esc_html($approval['church_name']); ?></td>
                                <td><?php echo esc_html($approval['pastor_email']); ?></td>
                                <td>
                                    <?php 
                                    $status_class = '';
                                    switch ($approval['approval_status']) {
                                        case 'approved':
                                            $status_class = 'status-approved';
                                            break;
                                        case 'denied':
                                            $status_class = 'status-denied';
                                            break;
                                        case 'merged':
                                            $status_class = 'status-merged';
                                            break;
                                        default:
                                            $status_class = 'status-pending';
                                            break;
                                    }
                                    ?>
                                    <span class="approval-status <?php echo $status_class; ?>">
                                        <?php echo esc_html(ucfirst($approval['approval_status'])); ?>
                                    </span>
                                </td>
                                <td><?php echo esc_html(date('Y-m-d H:i', strtotime($approval['created_at']))); ?></td>
                                <td><?php echo esc_html(date('Y-m-d H:i', strtotime($approval['token_expiry']))); ?></td>
                                <td>
                                    <?php if ($approval['approval_status'] === 'merged' || $approval['participant_approval_status'] === 'merged') : ?>
                                        <span class="description">Merged - resend disabled</span>
                                    <?php else : ?>
                                        <?php
                                        $row_approval_id = absint($approval['approval_id']);
                                        $resend_url = $this->nonce_action_url(
                                            'vaysf-approvals',
                                            'resend',
                                            'vaysf_resend_approval_' . $row_approval_id,
                                            array('id' => $row_approval_id)
                                        );
                                        ?>
                                        <a href="<?php echo esc_url($resend_url); ?>" class="button button-small">Resend Email</a>
                                    <?php endif; ?>
                                </td>
                            </tr>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </tbody>
            </table>
        </div>
        <style>.status-merged { color: #55595c; text-decoration: line-through; }</style>
        <?php
    }
}

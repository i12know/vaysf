<?php
/**
 * File: admin/class-vaysf-admin-churches.php
 * Description: Churches admin page - listing, sync request, and insurance
 *              approve/upload actions (Issue #154)
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_Admin_Churches extends VAYSF_Admin_Page {

    /**
     * Display churches page
     */
    public function display_churches_page() {
        global $wpdb;
        
        $table_name = $wpdb->prefix . 'sf_churches';
        
		// Handle actions
		if (isset($_GET['action']) && $_GET['action'] === 'sync') {
			// Log sync request
			if (vaysf_sync_churches()) {
				echo '<div class="notice notice-info"><p>Sync request for churches has been logged. The middleware will process this request during its next scheduled run.</p></div>';
			} else {
				echo '<div class="notice notice-error"><p>Error logging sync request for churches.</p></div>';
			}
		}

		if (isset($_GET['action']) && $_GET['action'] === 'approve_insurance') {
			$church_id = isset($_GET['id']) ? absint($_GET['id']) : 0;

			if (!current_user_can('manage_options')) {
				echo '<div class="notice notice-error"><p>You are not allowed to approve insurance documents.</p></div>';
			} elseif (!$church_id || !isset($_GET['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_GET['_wpnonce'])), 'vaysf_approve_insurance_' . $church_id)) {
				echo '<div class="notice notice-error"><p>Invalid insurance approval request.</p></div>';
			} else {
				$church = $wpdb->get_row(
					$wpdb->prepare(
						"SELECT church_id, church_name, church_rep_name, church_rep_email, insurance_status, insurance_file_url FROM $table_name WHERE church_id = %d",
						$church_id
					),
					ARRAY_A
				);

				if (!$church) {
					echo '<div class="notice notice-error"><p>Church not found.</p></div>';
				} elseif ($church['insurance_status'] !== 'submitted') {
					echo '<div class="notice notice-warning"><p>Insurance can only be approved after a PDF has been submitted.</p></div>';
				} elseif (empty($church['insurance_file_url'])) {
					echo '<div class="notice notice-warning"><p>Insurance can only be approved after a PDF has been uploaded.</p></div>';
				} else {
					$updated = $wpdb->update(
						$table_name,
						array(
							'insurance_status' => 'approved',
							'updated_at' => current_time('mysql'),
						),
						array('church_id' => $church_id),
						array('%s', '%s'),
						array('%d')
					);

					if ($updated === false) {
						echo '<div class="notice notice-error"><p>Could not approve insurance. Please try again.</p></div>';
					} else {
						$email_sent = vaysf_send_insurance_approved_email($church);

						if ($email_sent) {
							echo '<div class="notice notice-success"><p>Insurance approved for ' . esc_html($church['church_name']) . ', and the Church Rep was notified by email.</p></div>';
						} elseif (!empty($church['church_rep_email'])) {
							echo '<div class="notice notice-warning"><p>Insurance approved for ' . esc_html($church['church_name']) . ', but the approval email could not be sent.</p></div>';
						} else {
							echo '<div class="notice notice-warning"><p>Insurance approved for ' . esc_html($church['church_name']) . ', but no Church Rep email is on file.</p></div>';
						}
					}
				}
			}
		}

		$vaysf_action = isset($_POST['vaysf_action'])
			? sanitize_text_field(wp_unslash($_POST['vaysf_action']))
			: '';

		if ($vaysf_action === 'upload_insurance') {
			$church_id = isset($_POST['church_id']) ? absint($_POST['church_id']) : 0;

			if (!current_user_can('manage_options')) {
				echo '<div class="notice notice-error"><p>You are not allowed to upload insurance documents.</p></div>';
			} elseif (!$church_id || !isset($_POST['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'])), 'vaysf_upload_insurance_' . $church_id)) {
				echo '<div class="notice notice-error"><p>Invalid insurance upload request.</p></div>';
			} elseif (empty($_FILES['insurance_file']) || !isset($_FILES['insurance_file']['tmp_name'])) {
				echo '<div class="notice notice-error"><p>Please choose a PDF file to upload.</p></div>';
			} else {
				$church = $wpdb->get_row(
					$wpdb->prepare(
						"SELECT * FROM $table_name WHERE church_id = %d",
						$church_id
					),
					ARRAY_A
				);

				if (!$church) {
					echo '<div class="notice notice-error"><p>Church not found.</p></div>';
				} else {
					$notify_rep = !empty($_POST['notify_rep']);
					$stored = vaysf_store_insurance_pdf_for_church(
						$church,
						$_FILES['insurance_file'],
						array('notify_rep' => $notify_rep)
					);

					if (is_wp_error($stored)) {
						echo '<div class="notice notice-error"><p>' . esc_html($stored->get_error_message()) . '</p></div>';
					} elseif ($notify_rep && empty($stored['rep_email_sent']) && !empty($church['church_rep_email'])) {
						echo '<div class="notice notice-warning"><p>Insurance PDF uploaded for ' . esc_html($church['church_name']) . ', but the Church Rep notification email could not be sent.</p></div>';
					} elseif ($notify_rep && empty($stored['rep_email_sent'])) {
						echo '<div class="notice notice-warning"><p>Insurance PDF uploaded for ' . esc_html($church['church_name']) . ', but no Church Rep email is on file.</p></div>';
					} else {
						echo '<div class="notice notice-success"><p>Insurance PDF uploaded for ' . esc_html($church['church_name']) . '.</p></div>';
					}
				}
			}
		}
		
        // Get churches
        $churches = $wpdb->get_results("SELECT * FROM $table_name ORDER BY church_name", ARRAY_A);
        
        ?>
        <div class="wrap">
            <h1>Churches</h1>
            
            <div class="tablenav top">
                <div class="alignleft actions">
                    <a href="<?php echo admin_url('admin.php?page=vaysf-churches&action=sync'); ?>" class="button">Sync Churches</a>
                </div>
                <br class="clear">
            </div>
            
            <table class="wp-list-table widefat fixed striped">
                <thead>
                    <tr>
						<th>Church ID</th>
						<th>Church Code</th>
                        <th>Church Name</th>
                        <th>Pastor</th>
                        <th>Church Rep</th>
                        <th>Registration Status</th>
                        <th>Insurance Status</th>
                        <th>Payment Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    <?php if (empty($churches)) : ?>
                        <tr>
                            <td colspan="9">No churches found.</td>
                        </tr>
                    <?php else : ?>
                        <?php foreach ($churches as $church) : ?>
                            <?php
                            // Highlight rows awaiting staff attention (Issue #154).
                            $row_style = ($church['insurance_status'] === 'submitted')
                                ? ' style="background-color:#fff3cd;"'
                                : '';
                            ?>
                            <tr<?php echo $row_style; ?>>
								<td><?php echo esc_html($church['church_id']); ?></td>
								<td><?php echo esc_html($church['church_code']); ?></td>
                                <td><?php echo esc_html($church['church_name']); ?></td>
                                <td>
                                    <?php echo esc_html($church['pastor_name']); ?><br>
                                    <small><?php echo esc_html($church['pastor_email']); ?></small>
                                </td>
                                <td>
                                    <?php echo esc_html($church['church_rep_name']); ?><br>
                                    <small><?php echo esc_html($church['church_rep_email']); ?></small>
                                </td>
                                <td><?php echo esc_html(ucfirst($church['registration_status'])); ?></td>
                                <td>
                                    <?php echo vaysf_format_insurance_status($church['insurance_status']); ?>
                                    <?php if (!empty($church['insurance_uploaded_at'])) : ?>
                                        <br><small><?php echo esc_html(date_i18n('M j, Y g:i A', strtotime($church['insurance_uploaded_at']))); ?></small>
                                    <?php endif; ?>
                                    <?php if (!empty($church['insurance_file_url'])) : ?>
                                        <br><a href="<?php echo esc_url($church['insurance_file_url']); ?>" target="_blank" rel="noopener noreferrer">Download PDF</a>
                                    <?php endif; ?>
                                    <?php if ($church['insurance_status'] === 'submitted' && !empty($church['insurance_file_url'])) : ?>
                                        <?php
                                        $approve_url = wp_nonce_url(
                                            admin_url('admin.php?page=vaysf-churches&action=approve_insurance&id=' . $church['church_id']),
                                            'vaysf_approve_insurance_' . $church['church_id']
                                        );
                                        ?>
                                        <br><a href="<?php echo esc_url($approve_url); ?>" class="button button-small button-primary" onclick="return confirm('Approve this proof of insurance?');">Approve Insurance</a>
                                    <?php endif; ?>
                                    <?php if (current_user_can('manage_options')) : ?>
                                        <?php
                                        $replace_warning = !empty($church['insurance_file_url'])
                                            ? "return confirm('Replace the existing proof-of-insurance PDF for " . esc_js($church['church_name']) . "?');"
                                            : '';
                                        ?>
                                        <form method="post" enctype="multipart/form-data" style="margin-top:8px;" onsubmit="<?php echo esc_attr($replace_warning); ?>">
                                            <?php wp_nonce_field('vaysf_upload_insurance_' . $church['church_id']); ?>
                                            <input type="hidden" name="vaysf_action" value="upload_insurance">
                                            <input type="hidden" name="church_id" value="<?php echo esc_attr($church['church_id']); ?>">
                                            <input type="file" name="insurance_file" accept="application/pdf,.pdf" required style="max-width:180px;">
                                            <label style="display:block;margin-top:4px;">
                                                <input type="checkbox" name="notify_rep" value="1" checked>
                                                <small>Notify rep</small>
                                            </label>
                                            <button type="submit" class="button button-small" style="margin-top:4px;">Upload PDF</button>
                                        </form>
                                    <?php endif; ?>
                                </td>
                                <td><?php echo esc_html(ucfirst($church['payment_status'])); ?></td>
                                <td>
                                    <a href="<?php echo admin_url('admin.php?page=vaysf-churches&action=edit&id=' . $church['church_id']); ?>" class="button button-small">Edit</a>
                                    <a href="<?php echo admin_url('admin.php?page=vaysf-participants&church_id=' . $church['church_id']); ?>" class="button button-small">View Participants</a>
                                </td>
                            </tr>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </tbody>
            </table>
        </div>
        <?php
    }
}

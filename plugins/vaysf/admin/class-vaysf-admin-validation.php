<?php
/**
 * File: admin/class-vaysf-admin-validation.php
 * Description: Validation issues admin page - filters, resolve/reopen, bulk actions
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_Admin_Validation extends VAYSF_Admin_Page {

	/**
	 * Display validation page
	 */
	public function display_validation_page() {
		global $wpdb;
		
		$table_issues = vaysf_get_table_name('validation_issues');
		$table_churches = vaysf_get_table_name('churches');
		$table_participants = vaysf_get_table_name('participants');

		// Handle actions
		if (isset($_GET['action']) && $_GET['action'] === 'validate') {
			// Log validation request
			if (vaysf_validate_data()) {
				echo '<div class="notice notice-info"><p>Data validation request has been logged. The middleware will process this request during its next scheduled run.</p></div>';
			} else {
				echo '<div class="notice notice-error"><p>Error logging data validation request.</p></div>';
			}
		} else if (isset($_GET['action']) && $_GET['action'] === 'resolve' && isset($_GET['id'])) {
			$issue_id = absint($_GET['id']);
			$wpdb->update(
				$table_issues,
				array(
					'status' => 'resolved',
					'resolved_at' => current_time('mysql'),
					'updated_at' => current_time('mysql')
				),
				array('issue_id' => $issue_id),
				array('%s', '%s', '%s'),
				array('%d')
			);
			echo '<div class="notice notice-success"><p>Issue marked as resolved.</p></div>';
		} else if (isset($_GET['action']) && $_GET['action'] === 'reopen' && isset($_GET['id'])) {
			$issue_id = absint($_GET['id']);
			$wpdb->update(
				$table_issues,
				array(
					'status' => 'open',
					'resolved_at' => null,
					'updated_at' => current_time('mysql')
				),
				array('issue_id' => $issue_id),
				array('%s', '%s', '%s'),
				array('%d')
			);
			echo '<div class="notice notice-success"><p>Issue reopened.</p></div>';
		}
		
		// Filter by status
		$status_filter = isset($_GET['status']) ? sanitize_text_field($_GET['status']) : 'open';
		$where_clause = "WHERE i.status = '$status_filter'";
		
		// Filter by church
		$church_filter = isset($_GET['church_id']) ? absint($_GET['church_id']) : 0;
		if ($church_filter > 0) {
			$where_clause .= $wpdb->prepare(" AND i.church_id = %d", $church_filter);
		}
		
		// Filter by severity
		$severity_filter = isset($_GET['severity']) ? sanitize_text_field($_GET['severity']) : '';
		if (!empty($severity_filter)) {
			$where_clause .= $wpdb->prepare(" AND i.severity = %s", $severity_filter);
		}
		
		// Filter by rule level
		$rule_level_filter = isset($_GET['rule_level']) ? sanitize_text_field($_GET['rule_level']) : '';
		if (!empty($rule_level_filter)) {
			$where_clause .= $wpdb->prepare(" AND i.rule_level = %s", $rule_level_filter);
		}
		
		// Filter by sport type
		$sport_type_filter = isset($_GET['sport_type']) ? sanitize_text_field($_GET['sport_type']) : '';
		if (!empty($sport_type_filter)) {
			$where_clause .= $wpdb->prepare(" AND i.sport_type = %s", $sport_type_filter);
		}
		
		// Get issues
		$issues = $wpdb->get_results(
			"SELECT i.*, c.church_name, p.first_name, p.last_name 
			 FROM $table_issues i 
			 JOIN $table_churches c ON i.church_id = c.church_id 
			 LEFT JOIN $table_participants p ON i.participant_id = p.participant_id 
			 $where_clause 
			 ORDER BY i.created_at DESC",
			ARRAY_A
		);
		
		// Get all churches for filter dropdown
		$churches = $wpdb->get_results("SELECT church_id, church_name FROM $table_churches ORDER BY church_name", ARRAY_A);
		
		// Get distinct sport types
		$sport_types = $wpdb->get_col("SELECT DISTINCT sport_type FROM $table_issues WHERE sport_type IS NOT NULL");
		
		?>
		<div class="wrap">
			<h1>Validation Issues</h1>
			
			<div class="tablenav top">
				<div class="alignleft actions">
					<form method="get">
						<input type="hidden" name="page" value="vaysf-validation">
						
						<select name="status">
							<option value="open" <?php selected($status_filter, 'open'); ?>>Open Issues</option>
							<option value="resolved" <?php selected($status_filter, 'resolved'); ?>>Resolved Issues</option>
						</select>
						
						<select name="church_id">
							<option value="">All Churches</option>
							<?php foreach ($churches as $church) : ?>
								<option value="<?php echo esc_attr($church['church_id']); ?>" <?php selected($church_filter, $church['church_id']); ?>>
									<?php echo esc_html($church['church_name']); ?>
								</option>
							<?php endforeach; ?>
						</select>

						<select name="severity">
							<option value="">All Severities</option>
							<option value="ERROR" <?php selected($severity_filter, 'ERROR'); ?>>Error</option>
							<option value="WARNING" <?php selected($severity_filter, 'WARNING'); ?>>Warning</option>
							<option value="INFO" <?php selected($severity_filter, 'INFO'); ?>>Info</option>
						</select>

						<select name="rule_level">
							<option value="">All Levels</option>
							<option value="INDIVIDUAL" <?php selected($rule_level_filter, 'INDIVIDUAL'); ?>>Individual</option>
							<option value="TEAM" <?php selected($rule_level_filter, 'TEAM'); ?>>Team</option>
							<option value="CHURCH" <?php selected($rule_level_filter, 'CHURCH'); ?>>Church</option>
							<option value="TOURNAMENT" <?php selected($rule_level_filter, 'TOURNAMENT'); ?>>Tournament</option>
						</select>

						<?php if (!empty($sport_types)) : ?>
						<select name="sport_type">
							<option value="">All Sports</option>
							<?php foreach ($sport_types as $sport_type) : ?>
								<option value="<?php echo esc_attr($sport_type); ?>" <?php selected($sport_type_filter, $sport_type); ?>>
									<?php echo esc_html($sport_type); ?>
								</option>
							<?php endforeach; ?>
						</select>
						<?php endif; ?>
						
						<input type="submit" class="button" value="Filter">
					</form>
				</div>
				<div class="alignleft actions">
					<a href="<?php echo admin_url('admin.php?page=vaysf-validation&action=validate'); ?>" class="button">Validate Data</a>
					
					<?php if ($status_filter === 'open' && !empty($issues)) : ?>
					<button id="resolve-all-btn" class="button">Resolve All Filtered Issues</button>
					<?php elseif ($status_filter === 'resolved' && !empty($issues)) : ?>
					<button id="reopen-all-btn" class="button">Reopen All Filtered Issues</button>
					<?php endif; ?>
				</div>
				<br class="clear">
			</div>
			
			<table class="wp-list-table widefat fixed striped">
				<thead>
					<tr>
						<th style="width: 30px;"><input type="checkbox" id="select-all"></th>
						<th>Church</th>
						<th>Participant</th>
						<th>Issue Type</th>
						<th>Sport</th>
						<th>Description</th>
						<th>Rule Info</th>
						<th>Severity</th>
						<th>Status</th>
						<th>Created</th>
						<th>Actions</th>
					</tr>
				</thead>
				<tbody>
					<?php if (empty($issues)) : ?>
						<tr>
							<td colspan="11">No validation issues found.</td>
						</tr>
					<?php else : ?>
						<?php foreach ($issues as $issue) : ?>
							<tr data-issue-id="<?php echo esc_attr($issue['issue_id']); ?>">
								<td><input type="checkbox" class="issue-checkbox" value="<?php echo esc_attr($issue['issue_id']); ?>"></td>
								<td><?php echo esc_html($issue['church_name']); ?></td>
								<td>
									<?php
									if ($issue['participant_id']) {
										echo esc_html($issue['first_name'] . ' ' . $issue['last_name']);
									} else {
										echo '<em>Team/Church Issue</em>';
									}
									?>
								</td>
								<td><?php echo esc_html(str_replace('_', ' ', ucfirst($issue['issue_type']))); ?></td>
								<td>
									<?php 
									if ($issue['sport_type']) {
										echo esc_html($issue['sport_type']);
										if ($issue['sport_format']) {
											echo ' (' . esc_html($issue['sport_format']) . ')';
										}
									} else {
										echo '-';
									}
									?>
								</td>
								<td><?php echo esc_html($issue['issue_description']); ?></td>
								<td>
									<?php if ($issue['rule_code']) : ?>
										<span title="<?php echo esc_attr($issue['rule_level'] ?: 'Unknown Level'); ?>">
											<?php echo esc_html($issue['rule_code']); ?>
										</span>
									<?php else : ?>
										-
									<?php endif; ?>
								</td>
								<td>
									<?php
									$severity_class = '';
									switch ($issue['severity']) {
										case 'ERROR':
											$severity_class = 'severity-error';
											break;
										case 'WARNING':
											$severity_class = 'severity-warning';
											break;
										case 'INFO':
											$severity_class = 'severity-info';
											break;
									}
									?>
									<span class="validation-severity <?php echo $severity_class; ?>">
										<?php echo esc_html($issue['severity']); ?>
									</span>
								</td>
								<td>
									<?php
									$status_class = $issue['status'] === 'open' ? 'status-open' : 'status-resolved';
									?>
									<span class="validation-status <?php echo $status_class; ?>">
										<?php echo esc_html(ucfirst($issue['status'])); ?>
									</span>
								</td>
								<td><?php echo esc_html(date('Y-m-d H:i', strtotime($issue['created_at']))); ?></td>
								<td>
									<?php if ($issue['status'] === 'open') : ?>
										<a href="<?php echo admin_url('admin.php?page=vaysf-validation&action=resolve&id=' . $issue['issue_id'] . '&status=' . $status_filter); ?>" class="button button-small">Resolve</a>
									<?php else : ?>
										<a href="<?php echo admin_url('admin.php?page=vaysf-validation&action=reopen&id=' . $issue['issue_id'] . '&status=' . $status_filter); ?>" class="button button-small">Reopen</a>
									<?php endif; ?>
									<?php if ($issue['participant_id']) : ?>
										<a href="<?php echo admin_url('admin.php?page=vaysf-participants&action=edit&id=' . $issue['participant_id']); ?>" class="button button-small">View Participant</a>
									<?php endif; ?>
								</td>
							</tr>
						<?php endforeach; ?>
					<?php endif; ?>
				</tbody>
			</table>
		</div>
		
		<style>
			.validation-status, .validation-severity {
				display: inline-block;
				padding: 3px 6px;
				border-radius: 3px;
				font-weight: bold;
			}
			
			.status-open {
				background-color: #e2e3e5;
				color: #383d41;
			}
			
			.status-resolved {
				background-color: #d4edda;
				color: #155724;
			}
			
			.severity-error {
				background-color: #f8d7da;
				color: #721c24;
			}
			
			.severity-warning {
				background-color: #fff3cd;
				color: #856404;
			}
			
			.severity-info {
				background-color: #cce5ff;
				color: #004085;
			}
		</style>
		
		<script>
		jQuery(document).ready(function($) {
			// Select all functionality
			$('#select-all').on('click', function() {
				$('.issue-checkbox').prop('checked', this.checked);
			});
			
			// Bulk resolve functionality
			$('#resolve-all-btn').on('click', function() {
				const selectedIds = $('.issue-checkbox:checked').map(function() {
					return $(this).val();
				}).get();
				
				if (selectedIds.length === 0) {
					alert('Please select at least one issue to resolve.');
					return;
				}
				
				if (confirm('Are you sure you want to resolve ' + selectedIds.length + ' issues?')) {
					// Construct the REST API endpoint URL
					const apiUrl = '<?php echo rest_url('vaysf/v1/validation-issues/bulk'); ?>';
					
					// Get the nonce
					const nonce = '<?php echo wp_create_nonce('wp_rest'); ?>';
					
					// Make the API request
					$.ajax({
						url: apiUrl,
						method: 'POST',
						beforeSend: function(xhr) {
							xhr.setRequestHeader('X-WP-Nonce', nonce);
						},
						data: {
							issue_ids: selectedIds,
							status: 'resolved'
						},
						success: function(response) {
							alert('Successfully resolved ' + response.updated_count + ' issues.');
							location.reload();
						},
						error: function(xhr) {
							alert('Error: ' + xhr.responseJSON.message);
						}
					});
				}
			});
			
			// Bulk reopen functionality
			$('#reopen-all-btn').on('click', function() {
				const selectedIds = $('.issue-checkbox:checked').map(function() {
					return $(this).val();
				}).get();
				
				if (selectedIds.length === 0) {
					alert('Please select at least one issue to reopen.');
					return;
				}
				
				if (confirm('Are you sure you want to reopen ' + selectedIds.length + ' issues?')) {
					// Construct the REST API endpoint URL
					const apiUrl = '<?php echo rest_url('vaysf/v1/validation-issues/bulk'); ?>';
					
					// Get the nonce
					const nonce = '<?php echo wp_create_nonce('wp_rest'); ?>';
					
					// Make the API request
					$.ajax({
						url: apiUrl,
						method: 'POST',
						beforeSend: function(xhr) {
							xhr.setRequestHeader('X-WP-Nonce', nonce);
						},
						data: {
							issue_ids: selectedIds,
							status: 'open'
						},
						success: function(response) {
							alert('Successfully reopened ' + response.updated_count + ' issues.');
							location.reload();
						},
						error: function(xhr) {
							alert('Error: ' + xhr.responseJSON.message);
						}
					});
				}
			});
		});
		</script>
		<?php
	}
}

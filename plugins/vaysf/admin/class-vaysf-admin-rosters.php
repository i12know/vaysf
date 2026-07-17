<?php
/**
 * File: admin/class-vaysf-admin-rosters.php
 * Description: Rosters admin page - listing with church filter
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_Admin_Rosters extends VAYSF_Admin_Page {

	/**
	 * Display rosters page
	 */
	public function display_rosters_page() {
		global $wpdb;
		
		$table_rosters = $wpdb->prefix . 'sf_rosters';
		$table_participants = $wpdb->prefix . 'sf_participants';
		$table_churches = $wpdb->prefix . 'sf_churches';
		
		$church_filter = isset($_GET['church_code']) ? sanitize_text_field($_GET['church_code']) : '';
		$where_clause = $church_filter ? $wpdb->prepare("WHERE r.church_code = %s", $church_filter) : '';
		
		$rosters = $wpdb->get_results(
			"SELECT r.*, p.first_name, p.last_name, c.church_name 
			 FROM $table_rosters r 
			 JOIN $table_participants p ON r.participant_id = p.participant_id 
			 JOIN $table_churches c ON r.church_code = c.church_code 
			 $where_clause 
			 ORDER BY c.church_name, r.sport_type, r.sport_gender, r.sport_format",
			ARRAY_A
		);
		
		$churches = $wpdb->get_results("SELECT church_code, church_name FROM $table_churches ORDER BY church_name", ARRAY_A);
		
		?>
		<div class="wrap">
			<h1>Rosters</h1>
			
			<div class="tablenav top">
				<div class="alignleft actions">
					<form method="get">
						<input type="hidden" name="page" value="vaysf-rosters">
						<select name="church_code">
							<option value="">All Churches</option>
							<?php foreach ($churches as $church) : ?>
								<option value="<?php echo esc_attr($church['church_code']); ?>" <?php selected($church_filter, $church['church_code']); ?>>
									<?php echo esc_html($church['church_name']); ?>
								</option>
							<?php endforeach; ?>
						</select>
						<input type="submit" class="button" value="Filter">
					</form>
				</div>
				<br class="clear">
			</div>
			
			<table class="wp-list-table widefat fixed striped">
				<thead>
					<tr>
						<th>Church</th>
						<th>Participant</th>
						<th>Sport</th>
						<th>Gender</th>
						<th>Format</th>
						<th>Team</th>
						<th>Partner</th>
						<th>Actions</th>
					</tr>
				</thead>
				<tbody>
					<?php if (empty($rosters)) : ?>
						<tr>
							<td colspan="8">No rosters found.</td>
						</tr>
					<?php else : ?>
						<?php foreach ($rosters as $roster) : ?>
							<tr>
								<td><?php echo esc_html($roster['church_name']); ?></td>
								<td><?php echo esc_html($roster['first_name'] . ' ' . $roster['last_name']); ?></td>
								<td><?php echo esc_html($roster['sport_type']); ?></td>
								<td><?php echo esc_html($roster['sport_gender']); ?></td>
								<td><?php echo esc_html($roster['sport_format']); ?></td>
								<td><?php echo esc_html($roster['team_order'] ?: '-'); ?></td>
								<td><?php echo esc_html($roster['partner_name'] ?: '-'); ?></td>
								<td>
									<a href="<?php echo admin_url('admin.php?page=vaysf-rosters&action=edit&id=' . $roster['roster_id']); ?>" class="button button-small">Edit</a>
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

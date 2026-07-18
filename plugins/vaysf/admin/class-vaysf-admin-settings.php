<?php
/**
 * File: admin/class-vaysf-admin-settings.php
 * Description: Settings admin page - plugin settings registration/rendering and
 *              the event-day results reset section
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_Admin_Settings extends VAYSF_Admin_Page {

    /**
     * Register settings
     */
    public function register_settings() {
        register_setting('vaysf_settings', 'vaysf_token_expiry_days');
        register_setting('vaysf_settings', 'vaysf_email_from');
        register_setting('vaysf_settings', 'vaysf_approval_email_subject');
		register_setting('vaysf_settings', 'vaysf_api_key');
		register_setting('vaysf_settings', 'vaysf_log_emails', array(
			'type' => 'boolean',
			'default' => false,
			'sanitize_callback' => 'rest_sanitize_boolean'
		));
        register_setting('vaysf_settings', 'vaysf_sports_fest_date');        

		add_settings_field(
			'vaysf_log_emails',
			'Log Emails',
			array($this, 'display_field_log_emails'),
			'vaysf_settings',
			'vaysf_section_email'
		);

		add_settings_section(
			'vaysf_section_api',
			'API Settings',
			array($this, 'display_section_api'),
			'vaysf_settings'
		);

        // ADD THIS NEW SECTION:
        add_settings_section(
            'vaysf_section_event',
            'Event Settings', 
            array($this, 'display_section_event'),
            'vaysf_settings'
        );

        // ADD THIS NEW FIELD:
        add_settings_field(
            'vaysf_sports_fest_date',
            'Sports Fest Date',
            array($this, 'display_field_sports_fest_date'),
            'vaysf_settings',
            'vaysf_section_event'
        );

		add_settings_field(
			'vaysf_api_key',
			'API Key',
			array($this, 'display_field_api_key'),
			'vaysf_settings',
			'vaysf_section_api'
		);
        
        add_settings_section(
            'vaysf_section_general',
            'General Settings',
            array($this, 'display_section_general'),
            'vaysf_settings'
        );
        
        add_settings_field(
            'vaysf_token_expiry_days',
            'Token Expiry Days',
            array($this, 'display_field_token_expiry_days'),
            'vaysf_settings',
            'vaysf_section_general'
        );
        
        add_settings_section(
            'vaysf_section_email',
            'Email Settings',
            array($this, 'display_section_email'),
            'vaysf_settings'
        );
        
        add_settings_field(
            'vaysf_email_from',
            'From Email',
            array($this, 'display_field_email_from'),
            'vaysf_settings',
            'vaysf_section_email'
        );
        
        add_settings_field(
            'vaysf_approval_email_subject',
            'Approval Email Subject',
            array($this, 'display_field_approval_email_subject'),
            'vaysf_settings',
            'vaysf_section_email'
        );
    }
    
    /**
     * Display general section
     */
    public function display_section_general() {
        echo '<p>General settings for Sports Fest integration.</p>';
    }
    
    /**
     * Display email section
     */
    public function display_section_email() {
        echo '<p>Email settings for Sports Fest integration.</p>';
    }
    
    /**
     * Display token expiry days field
     */
    public function display_field_token_expiry_days() {
        $value = get_option('vaysf_token_expiry_days', 7);
        echo '<input type="number" name="vaysf_token_expiry_days" value="' . esc_attr($value) . '" min="1" max="30"> days';
        echo '<p class="description">The number of days before a pastor\'s approval token expires.</p>';
    }
    
    /**
     * Display email from field
     */
    public function display_field_email_from() {
        $value = get_option('vaysf_email_from', get_option('admin_email'));
        echo '<input type="email" name="vaysf_email_from" value="' . esc_attr($value) . '" class="regular-text">';
        echo '<p class="description">The email address used as the sender for approval emails.</p>';
    }
    
    /**
     * Display approval email subject field
     */
    public function display_field_approval_email_subject() {
        $value = get_option('vaysf_approval_email_subject', 'Sports Fest 2025: Approval Request');
        echo '<input type="text" name="vaysf_approval_email_subject" value="' . esc_attr($value) . '" class="regular-text">';
        echo '<p class="description">The subject line for pastor approval emails. The participant\'s name will be appended.</p>';
    }

	/**
	 * Display log emails field
	 */
	public function display_field_log_emails() {
		$value = get_option('vaysf_log_emails', false);
		echo '<input type="checkbox" name="vaysf_log_emails" value="1" ' . checked(1, $value, false) . '>';
		echo '<p class="description">If enabled, all emails sent through the API will be logged in the database.</p>';
	}

	/**
	 * Display API settings section
	 */
	public function display_section_api() {
		echo '<p>Settings for the Sports Fest API integration.</p>';
	}

	/**
	 * Display API key field
	 */
	public function display_field_api_key() {
		$api_key = get_option('vaysf_api_key', '');
		
		echo '<input type="text" id="vaysf_api_key" name="vaysf_api_key" value="' . esc_attr($api_key) . '" class="regular-text">';
		echo '<button type="button" id="generate_api_key" class="button">Generate New Key</button>';
		echo '<p class="description">This key is used to authenticate API requests from the middleware. Keep it secret!</p>';
		
		// Add JavaScript to generate API key
		?>
		<script type="text/javascript">
		jQuery(document).ready(function($) {
			$('#generate_api_key').on('click', function() {
				// Generate random API key (32 characters)
				var chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
				var key = '';
				for (var i = 0; i < 32; i++) {
					key += chars.charAt(Math.floor(Math.random() * chars.length));
				}
				
				// Set value in field
				$('#vaysf_api_key').val(key);
			});
		});
		</script>
		<?php
	}
    /**
     * Display settings page
     */
    public function display_settings_page() {
        $results_reset_notice = null;
        $vaysf_action = isset($_POST['vaysf_action'])
            ? sanitize_text_field(wp_unslash($_POST['vaysf_action']))
            : '';

        if ($vaysf_action === 'clear_results_tables') {
            $results_reset_notice = $this->clear_results_tables_from_post();
        }

        ?>
        <div class="wrap">
            <h1>Sports Fest Settings</h1>

            <?php $this->print_admin_notice($results_reset_notice, 'Event-day result tables cleared.'); ?>
            
            <form method="post" action="options.php">
                <?php settings_fields('vaysf_settings'); ?>
                <?php do_settings_sections('vaysf_settings'); ?>
                <?php submit_button(); ?>
            </form>

            <?php $this->display_results_reset_section(); ?>
        </div>
        <?php
    }

    /**
     * Result-entry tables that can be cleared before event-day data entry.
     *
     * @return array<string,string> Label => table name
     */
    private function result_entry_table_names() {
        return array(
            'Result files' => vaysf_get_table_name('result_files'),
            'Result revisions' => vaysf_get_table_name('result_revisions'),
            'Current results' => vaysf_get_table_name('results'),
        );
    }

    /**
     * Count rows in the event-day result tables.
     *
     * @return array<string,int>
     */
    private function result_entry_table_counts() {
        global $wpdb;

        $counts = array();
        foreach ($this->result_entry_table_names() as $label => $table_name) {
            $counts[$label] = (int) $wpdb->get_var("SELECT COUNT(*) FROM {$table_name}");
        }
        $counts['Result-marked schedule rows'] = $this->result_marked_schedule_count();

        return $counts;
    }

    /**
     * Count schedule rows carrying result-derived statuses.
     *
     * @return int
     */
    private function result_marked_schedule_count() {
        global $wpdb;

        $table_schedules = vaysf_get_table_name('schedules');
        return (int) $wpdb->get_var(
            "SELECT COUNT(*)
            FROM {$table_schedules}
            WHERE game_status IN ('in_progress', 'reported', 'official', 'under_review')"
        );
    }

    /**
     * Clear result-entry tables after explicit admin confirmation.
     *
     * @return true|WP_Error
     */
    private function clear_results_tables_from_post() {
        global $wpdb;

        if (!current_user_can('sf2025_admin')) {
            return new WP_Error('vaysf_results_reset_forbidden', 'You are not authorized to clear event-day results.');
        }

        if (
            !isset($_POST['_wpnonce'])
            || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'])), 'vaysf_clear_results_tables')
        ) {
            return new WP_Error('vaysf_results_reset_nonce', 'Security check failed. Please try again.');
        }

        $confirmation = isset($_POST['confirm_clear_results'])
            ? sanitize_text_field(wp_unslash($_POST['confirm_clear_results']))
            : '';
        if ($confirmation !== 'CLEAR RESULTS') {
            return new WP_Error('vaysf_results_reset_confirmation', 'Type CLEAR RESULTS to confirm the reset.');
        }

        $tables = $this->result_entry_table_names();
        $wpdb->query('START TRANSACTION');
        foreach ($tables as $table_name) {
            $deleted = $wpdb->query("DELETE FROM {$table_name}");
            if ($deleted === false) {
                $wpdb->query('ROLLBACK');
                return new WP_Error('vaysf_results_reset_failed', 'Could not clear one of the event-day result tables.');
            }
        }
        $table_schedules = vaysf_get_table_name('schedules');
        $schedule_reset = $wpdb->query(
            $wpdb->prepare(
                "UPDATE {$table_schedules}
                SET game_status = %s, updated_at = %s
                WHERE game_status IN ('in_progress', 'reported', 'official', 'under_review')",
                'scheduled',
                current_time('mysql')
            )
        );
        if ($schedule_reset === false) {
            $wpdb->query('ROLLBACK');
            return new WP_Error('vaysf_results_reset_failed', 'Could not reset schedule result statuses.');
        }
        $wpdb->query('COMMIT');

        return true;
    }

    /**
     * Render maintenance controls for event-day result data.
     */
    private function display_results_reset_section() {
        $counts = $this->result_entry_table_counts();
        ?>
        <hr>
        <h2>Event-Day Results Reset</h2>
        <p>This clears the current score-entry database rows and resets result-marked schedule statuses before coordinators begin Saturday data entry.</p>
        <table class="widefat striped" style="max-width: 520px; margin-bottom: 12px;">
            <thead>
                <tr>
                    <th>Table</th>
                    <th>Current Rows</th>
                </tr>
            </thead>
            <tbody>
                <?php foreach ($counts as $label => $count) : ?>
                    <tr>
                        <td><?php echo esc_html($label); ?></td>
                        <td><?php echo esc_html(number_format_i18n($count)); ?></td>
                    </tr>
                <?php endforeach; ?>
            </tbody>
        </table>
        <form method="post">
            <?php wp_nonce_field('vaysf_clear_results_tables'); ?>
            <input type="hidden" name="vaysf_action" value="clear_results_tables">
            <p>
                <label for="confirm_clear_results">
                    Type <code>CLEAR RESULTS</code> to delete rows from <code>sf_results</code>, <code>sf_result_revisions</code>, and <code>sf_result_files</code>, then reset result-marked schedule rows to <code>scheduled</code>.
                </label>
            </p>
            <p>
                <input type="text" id="confirm_clear_results" name="confirm_clear_results" class="regular-text" autocomplete="off">
            </p>
            <?php submit_button('Clear Event-Day Results Tables', 'delete', 'submit', false); ?>
        </form>
        <?php
    }

    /**
     * Display event settings section
     */
    public function display_section_event() {
        echo '<p>Settings for the Sports Fest event.</p>';
    }

    /**
     * Display sports fest date field
     */
    public function display_field_sports_fest_date() {
        $value = get_option('vaysf_sports_fest_date', '2026-07-18');
        echo '<input type="date" id="vaysf_sports_fest_date" name="vaysf_sports_fest_date" value="' . esc_attr($value) . '" class="regular-text">';
        echo '<p class="description">The date of the Sports Fest event (stored as YYYY-MM-DD).</p>';
    }
}

<?php
/**
 * File: admin/admin.php
 * Description: Admin interface for VAYSF Integration
 * Version: 1.0.6
 * Author: Bumble Ho
 * 		should this be church_code rather than church_name to display particpants?
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_Admin {
    
    /**
     * Constructor
     */
    public function __construct() {
        // Add admin menu
        add_action('admin_menu', array($this, 'add_admin_menu'));
        
        // Register settings
        add_action('admin_init', array($this, 'register_settings'));
    }
    
    /**
     * Add admin menu
     */
    public function add_admin_menu() {
        // Add main menu
        add_menu_page(
            'Sports Fest Integration',
            'Sports Fest',
            'sf2025_read',
            'vaysf',
            array($this, 'display_dashboard_page'),
            'dashicons-shield-alt',
            30
        );
        
        // Add submenu pages
        add_submenu_page(
            'vaysf',
            'Dashboard',
            'Dashboard',
            'sf2025_read',
            'vaysf',
            array($this, 'display_dashboard_page')
        );
        
        add_submenu_page(
            'vaysf',
            'Churches',
            'Churches',
            'sf2025_read',
            'vaysf-churches',
            array($this, 'display_churches_page')
        );
        
        add_submenu_page(
            'vaysf',
            'Participants',
            'Participants',
            'sf2025_read',
            'vaysf-participants',
            array($this, 'display_participants_page')
        );

		add_submenu_page(
			'vaysf',
			'Rosters',
			'Rosters',
			'sf2025_read',
			'vaysf-rosters',
			array($this, 'display_rosters_page')
		);
        
        add_submenu_page(
            'vaysf',
            'Approvals',
            'Approvals',
            'sf2025_read',
            'vaysf-approvals',
            array($this, 'display_approvals_page')
        );
        
        add_submenu_page(
            'vaysf',
            'Validation',
            'Validation',
            'sf2025_read',
            'vaysf-validation',
            array($this, 'display_validation_page')
        );

        add_submenu_page(
            'vaysf',
            'Schedules',
            'Schedules',
            'sf2025_read',
            'vaysf-schedules',
            array($this, 'display_schedules_page')
        );

        add_submenu_page(
            'vaysf',
            'Results',
            'Results',
            'sf2025_read',
            'vaysf-results',
            array($this, 'display_results_page')
        );
        
        add_submenu_page(
            'vaysf',
            'Settings',
            'Settings',
            'sf2025_admin',
            'vaysf-settings',
            array($this, 'display_settings_page')
        );
    }
    
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
    
    /**
     * Display approvals page
     */
    public function display_approvals_page() {
        global $wpdb;
        
        $table_approvals = $wpdb->prefix . 'sf_approvals';
        $table_participants = $wpdb->prefix . 'sf_participants';
        $table_churches = $wpdb->prefix . 'sf_churches';
        
		// Handle actions
                if (isset($_GET['action']) && $_GET['action'] === 'generate') {
                        // Log approval token generation request
                        if (vaysf_generate_approvals()) {
                                echo '<div class="notice notice-info"><p>Approval token generation has been logged. The middleware will process this request during its next scheduled run.</p></div>';
                        } else {
                                echo '<div class="notice notice-error"><p>Error logging approval token generation request.</p></div>';
                        }
                } elseif (isset($_GET['action']) && $_GET['action'] === 'resend' && !empty($_GET['id'])) {
                        $resend_id = absint($_GET['id']);
                        $approval = $wpdb->get_row(
                                $wpdb->prepare(
                                        "SELECT a.*, p.first_name, p.last_name, c.church_name FROM $table_approvals a JOIN $table_participants p ON a.participant_id = p.participant_id JOIN $table_churches c ON a.church_id = c.church_id WHERE a.approval_id = %d",
                                        $resend_id
                                ),
                                ARRAY_A
                        );
                        if ($approval) {
                                if (vaysf_resend_approval_email($approval)) {
                                        echo '<div class="notice notice-success"><p>Approval email resent successfully.</p></div>';
                                } else {
                                        echo '<div class="notice notice-error"><p>Failed to resend approval email.</p></div>';
                                }
                        } else {
                                echo '<div class="notice notice-error"><p>Approval record not found.</p></div>';
                        }
                }
        
        // Filter by participant
        $participant_filter = isset($_GET['participant_id']) ? (int) $_GET['participant_id'] : 0;
        $where_clause = $participant_filter ? "WHERE a.participant_id = $participant_filter" : '';
        
        // Get approvals
        $approvals = $wpdb->get_results(
            "SELECT a.*, p.first_name, p.last_name, c.church_name 
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
                    <a href="<?php echo admin_url('admin.php?page=vaysf-approvals&action=generate'); ?>" class="button">Generate Approval Tokens</a>
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
                                    <a href="<?php echo admin_url('admin.php?page=vaysf-approvals&action=resend&id=' . $approval['approval_id']); ?>" class="button button-small">Resend Email</a>
                                </td>
                            </tr>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </tbody>
            </table>
        </div>
        <?php
    }

    /**
     * Return source_hash fields in the same order as middleware/schedule_publisher.py.
     */
    private function schedule_hash_fields() {
        return array(
            'event', 'stage', 'pool_id', 'round_number',
            'team_a_key', 'team_a_label', 'team_b_key', 'team_b_label',
            'team_c_key', 'team_c_label', 'team_ids_json',
            'resource_id', 'scheduled_slot',
        );
    }

    /**
     * Compute the schedule source hash used by publish-schedule diffing.
     */
    private function compute_schedule_source_hash($row) {
        $subset = array();
        foreach ($this->schedule_hash_fields() as $field) {
            $subset[$field] = array_key_exists($field, $row) ? $row[$field] : null;
        }
        ksort($subset);

        return hash('sha256', wp_json_encode($subset, JSON_UNESCAPED_SLASHES));
    }

    private function schedule_status_options() {
        return array('scheduled', 'in_progress', 'reported', 'official', 'under_review', 'cancelled');
    }

    private function public_status_options() {
        return array('pending', 'in_progress', 'reported', 'official', 'under_review');
    }

    private function scan_status_options() {
        return array('pending', 'uploaded', 'missing', 'not_required');
    }

    private function revision_state_options() {
        return array('unverified', 'verified', 'rejected');
    }

    private function is_protected_schedule_status($status) {
        return in_array($status, array('reported', 'official', 'under_review'), true);
    }

    private function format_game_teams($row) {
        $teams = array();
        foreach (array('team_a_label', 'team_b_label', 'team_c_label') as $field) {
            if (!empty($row[$field])) {
                $teams[] = $row[$field];
            }
        }
        return implode(' vs ', $teams);
    }

    private function textarea_json_value($value) {
        if (is_array($value) || is_object($value)) {
            return wp_json_encode($value, JSON_PRETTY_PRINT);
        }
        return (string) $value;
    }

    private function sanitize_schedule_payload_from_post() {
        $payload = array();
        $text_fields = array(
            'game_key', 'event', 'stage', 'pool_id', 'sub_event',
            'team_a_key', 'team_a_label', 'team_b_key', 'team_b_label',
            'team_c_key', 'team_c_label', 'team_ids_json',
            'resource_id', 'scheduled_slot', 'scheduled_time',
            'scheduled_location', 'game_status',
        );

        foreach ($text_fields as $field) {
            $payload[$field] = isset($_POST[$field])
                ? sanitize_text_field(wp_unslash($_POST[$field]))
                : '';
        }

        // Nullable sf_schedules columns that also feed compute_schedule_source_hash():
        // normalize a blank submission to null (not '') so an admin-edited row hashes
        // the same way middleware/schedule_publisher.py hashes a game whose optional
        // field is simply absent from schedule_input.json (Python .get() -> None ->
        // JSON null). Leaving these as '' would make publish-schedule's diff report
        // every admin-touched row as "changed" even when nothing meaningful changed.
        foreach ($this->schedule_hash_fields() as $field) {
            if ($field !== 'round_number' && $payload[$field] === '') {
                $payload[$field] = null;
            }
        }

        $payload['round_number'] = isset($_POST['round_number']) && $_POST['round_number'] !== ''
            ? absint($_POST['round_number'])
            : null;
        $payload['schedule_version'] = isset($_POST['schedule_version'])
            ? absint($_POST['schedule_version'])
            : 0;
        $payload['synced_to_chmeetings'] = !empty($_POST['synced_to_chmeetings']) ? 1 : 0;

        return $payload;
    }

    private function save_schedule_from_post($schedule_id = 0) {
        global $wpdb;

        if (!current_user_can('sf2025_admin')) {
            return new WP_Error('vaysf_forbidden', 'You are not allowed to modify schedules.');
        }

        $table_schedules = vaysf_get_table_name('schedules');
        $schedule_id = absint($schedule_id);
        $existing = null;

        if ($schedule_id) {
            $existing = $wpdb->get_row(
                $wpdb->prepare("SELECT * FROM $table_schedules WHERE schedule_id = %d", $schedule_id),
                ARRAY_A
            );
            if (!$existing) {
                return new WP_Error('vaysf_schedule_missing', 'Schedule row not found.');
            }
        }

        $payload = $this->sanitize_schedule_payload_from_post();
        if ($payload['game_key'] === '') {
            return new WP_Error('vaysf_schedule_game_key_required', 'Game key is required.');
        }
        if (!in_array($payload['game_status'], $this->schedule_status_options(), true)) {
            return new WP_Error('vaysf_schedule_bad_status', 'Invalid game status.');
        }

        if ($existing && $this->is_protected_schedule_status($existing['game_status']) && empty($_POST['confirm_protected'])) {
            return new WP_Error('vaysf_schedule_protected', 'Protected schedule rows require explicit confirmation before editing.');
        }
        if ($payload['game_status'] === 'cancelled' && empty($_POST['confirm_cancel'])) {
            return new WP_Error('vaysf_schedule_cancel_confirm', 'Cancelling a schedule row requires explicit confirmation.');
        }

        $payload['source_hash'] = $this->compute_schedule_source_hash($payload);
        $payload['updated_at'] = current_time('mysql');

        $data = array(
            'game_key' => $payload['game_key'],
            'schedule_version' => $payload['schedule_version'],
            'event' => $payload['event'],
            'stage' => $payload['stage'],
            'pool_id' => $payload['pool_id'],
            'round_number' => $payload['round_number'],
            'sub_event' => $payload['sub_event'],
            'team_a_key' => $payload['team_a_key'],
            'team_a_label' => $payload['team_a_label'],
            'team_b_key' => $payload['team_b_key'],
            'team_b_label' => $payload['team_b_label'],
            'team_c_key' => $payload['team_c_key'],
            'team_c_label' => $payload['team_c_label'],
            'team_ids_json' => $payload['team_ids_json'],
            'resource_id' => $payload['resource_id'],
            'scheduled_slot' => $payload['scheduled_slot'],
            'scheduled_time' => $payload['scheduled_time'] ?: null,
            'scheduled_location' => $payload['scheduled_location'],
            'game_status' => $payload['game_status'],
            'source_hash' => $payload['source_hash'],
            'synced_to_chmeetings' => $payload['synced_to_chmeetings'],
            'updated_at' => $payload['updated_at'],
        );
        $formats = array(
            '%s', '%d', '%s', '%s', '%s', '%d', '%s',
            '%s', '%s', '%s', '%s', '%s', '%s', '%s',
            '%s', '%s', '%s', '%s', '%s', '%s', '%d', '%s',
        );

        if ($schedule_id) {
            $result = $wpdb->update(
                $table_schedules,
                $data,
                array('schedule_id' => $schedule_id),
                $formats,
                array('%d')
            );
        } else {
            $data['created_at'] = current_time('mysql');
            $formats[] = '%s';
            $result = $wpdb->insert($table_schedules, $data, $formats);
        }

        if ($result === false) {
            return new WP_Error('vaysf_schedule_save_failed', 'Could not save schedule row.');
        }

        return true;
    }

    private function cancel_schedule_from_post($schedule_id) {
        global $wpdb;

        if (!current_user_can('sf2025_admin')) {
            return new WP_Error('vaysf_forbidden', 'You are not allowed to cancel schedules.');
        }
        if (empty($_POST['confirm_cancel'])) {
            return new WP_Error('vaysf_schedule_cancel_confirm', 'Cancelling a schedule row requires explicit confirmation.');
        }

        $table_schedules = vaysf_get_table_name('schedules');
        $schedule = $wpdb->get_row(
            $wpdb->prepare("SELECT * FROM $table_schedules WHERE schedule_id = %d", absint($schedule_id)),
            ARRAY_A
        );
        if (!$schedule) {
            return new WP_Error('vaysf_schedule_missing', 'Schedule row not found.');
        }
        if ($this->is_protected_schedule_status($schedule['game_status']) && empty($_POST['confirm_protected'])) {
            return new WP_Error('vaysf_schedule_protected', 'Protected schedule rows require explicit confirmation before cancellation.');
        }

        $schedule['game_status'] = 'cancelled';
        $schedule['source_hash'] = $this->compute_schedule_source_hash($schedule);

        $result = $wpdb->update(
            $table_schedules,
            array(
                'game_status' => 'cancelled',
                'source_hash' => $schedule['source_hash'],
                'updated_at' => current_time('mysql'),
            ),
            array('schedule_id' => absint($schedule_id)),
            array('%s', '%s', '%s'),
            array('%d')
        );

        if ($result === false) {
            return new WP_Error('vaysf_schedule_cancel_failed', 'Could not cancel schedule row.');
        }

        return true;
    }

    private function print_admin_notice($result, $success_message) {
        if (is_wp_error($result)) {
            echo '<div class="notice notice-error"><p>' . esc_html($result->get_error_message()) . '</p></div>';
        } elseif ($result) {
            echo '<div class="notice notice-success"><p>' . esc_html($success_message) . '</p></div>';
        }
    }

    private function render_schedule_form($schedule = array()) {
        $schedule_id = isset($schedule['schedule_id']) ? absint($schedule['schedule_id']) : 0;
        $action = $schedule_id ? 'save_schedule' : 'create_schedule';
        $nonce_action = $action . '_' . $schedule_id;
        $statuses = $this->schedule_status_options();
        ?>
        <form method="post" class="vaysf-admin-form">
            <?php wp_nonce_field($nonce_action); ?>
            <input type="hidden" name="vaysf_action" value="<?php echo esc_attr($action); ?>">
            <input type="hidden" name="schedule_id" value="<?php echo esc_attr($schedule_id); ?>">
            <table class="form-table" role="presentation">
                <tr>
                    <th><label for="game_key">Game Key</label></th>
                    <td><input name="game_key" id="game_key" class="regular-text" required value="<?php echo esc_attr($schedule['game_key'] ?? ''); ?>"></td>
                </tr>
                <tr>
                    <th><label for="schedule_version">Schedule Version</label></th>
                    <td><input name="schedule_version" id="schedule_version" type="number" min="0" value="<?php echo esc_attr($schedule['schedule_version'] ?? 0); ?>"></td>
                </tr>
                <tr>
                    <th>Event Metadata</th>
                    <td>
                        <input name="event" placeholder="Event" value="<?php echo esc_attr($schedule['event'] ?? ''); ?>">
                        <input name="stage" placeholder="Stage" value="<?php echo esc_attr($schedule['stage'] ?? ''); ?>">
                        <input name="pool_id" placeholder="Pool" value="<?php echo esc_attr($schedule['pool_id'] ?? ''); ?>">
                        <input name="round_number" type="number" min="0" placeholder="Round" value="<?php echo esc_attr($schedule['round_number'] ?? ''); ?>">
                        <input name="sub_event" placeholder="Sub-event" value="<?php echo esc_attr($schedule['sub_event'] ?? ''); ?>">
                    </td>
                </tr>
                <tr>
                    <th>Teams</th>
                    <td>
                        <p><input name="team_a_key" placeholder="Team A key" value="<?php echo esc_attr($schedule['team_a_key'] ?? ''); ?>"> <input class="regular-text" name="team_a_label" placeholder="Team A label" value="<?php echo esc_attr($schedule['team_a_label'] ?? ''); ?>"></p>
                        <p><input name="team_b_key" placeholder="Team B key" value="<?php echo esc_attr($schedule['team_b_key'] ?? ''); ?>"> <input class="regular-text" name="team_b_label" placeholder="Team B label" value="<?php echo esc_attr($schedule['team_b_label'] ?? ''); ?>"></p>
                        <p><input name="team_c_key" placeholder="Team C key" value="<?php echo esc_attr($schedule['team_c_key'] ?? ''); ?>"> <input class="regular-text" name="team_c_label" placeholder="Team C label" value="<?php echo esc_attr($schedule['team_c_label'] ?? ''); ?>"></p>
                        <textarea name="team_ids_json" rows="3" class="large-text code" placeholder='["TEAM-A","TEAM-B"]'><?php echo esc_textarea($schedule['team_ids_json'] ?? ''); ?></textarea>
                    </td>
                </tr>
                <tr>
                    <th>Schedule</th>
                    <td>
                        <input name="resource_id" placeholder="Resource ID" value="<?php echo esc_attr($schedule['resource_id'] ?? ''); ?>">
                        <input name="scheduled_slot" placeholder="Slot" value="<?php echo esc_attr($schedule['scheduled_slot'] ?? ''); ?>">
                        <input name="scheduled_time" placeholder="YYYY-MM-DD HH:MM:SS" value="<?php echo esc_attr($schedule['scheduled_time'] ?? ''); ?>">
                        <input class="regular-text" name="scheduled_location" placeholder="Location" value="<?php echo esc_attr($schedule['scheduled_location'] ?? ''); ?>">
                    </td>
                </tr>
                <tr>
                    <th><label for="game_status">Status</label></th>
                    <td>
                        <select name="game_status" id="game_status">
                            <?php foreach ($statuses as $status) : ?>
                                <option value="<?php echo esc_attr($status); ?>" <?php selected($schedule['game_status'] ?? 'scheduled', $status); ?>><?php echo esc_html($status); ?></option>
                            <?php endforeach; ?>
                        </select>
                        <label><input type="checkbox" name="synced_to_chmeetings" value="1" <?php checked(!empty($schedule['synced_to_chmeetings'])); ?>> Synced to ChMeetings</label>
                    </td>
                </tr>
                <tr>
                    <th>Guards</th>
                    <td>
                        <label><input type="checkbox" name="confirm_protected" value="1"> I understand this may change a protected reported/official/under-review row.</label><br>
                        <label><input type="checkbox" name="confirm_cancel" value="1"> I understand cancelled games follow the force-cancel path and should not be hard-deleted.</label>
                    </td>
                </tr>
            </table>
            <?php submit_button($schedule_id ? 'Save Schedule' : 'Create Schedule'); ?>
        </form>
        <?php
    }

    /**
     * Display event-day schedules admin page.
     */
    public function display_schedules_page() {
        global $wpdb;

        $table_schedules = vaysf_get_table_name('schedules');
        $vaysf_action = isset($_POST['vaysf_action']) ? sanitize_text_field(wp_unslash($_POST['vaysf_action'])) : '';
        $schedule_id = isset($_POST['schedule_id'])
            ? absint($_POST['schedule_id'])
            : (isset($_REQUEST['id']) ? absint($_REQUEST['id']) : 0);

        if ($vaysf_action === 'save_schedule' || $vaysf_action === 'create_schedule') {
            $nonce_action = $vaysf_action . '_' . $schedule_id;
            if (!isset($_POST['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'])), $nonce_action)) {
                $this->print_admin_notice(new WP_Error('vaysf_bad_nonce', 'Invalid schedule request.'), '');
            } else {
                $this->print_admin_notice($this->save_schedule_from_post($schedule_id), 'Schedule saved.');
            }
        } elseif ($vaysf_action === 'cancel_schedule') {
            if (!isset($_POST['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'])), 'cancel_schedule_' . $schedule_id)) {
                $this->print_admin_notice(new WP_Error('vaysf_bad_nonce', 'Invalid schedule cancellation request.'), '');
            } else {
                $this->print_admin_notice($this->cancel_schedule_from_post($schedule_id), 'Schedule cancelled.');
            }
        }

        $action = isset($_GET['action']) ? sanitize_text_field(wp_unslash($_GET['action'])) : '';
        if ($action === 'new' || ($action === 'edit' && $schedule_id)) {
            $schedule = array();
            if ($schedule_id) {
                $schedule = $wpdb->get_row(
                    $wpdb->prepare("SELECT * FROM $table_schedules WHERE schedule_id = %d", $schedule_id),
                    ARRAY_A
                );
            }
            ?>
            <div class="wrap">
                <h1><?php echo $schedule_id ? 'Edit Schedule' : 'Create Schedule'; ?></h1>
                <p><a class="button" href="<?php echo esc_url(admin_url('admin.php?page=vaysf-schedules')); ?>">Back to Schedules</a></p>
                <?php
                if ($schedule_id && !$schedule) {
                    echo '<div class="notice notice-error"><p>Schedule row not found.</p></div>';
                } else {
                    $this->render_schedule_form($schedule ?: array('game_status' => 'scheduled'));
                }
                ?>
            </div>
            <?php
            return;
        }

        $event_filter = isset($_GET['event']) ? sanitize_text_field(wp_unslash($_GET['event'])) : '';
        $status_filter = isset($_GET['game_status']) ? sanitize_text_field(wp_unslash($_GET['game_status'])) : '';
        $version_filter = isset($_GET['schedule_version']) && $_GET['schedule_version'] !== '' ? absint($_GET['schedule_version']) : null;
        $paged = max(1, isset($_GET['paged']) ? absint($_GET['paged']) : 1);
        $per_page = 50;
        $offset = ($paged - 1) * $per_page;

        $where = array();
        $args = array();
        if ($event_filter !== '') {
            $where[] = 'event = %s';
            $args[] = $event_filter;
        }
        if ($status_filter !== '') {
            $where[] = 'game_status = %s';
            $args[] = $status_filter;
        }
        if ($version_filter !== null) {
            $where[] = 'schedule_version = %d';
            $args[] = $version_filter;
        }
        $where_clause = $where ? 'WHERE ' . implode(' AND ', $where) : '';

        $count_sql = "SELECT COUNT(*) FROM $table_schedules $where_clause";
        $total_items = $args ? (int) $wpdb->get_var($wpdb->prepare($count_sql, $args)) : (int) $wpdb->get_var($count_sql);
        $query_args = array_merge($args, array($per_page, $offset));
        $query_sql = "SELECT * FROM $table_schedules $where_clause ORDER BY schedule_version DESC, scheduled_time IS NULL, scheduled_time, schedule_id LIMIT %d OFFSET %d";
        $schedules = $wpdb->get_results($wpdb->prepare($query_sql, $query_args), ARRAY_A);
        $events = $wpdb->get_col("SELECT DISTINCT event FROM $table_schedules WHERE event IS NOT NULL AND event <> '' ORDER BY event");
        $versions = $wpdb->get_col("SELECT DISTINCT schedule_version FROM $table_schedules ORDER BY schedule_version DESC");
        $total_pages = max(1, (int) ceil($total_items / $per_page));
        ?>
        <div class="wrap">
            <h1>Schedules <a href="<?php echo esc_url(admin_url('admin.php?page=vaysf-schedules&action=new')); ?>" class="page-title-action">Add New</a></h1>
            <form method="get" class="tablenav top">
                <input type="hidden" name="page" value="vaysf-schedules">
                <select name="event">
                    <option value="">All events</option>
                    <?php foreach ($events as $event) : ?>
                        <option value="<?php echo esc_attr($event); ?>" <?php selected($event_filter, $event); ?>><?php echo esc_html($event); ?></option>
                    <?php endforeach; ?>
                </select>
                <select name="game_status">
                    <option value="">All statuses</option>
                    <?php foreach ($this->schedule_status_options() as $status) : ?>
                        <option value="<?php echo esc_attr($status); ?>" <?php selected($status_filter, $status); ?>><?php echo esc_html($status); ?></option>
                    <?php endforeach; ?>
                </select>
                <select name="schedule_version">
                    <option value="">All versions</option>
                    <?php foreach ($versions as $version) : ?>
                        <option value="<?php echo esc_attr($version); ?>" <?php selected((string) $version_filter, (string) $version); ?>><?php echo esc_html($version); ?></option>
                    <?php endforeach; ?>
                </select>
                <input type="submit" class="button" value="Filter">
            </form>
            <table class="wp-list-table widefat fixed striped">
                <thead>
                    <tr>
                        <th>Game Key</th>
                        <th>Event / Stage / Pool</th>
                        <th>Teams</th>
                        <th>Resource / Slot</th>
                        <th>Status</th>
                        <th>Published</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    <?php if (!$schedules) : ?>
                        <tr><td colspan="7">No schedule rows found.</td></tr>
                    <?php else : ?>
                        <?php foreach ($schedules as $schedule) : ?>
                            <tr>
                                <td><strong><?php echo esc_html($schedule['game_key']); ?></strong><br><small>ID <?php echo esc_html($schedule['schedule_id']); ?> | v<?php echo esc_html($schedule['schedule_version']); ?></small></td>
                                <td><?php echo esc_html($schedule['event']); ?><br><small><?php echo esc_html(trim(($schedule['stage'] ?: '') . ' ' . ($schedule['pool_id'] ?: ''))); ?></small></td>
                                <td><?php echo esc_html($this->format_game_teams($schedule)); ?></td>
                                <td><?php echo esc_html($schedule['resource_id']); ?><br><small><?php echo esc_html($schedule['scheduled_slot']); ?></small></td>
                                <td><?php echo esc_html($schedule['game_status']); ?></td>
                                <td><?php echo esc_html($schedule['published_at'] ?: '-'); ?></td>
                                <td>
                                    <a class="button button-small" href="<?php echo esc_url(admin_url('admin.php?page=vaysf-schedules&action=edit&id=' . $schedule['schedule_id'])); ?>">Edit</a>
                                    <?php if ($schedule['game_status'] !== 'cancelled') : ?>
                                        <?php
                                        $row_is_protected = $this->is_protected_schedule_status($schedule['game_status']);
                                        $cancel_confirm_message = $row_is_protected
                                            ? sprintf(
                                                'This game is currently "%s" (protected — reported/official/under review). '
                                                . 'Cancelling it marks a completed or in-review match as cancelled. '
                                                . 'This does not hard-delete it, but is a significant action. Continue?',
                                                $schedule['game_status']
                                            )
                                            : 'Cancel this schedule row? This does not hard-delete it.';
                                        ?>
                                        <form method="post" style="display:inline;">
                                            <?php wp_nonce_field('cancel_schedule_' . $schedule['schedule_id']); ?>
                                            <input type="hidden" name="vaysf_action" value="cancel_schedule">
                                            <input type="hidden" name="id" value="<?php echo esc_attr($schedule['schedule_id']); ?>">
                                            <input type="hidden" name="confirm_cancel" value="1">
                                            <?php if ($row_is_protected) : ?>
                                                <input type="hidden" name="confirm_protected" value="1">
                                            <?php endif; ?>
                                            <button type="submit" class="button button-small<?php echo $row_is_protected ? ' button-link-delete' : ''; ?>" onclick="return confirm('<?php echo esc_js($cancel_confirm_message); ?>');"><?php echo $row_is_protected ? 'Cancel (protected)' : 'Cancel'; ?></button>
                                        </form>
                                    <?php endif; ?>
                                </td>
                            </tr>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </tbody>
            </table>
            <div class="tablenav bottom">
                <div class="tablenav-pages">
                    <span class="displaying-num"><?php echo esc_html($total_items); ?> row(s)</span>
                    <?php
                    $base_args = array(
                        'page' => 'vaysf-schedules',
                        'event' => $event_filter,
                        'game_status' => $status_filter,
                    );
                    if ($version_filter !== null) {
                        $base_args['schedule_version'] = $version_filter;
                    }
                    if ($paged > 1) {
                        echo '<a class="button" href="' . esc_url(add_query_arg(array_merge($base_args, array('paged' => $paged - 1)), admin_url('admin.php'))) . '">&laquo; Previous</a> ';
                    }
                    echo '<span class="paging-input">Page ' . esc_html($paged) . ' of ' . esc_html($total_pages) . '</span>';
                    if ($paged < $total_pages) {
                        echo ' <a class="button" href="' . esc_url(add_query_arg(array_merge($base_args, array('paged' => $paged + 1)), admin_url('admin.php'))) . '">Next &raquo;</a>';
                    }
                    ?>
                </div>
            </div>
        </div>
        <?php
    }

    private function result_payload_from_post() {
        return array(
            'schedule_id' => isset($_POST['schedule_id']) ? absint($_POST['schedule_id']) : 0,
            'score_json' => isset($_POST['score_json']) ? wp_unslash($_POST['score_json']) : '',
            'winner_keys_json' => isset($_POST['winner_keys_json']) ? wp_unslash($_POST['winner_keys_json']) : '',
            'correction_reason' => isset($_POST['correction_reason']) ? sanitize_textarea_field(wp_unslash($_POST['correction_reason'])) : '',
            'public_status' => isset($_POST['public_status']) ? sanitize_text_field(wp_unslash($_POST['public_status'])) : 'pending',
            'scan_status' => isset($_POST['scan_status']) ? sanitize_text_field(wp_unslash($_POST['scan_status'])) : 'pending',
            'notes' => isset($_POST['notes']) ? sanitize_textarea_field(wp_unslash($_POST['notes'])) : '',
            'verification_state' => isset($_POST['verification_state']) ? sanitize_text_field(wp_unslash($_POST['verification_state'])) : 'unverified',
        );
    }

    /**
     * A blank value is allowed (score_json/winner_keys_json are nullable and
     * legitimately empty before a result is submitted); a non-blank value must
     * be valid JSON so sf_results never persists a string a downstream reader
     * (public display, middleware) would fail to json_decode().
     */
    private function validate_json_field($value, $label) {
        $value = trim((string) $value);
        if ($value === '') {
            return null;
        }
        json_decode($value);
        if (json_last_error() !== JSON_ERROR_NONE) {
            return new WP_Error(
                'vaysf_result_invalid_json',
                sprintf('%s must be valid JSON: %s', $label, json_last_error_msg())
            );
        }
        return null;
    }

    private function save_result_correction_from_post($result_id = 0) {
        global $wpdb;

        if (!current_user_can('sf2025_admin')) {
            return new WP_Error('vaysf_forbidden', 'You are not allowed to modify results.');
        }

        $table_results = vaysf_get_table_name('results');
        $table_revisions = vaysf_get_table_name('result_revisions');
        $table_schedules = vaysf_get_table_name('schedules');
        $payload = $this->result_payload_from_post();
        $result_id = absint($result_id);

        if (!$payload['schedule_id']) {
            return new WP_Error('vaysf_result_schedule_required', 'Schedule row is required.');
        }
        if (!in_array($payload['public_status'], $this->public_status_options(), true)) {
            return new WP_Error('vaysf_result_public_status', 'Invalid public status.');
        }
        if (!in_array($payload['scan_status'], $this->scan_status_options(), true)) {
            return new WP_Error('vaysf_result_scan_status', 'Invalid scan status.');
        }
        if (!in_array($payload['verification_state'], $this->revision_state_options(), true)) {
            return new WP_Error('vaysf_result_revision_state', 'Invalid revision state.');
        }

        foreach (array('score_json' => 'Score JSON', 'winner_keys_json' => 'Winner Keys JSON') as $json_field => $json_label) {
            $json_error = $this->validate_json_field($payload[$json_field], $json_label);
            if (is_wp_error($json_error)) {
                return $json_error;
            }
        }

        $schedule_exists = $wpdb->get_var(
            $wpdb->prepare("SELECT COUNT(*) FROM $table_schedules WHERE schedule_id = %d", $payload['schedule_id'])
        );
        if (!$schedule_exists) {
            return new WP_Error('vaysf_result_schedule_missing', 'Schedule row not found.');
        }

        $existing = null;
        if ($result_id) {
            $existing = $wpdb->get_row(
                $wpdb->prepare("SELECT * FROM $table_results WHERE result_id = %d", $result_id),
                ARRAY_A
            );
            if (!$existing) {
                return new WP_Error('vaysf_result_missing', 'Result row not found.');
            }
        } else {
            $existing = $wpdb->get_row(
                $wpdb->prepare("SELECT * FROM $table_results WHERE schedule_id = %d", $payload['schedule_id']),
                ARRAY_A
            );
            if ($existing) {
                return new WP_Error('vaysf_result_duplicate', 'A result already exists for this schedule row. Edit the existing result instead.');
            }
        }

        $now = current_time('mysql');
        $user_id = get_current_user_id();
        $wpdb->query('START TRANSACTION');

        if ($existing) {
            $result_id = absint($existing['result_id']);
            $next_revision = absint($existing['current_revision']) + 1;
        } else {
            $inserted = $wpdb->insert(
                $table_results,
                array(
                    'schedule_id' => $payload['schedule_id'],
                    'score_json' => $payload['score_json'],
                    'winner_keys_json' => $payload['winner_keys_json'],
                    'submitted_by_user_id' => $user_id,
                    'current_revision' => 0,
                    'correction_reason' => $payload['correction_reason'],
                    'public_status' => $payload['public_status'],
                    'scan_status' => $payload['scan_status'],
                    'notes' => $payload['notes'],
                    'created_at' => $now,
                    'updated_at' => $now,
                ),
                array('%d', '%s', '%s', '%d', '%d', '%s', '%s', '%s', '%s', '%s', '%s')
            );
            if ($inserted === false) {
                $wpdb->query('ROLLBACK');
                return new WP_Error('vaysf_result_create_failed', 'Could not create result row.');
            }
            $result_id = absint($wpdb->insert_id);
            $next_revision = 1;
        }

        $revision_inserted = $wpdb->insert(
            $table_revisions,
            array(
                'result_id' => $result_id,
                'revision_number' => $next_revision,
                'score_json' => $payload['score_json'],
                'winner_keys_json' => $payload['winner_keys_json'],
                'notes' => $payload['notes'],
                'correction_reason' => $payload['correction_reason'],
                'submitted_by_user_id' => $user_id,
                'submitted_at' => $now,
                'verification_state' => $payload['verification_state'],
                'source_ip' => isset($_SERVER['REMOTE_ADDR']) ? sanitize_text_field(wp_unslash($_SERVER['REMOTE_ADDR'])) : '',
                'request_metadata' => wp_json_encode(array('source' => 'wp-admin', 'user_id' => $user_id)),
            ),
            array('%d', '%d', '%s', '%s', '%s', '%s', '%d', '%s', '%s', '%s', '%s')
        );

        if ($revision_inserted === false) {
            $wpdb->query('ROLLBACK');
            return new WP_Error('vaysf_revision_create_failed', 'Could not append result revision.');
        }

        $updated = $wpdb->update(
            $table_results,
            array(
                'schedule_id' => $payload['schedule_id'],
                'score_json' => $payload['score_json'],
                'winner_keys_json' => $payload['winner_keys_json'],
                'submitted_by_user_id' => $user_id,
                'current_revision' => $next_revision,
                'correction_reason' => $payload['correction_reason'],
                'public_status' => $payload['public_status'],
                'scan_status' => $payload['scan_status'],
                'notes' => $payload['notes'],
                'updated_at' => $now,
            ),
            array('result_id' => $result_id),
            array('%d', '%s', '%s', '%d', '%d', '%s', '%s', '%s', '%s', '%s'),
            array('%d')
        );

        if ($updated === false) {
            $wpdb->query('ROLLBACK');
            return new WP_Error('vaysf_result_update_failed', 'Could not update current result row.');
        }

        $wpdb->query('COMMIT');
        return true;
    }

    private function verify_result_from_post($result_id, $mode) {
        global $wpdb;

        if (!current_user_can('sf2025_admin')) {
            return new WP_Error('vaysf_forbidden', 'You are not allowed to verify results.');
        }

        $data = array('updated_at' => current_time('mysql'));
        $formats = array('%s');
        if ($mode === 'verify') {
            $data['verified_by_user_id'] = get_current_user_id();
            $data['verified_at'] = current_time('mysql');
            $formats[] = '%d';
            $formats[] = '%s';
        } elseif ($mode === 'certify') {
            $data['certified_at'] = current_time('mysql');
            $formats[] = '%s';
        } else {
            return new WP_Error('vaysf_bad_result_action', 'Invalid result action.');
        }

        $updated = $wpdb->update(
            vaysf_get_table_name('results'),
            $data,
            array('result_id' => absint($result_id)),
            $formats,
            array('%d')
        );

        if ($updated === false) {
            return new WP_Error('vaysf_result_verify_failed', 'Could not update result verification state.');
        }

        return true;
    }

    private function render_result_form($result = array()) {
        global $wpdb;

        $result_id = isset($result['result_id']) ? absint($result['result_id']) : 0;
        $action = $result_id ? 'save_result' : 'create_result';
        $nonce_action = $action . '_' . $result_id;
        $schedules = $wpdb->get_results(
            "SELECT schedule_id, game_key, event, team_a_label, team_b_label, team_c_label FROM " . vaysf_get_table_name('schedules') . " ORDER BY schedule_version DESC, game_key LIMIT 500",
            ARRAY_A
        );
        ?>
        <form method="post" class="vaysf-admin-form">
            <?php wp_nonce_field($nonce_action); ?>
            <input type="hidden" name="vaysf_action" value="<?php echo esc_attr($action); ?>">
            <input type="hidden" name="result_id" value="<?php echo esc_attr($result_id); ?>">
            <table class="form-table" role="presentation">
                <tr>
                    <th><label for="schedule_id">Schedule Row</label></th>
                    <td>
                        <select name="schedule_id" id="schedule_id" required>
                            <option value="">Choose a game</option>
                            <?php foreach ($schedules as $schedule) : ?>
                                <?php $label = $schedule['game_key'] . ' - ' . $schedule['event'] . ' - ' . $this->format_game_teams($schedule); ?>
                                <option value="<?php echo esc_attr($schedule['schedule_id']); ?>" <?php selected($result['schedule_id'] ?? '', $schedule['schedule_id']); ?>><?php echo esc_html($label); ?></option>
                            <?php endforeach; ?>
                        </select>
                    </td>
                </tr>
                <tr>
                    <th><label for="score_json">Score JSON</label></th>
                    <td><textarea name="score_json" id="score_json" rows="5" class="large-text code"><?php echo esc_textarea($this->textarea_json_value($result['score_json'] ?? '')); ?></textarea></td>
                </tr>
                <tr>
                    <th><label for="winner_keys_json">Winner Keys JSON</label></th>
                    <td><textarea name="winner_keys_json" id="winner_keys_json" rows="3" class="large-text code"><?php echo esc_textarea($this->textarea_json_value($result['winner_keys_json'] ?? '')); ?></textarea></td>
                </tr>
                <tr>
                    <th>Status</th>
                    <td>
                        <select name="public_status">
                            <?php foreach ($this->public_status_options() as $status) : ?>
                                <option value="<?php echo esc_attr($status); ?>" <?php selected($result['public_status'] ?? 'pending', $status); ?>><?php echo esc_html($status); ?></option>
                            <?php endforeach; ?>
                        </select>
                        <select name="scan_status">
                            <?php foreach ($this->scan_status_options() as $status) : ?>
                                <option value="<?php echo esc_attr($status); ?>" <?php selected($result['scan_status'] ?? 'pending', $status); ?>><?php echo esc_html($status); ?></option>
                            <?php endforeach; ?>
                        </select>
                        <select name="verification_state">
                            <?php foreach ($this->revision_state_options() as $state) : ?>
                                <option value="<?php echo esc_attr($state); ?>"><?php echo esc_html($state); ?></option>
                            <?php endforeach; ?>
                        </select>
                    </td>
                </tr>
                <tr>
                    <th><label for="correction_reason">Correction Reason</label></th>
                    <td><textarea name="correction_reason" id="correction_reason" rows="3" class="large-text"><?php echo esc_textarea($result['correction_reason'] ?? ''); ?></textarea></td>
                </tr>
                <tr>
                    <th><label for="notes">Notes</label></th>
                    <td><textarea name="notes" id="notes" rows="3" class="large-text"><?php echo esc_textarea($result['notes'] ?? ''); ?></textarea></td>
                </tr>
            </table>
            <?php submit_button($result_id ? 'Save Correction' : 'Create Result'); ?>
        </form>
        <?php
    }

    /**
     * Display event-day results and revision history admin page.
     */
    public function display_results_page() {
        global $wpdb;

        $table_results = vaysf_get_table_name('results');
        $table_schedules = vaysf_get_table_name('schedules');
        $table_revisions = vaysf_get_table_name('result_revisions');
        $table_files = vaysf_get_table_name('result_files');
        $vaysf_action = isset($_POST['vaysf_action']) ? sanitize_text_field(wp_unslash($_POST['vaysf_action'])) : '';
        $result_id = isset($_POST['result_id'])
            ? absint($_POST['result_id'])
            : (isset($_REQUEST['id']) ? absint($_REQUEST['id']) : 0);

        if ($vaysf_action === 'save_result' || $vaysf_action === 'create_result') {
            $nonce_action = $vaysf_action . '_' . $result_id;
            if (!isset($_POST['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'])), $nonce_action)) {
                $this->print_admin_notice(new WP_Error('vaysf_bad_nonce', 'Invalid result request.'), '');
            } else {
                $this->print_admin_notice($this->save_result_correction_from_post($result_id), $result_id ? 'Result correction saved and revision appended.' : 'Result created and revision appended.');
            }
        } elseif ($vaysf_action === 'verify_result' || $vaysf_action === 'certify_result') {
            $mode = $vaysf_action === 'verify_result' ? 'verify' : 'certify';
            if (!isset($_POST['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'])), $vaysf_action . '_' . $result_id)) {
                $this->print_admin_notice(new WP_Error('vaysf_bad_nonce', 'Invalid verification request.'), '');
            } else {
                $this->print_admin_notice($this->verify_result_from_post($result_id, $mode), ucfirst($mode) . ' action saved.');
            }
        }

        $action = isset($_GET['action']) ? sanitize_text_field(wp_unslash($_GET['action'])) : '';
        if ($action === 'new' || ($action === 'edit' && $result_id)) {
            $result = array();
            if ($result_id) {
                $result = $wpdb->get_row(
                    $wpdb->prepare("SELECT * FROM $table_results WHERE result_id = %d", $result_id),
                    ARRAY_A
                );
            }
            ?>
            <div class="wrap">
                <h1><?php echo $result_id ? 'Edit Result' : 'Create Result'; ?></h1>
                <p><a class="button" href="<?php echo esc_url(admin_url('admin.php?page=vaysf-results')); ?>">Back to Results</a></p>
                <?php
                if ($result_id && !$result) {
                    echo '<div class="notice notice-error"><p>Result row not found.</p></div>';
                } else {
                    $this->render_result_form($result);
                }
                ?>
            </div>
            <?php
            return;
        }

        if ($action === 'revisions' && $result_id) {
            $result = $wpdb->get_row(
                $wpdb->prepare(
                    "SELECT r.*, s.game_key, s.event FROM $table_results r LEFT JOIN $table_schedules s ON r.schedule_id = s.schedule_id WHERE r.result_id = %d",
                    $result_id
                ),
                ARRAY_A
            );
            $revisions = $wpdb->get_results(
                $wpdb->prepare("SELECT * FROM $table_revisions WHERE result_id = %d ORDER BY revision_number DESC", $result_id),
                ARRAY_A
            );
            $files = $wpdb->get_results(
                $wpdb->prepare(
                    "SELECT f.*, rr.revision_id, rr.revision_number
                    FROM $table_files f
                    INNER JOIN $table_revisions rr ON rr.revision_id = f.result_revision_id
                    WHERE rr.result_id = %d
                    ORDER BY rr.revision_number DESC, f.uploaded_at DESC",
                    $result_id
                ),
                ARRAY_A
            );
            $files_by_revision = array();
            if (is_array($files)) {
                foreach ($files as $file) {
                    $revision_key = absint($file['revision_id']);
                    if (!isset($files_by_revision[$revision_key])) {
                        $files_by_revision[$revision_key] = array();
                    }
                    $files_by_revision[$revision_key][] = $file;
                }
            }
            ?>
            <div class="wrap">
                <h1>Result Revision History</h1>
                <p><a class="button" href="<?php echo esc_url(admin_url('admin.php?page=vaysf-results')); ?>">Back to Results</a></p>
                <?php if (!$result) : ?>
                    <div class="notice notice-error"><p>Result row not found.</p></div>
                <?php else : ?>
                    <h2><?php echo esc_html($result['game_key'] . ' - ' . $result['event']); ?></h2>
                    <table class="wp-list-table widefat fixed striped">
                        <thead>
                            <tr>
                                <th>Revision</th>
                                <th>Score</th>
                                <th>Winner Keys</th>
                                <th>State</th>
                                <th>Reason / Notes</th>
                                <th>Files</th>
                                <th>Submitted</th>
                            </tr>
                        </thead>
                        <tbody>
                            <?php if (!$revisions) : ?>
                                <tr><td colspan="7">No revisions found.</td></tr>
                            <?php else : ?>
                                <?php foreach ($revisions as $revision) : ?>
                                    <tr>
                                        <td><?php echo esc_html($revision['revision_number']); ?></td>
                                        <td><pre><?php echo esc_html($revision['score_json']); ?></pre></td>
                                        <td><pre><?php echo esc_html($revision['winner_keys_json']); ?></pre></td>
                                        <td><?php echo esc_html($revision['verification_state']); ?></td>
                                        <td><?php echo esc_html($revision['correction_reason']); ?><br><small><?php echo esc_html($revision['notes']); ?></small></td>
                                        <td>
                                            <?php $revision_files = $files_by_revision[absint($revision['revision_id'])] ?? array(); ?>
                                            <?php if (!$revision_files) : ?>
                                                -
                                            <?php else : ?>
                                                <?php foreach ($revision_files as $file) : ?>
                                                    <div>
                                                        <?php echo esc_html($file['original_filename']); ?><br>
                                                        <small><?php echo esc_html(size_format(absint($file['byte_size']))); ?></small>
                                                        <a href="<?php echo esc_url(vaysf_get_result_file_view_url($file['file_id'])); ?>" target="_blank" rel="noopener noreferrer">View</a>
                                                        |
                                                        <a href="<?php echo esc_url(vaysf_get_result_file_download_url($file['file_id'])); ?>">Download</a>
                                                    </div>
                                                <?php endforeach; ?>
                                            <?php endif; ?>
                                        </td>
                                        <td><?php echo esc_html($revision['submitted_at']); ?><br><small>User <?php echo esc_html($revision['submitted_by_user_id']); ?></small></td>
                                    </tr>
                                <?php endforeach; ?>
                            <?php endif; ?>
                        </tbody>
                    </table>
                <?php endif; ?>
            </div>
            <?php
            return;
        }

        $public_filter = isset($_GET['public_status']) ? sanitize_text_field(wp_unslash($_GET['public_status'])) : '';
        $event_filter = isset($_GET['event']) ? sanitize_text_field(wp_unslash($_GET['event'])) : '';
        $where = array();
        $args = array();
        if ($public_filter !== '') {
            $where[] = 'r.public_status = %s';
            $args[] = $public_filter;
        }
        if ($event_filter !== '') {
            $where[] = 's.event = %s';
            $args[] = $event_filter;
        }
        $where_clause = $where ? 'WHERE ' . implode(' AND ', $where) : '';
        $query_sql = "SELECT r.*, s.game_key, s.event, s.stage, s.team_a_label, s.team_b_label, s.team_c_label FROM $table_results r LEFT JOIN $table_schedules s ON r.schedule_id = s.schedule_id $where_clause ORDER BY r.updated_at DESC, r.result_id DESC LIMIT 200";
        $results = $args ? $wpdb->get_results($wpdb->prepare($query_sql, $args), ARRAY_A) : $wpdb->get_results($query_sql, ARRAY_A);
        $events = $wpdb->get_col("SELECT DISTINCT event FROM $table_schedules WHERE event IS NOT NULL AND event <> '' ORDER BY event");
        ?>
        <div class="wrap">
            <h1>Results <a href="<?php echo esc_url(admin_url('admin.php?page=vaysf-results&action=new')); ?>" class="page-title-action">Add New</a></h1>
            <form method="get" class="tablenav top">
                <input type="hidden" name="page" value="vaysf-results">
                <select name="event">
                    <option value="">All events</option>
                    <?php foreach ($events as $event) : ?>
                        <option value="<?php echo esc_attr($event); ?>" <?php selected($event_filter, $event); ?>><?php echo esc_html($event); ?></option>
                    <?php endforeach; ?>
                </select>
                <select name="public_status">
                    <option value="">All statuses</option>
                    <?php foreach ($this->public_status_options() as $status) : ?>
                        <option value="<?php echo esc_attr($status); ?>" <?php selected($public_filter, $status); ?>><?php echo esc_html($status); ?></option>
                    <?php endforeach; ?>
                </select>
                <input type="submit" class="button" value="Filter">
            </form>
            <table class="wp-list-table widefat fixed striped">
                <thead>
                    <tr>
                        <th>Game</th>
                        <th>Teams</th>
                        <th>Status</th>
                        <th>Revision</th>
                        <th>Certified / Verified</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    <?php if (!$results) : ?>
                        <tr><td colspan="6">No results found.</td></tr>
                    <?php else : ?>
                        <?php foreach ($results as $result) : ?>
                            <tr>
                                <td><strong><?php echo esc_html($result['game_key']); ?></strong><br><small><?php echo esc_html($result['event']); ?></small></td>
                                <td><?php echo esc_html($this->format_game_teams($result)); ?></td>
                                <td><?php echo esc_html($result['public_status']); ?><br><small>Scan: <?php echo esc_html($result['scan_status']); ?></small></td>
                                <td><?php echo esc_html($result['current_revision']); ?></td>
                                <td><?php echo esc_html($result['certified_at'] ?: '-'); ?><br><small><?php echo esc_html($result['verified_at'] ?: '-'); ?></small></td>
                                <td>
                                    <a class="button button-small" href="<?php echo esc_url(admin_url('admin.php?page=vaysf-results&action=edit&id=' . $result['result_id'])); ?>">Correct</a>
                                    <a class="button button-small" href="<?php echo esc_url(admin_url('admin.php?page=vaysf-results&action=revisions&id=' . $result['result_id'])); ?>">Revisions</a>
                                    <form method="post" style="display:inline;">
                                        <?php wp_nonce_field('certify_result_' . $result['result_id']); ?>
                                        <input type="hidden" name="vaysf_action" value="certify_result">
                                        <input type="hidden" name="id" value="<?php echo esc_attr($result['result_id']); ?>">
                                        <button class="button button-small" type="submit">Certify</button>
                                    </form>
                                    <form method="post" style="display:inline;">
                                        <?php wp_nonce_field('verify_result_' . $result['result_id']); ?>
                                        <input type="hidden" name="vaysf_action" value="verify_result">
                                        <input type="hidden" name="id" value="<?php echo esc_attr($result['result_id']); ?>">
                                        <button class="button button-small" type="submit">Verify</button>
                                    </form>
                                </td>
                            </tr>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </tbody>
            </table>
        </div>
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

        return $counts;
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
        <p>This clears the current score-entry database rows before coordinators begin Saturday data entry.</p>
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
                    Type <code>CLEAR RESULTS</code> to delete rows from <code>sf_results</code>, <code>sf_result_revisions</code>, and <code>sf_result_files</code>.
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

// Initialize admin
new VAYSF_Admin();

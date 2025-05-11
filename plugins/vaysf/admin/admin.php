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
            'Competitions',
            'Competitions',
            'sf2025_read',
            'vaysf-competitions',
            array($this, 'display_competitions_page')
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
                            <td colspan="7">No churches found.</td>
                        </tr>
                    <?php else : ?>
                        <?php foreach ($churches as $church) : ?>
                            <tr>
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
                                <td><?php echo esc_html(ucfirst($church['insurance_status'])); ?></td>
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
    $where_clause = $church_filter ? "WHERE p.church_id = $church_filter" : '';
    
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
     * Display settings page
     */
    public function display_settings_page() {
        ?>
        <div class="wrap">
            <h1>Sports Fest Settings</h1>
            
            <form method="post" action="options.php">
                <?php settings_fields('vaysf_settings'); ?>
                <?php do_settings_sections('vaysf_settings'); ?>
                <?php submit_button(); ?>
            </form>
        </div>
        <?php
    }
}

// Initialize admin
new VAYSF_Admin();
<?php
/**
 * Plugin Name: VAYSF Integration
 * Description: Vietnamese Alliance Youth Sports Fest integration with ChMeetings via REST API (works with external Windows middleware)
 *              - The middleware will run on a scheduled basis (once a day during slow period, but higher frequency during rush period before deadlines)
 * Version: 1.0.10
 * Author: Bumble Ho
 * Text Domain: vaysf
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_Integration {
    
    /**
     * Plugin version
     */
    const VERSION = '1.0.10';
    
    /**
     * Database version
     */
    const DB_VERSION = '1.0.2';  // Incremented due to schema change
    
    /**
     * Database version option name
     */
    const DB_VERSION_OPTION = 'vaysf_db_version';
    
    /**
     * Table prefix
     */
    const TABLE_PREFIX = 'sf_';
    
    /**
     * Plugin instance
     */
    private static $instance = null;
    
    /**
     * Get plugin instance
     */
    public static function get_instance() {
        if (null === self::$instance) {
            self::$instance = new self();
        }
        return self::$instance;
    }
    
    /**
     * Constructor
     */
    private function __construct() {
        register_activation_hook(__FILE__, array($this, 'activate'));
        register_deactivation_hook(__FILE__, array($this, 'deactivate'));
        
        add_action('plugins_loaded', array($this, 'init'));
        
		add_filter('plugin_action_links_' . plugin_basename(__FILE__), array($this, 'add_plugin_action_links'));
		
        // Include files
        $this->include_files();
    }
    
	/**
	 * Include required files
	 */
        private function include_files() {
                // Helper functions
                require_once(plugin_dir_path(__FILE__) . 'includes/functions.php');

                // Include REST API
                require_once(plugin_dir_path(__FILE__) . 'includes/rest-api.php');
		
		// Include admin interface files
		require_once(plugin_dir_path(__FILE__) . 'admin/admin.php');
		
		// Include short codes: 
		//	- Overall Statistics [vaysf_stats]
		//	- Customized Statistics [vaysf_stats display="participants" layout="list"]; display=all/churches/participants/approvals/issues; layout=grid/list 
		//	- Churches List [vaysf_churches limit="5" orderby="church_name" order="ASC"]
		//	- Participants List [vaysf_participants limit="10" church="RPC" status="approved" sport="Basketball"]
		require_once(plugin_dir_path(__FILE__) . 'includes/shortcodes.php');
		// This is not counting the [pastor_approval] short code in the pastor-approval page for processing the approve/deny token triggered from the approval email.
	}
    
	/**
	 * Add action links to plugin page
	 */
	public function add_plugin_action_links($links) {
		$admin_link = array(
			'admin' => sprintf(
				'<a href="%s">%s</a>', 
				admin_url('admin.php?page=vaysf'), 
				__('Admin', 'vaysf')
			)
		);
		return array_merge($admin_link, $links);
	}
    
    /**
     * Initialize plugin
     */
    public function init() {
        $installed_version = get_option(self::DB_VERSION_OPTION);
        
        if ($installed_version !== self::DB_VERSION) {
            $this->create_tables();
        }
        
        // Register custom roles and capabilities
        $this->register_roles();
        
        // Register plugin settings
        $this->register_settings();
		
	   // Add hook for rewrite rules (moved this to WordPress 'init' hook)
		add_action('init', array($this, 'register_rewrite_rules'));
		
		// Register query vars
		add_filter('query_vars', array($this, 'register_query_vars'));
		
		// Add template redirect hook
		add_action('template_redirect', array($this, 'handle_approval_page'));
		
		// Flush rewrite rules on activation (only once)
		if (get_option('vaysf_rewrite_rules_flushed') !== self::VERSION) {
			flush_rewrite_rules();
			update_option('vaysf_rewrite_rules_flushed', self::VERSION);
		}
	}

	/**
	 * Register rewrite rules
	 */
	public function register_rewrite_rules() {
		// Add rewrite rule for pastor approval
		add_rewrite_rule(
			'pastor-approval/?$',
			'index.php?vaysf_pastor_approval=1',
			'top'
		);
	}

	public function register_query_vars($vars) {
		$vars[] = 'vaysf_pastor_approval';
		return $vars;
	}

	public function handle_approval_page() {
		if (get_query_var('vaysf_pastor_approval')) {
			// Check if the template file exists
			$template_path = plugin_dir_path(__FILE__) . 'templates/pastor-approval.php';
			if (file_exists($template_path)) {
				include_once($template_path);
				exit;
			} else {
				// Fallback if template doesn't exist
				wp_die('Pastor approval template not found. Please contact the site administrator.');
			}
		}
	}
	     
    /**
     * Plugin activation
     */
    public function activate() {
        // Create database tables
        $this->create_tables();
        
        // Initialize settings
        $this->initialize_settings();
        
        // Create default roles
        $this->register_roles();
        
        // Create necessary directories
        $this->create_directories();
        
        // Flush rewrite rules
        flush_rewrite_rules();
    }
    
    /**
     * Plugin deactivation
     */
    public function deactivate() {
        // Flush rewrite rules
        flush_rewrite_rules();
    }
    
    /**
     * Register custom roles and capabilities
     */
    private function register_roles() {
        // Add sf2025_admin role
        add_role('sf2025_admin', 'Sports Fest Admin', array(
            'read' => true,
            'sf2025_admin' => true,
            'sf2025_read' => true,
            'sf2025_write' => true
        ));
        
        // Add sf2025_manager role
        add_role('sf2025_manager', 'Sports Fest Manager', array(
            'read' => true,
            'sf2025_read' => true,
            'sf2025_write' => true
        ));
        
        // Add sf2025_viewer role
        add_role('sf2025_viewer', 'Sports Fest Viewer', array(
            'read' => true,
            'sf2025_read' => true
        ));
        
        // Add capabilities to administrator role
        $admin_role = get_role('administrator');
        if ($admin_role) {
            $admin_role->add_cap('sf2025_admin');
            $admin_role->add_cap('sf2025_read');
            $admin_role->add_cap('sf2025_write');
        }
    }
    
    /**
     * Register plugin settings
     */
    private function register_settings() {
        register_setting('vaysf_settings', 'vaysf_token_expiry_days', array(
            'type' => 'integer',
            'default' => 7,
            'sanitize_callback' => 'absint'
        ));
        
        register_setting('vaysf_settings', 'vaysf_email_from', array(
            'type' => 'string',
            'default' => get_option('admin_email'),
            'sanitize_callback' => 'sanitize_email'
        ));
        
        register_setting('vaysf_settings', 'vaysf_approval_email_subject', array(
            'type' => 'string',
            'default' => 'Sports Fest 2025: Approval Request',
            'sanitize_callback' => 'sanitize_text_field'
        ));
    }
    
    /**
     * Initialize default settings
     */
    private function initialize_settings() {
        add_option('vaysf_token_expiry_days', 7);
        add_option('vaysf_email_from', get_option('admin_email'));
        add_option('vaysf_approval_email_subject', 'Sports Fest 2025: Approval Request');
		add_option('vaysf_api_key', '');
    }
    
    /**
     * Create necessary directories
     */
    private function create_directories() {
        // Create upload directory for VAYSF
        $upload_dir = wp_upload_dir();
        $vaysf_dir = $upload_dir['basedir'] . '/vaysf';
        
        if (!file_exists($vaysf_dir)) {
            wp_mkdir_p($vaysf_dir);
        }
        
        // Create an index.php file in the directory
        $index_file = $vaysf_dir . '/index.php';
        if (!file_exists($index_file)) {
            file_put_contents($index_file, '<?php // Silence is golden');
        }
    }
    
    /**
     * Create database tables
     */
    private function create_tables() {
        global $wpdb;
        
        require_once(ABSPATH . 'wp-admin/includes/upgrade.php');
        
        $charset_collate = $wpdb->get_charset_collate();
        
		// Churches table
		$table_churches = $wpdb->prefix . self::TABLE_PREFIX . 'churches';
		$sql_churches = "CREATE TABLE $table_churches (
			church_id BIGINT(20) UNSIGNED NOT NULL AUTO_INCREMENT,
			church_code VARCHAR(3) NOT NULL,
			church_name VARCHAR(255) NOT NULL,
			pastor_name VARCHAR(255) NOT NULL,
			pastor_email VARCHAR(255) NOT NULL,
			pastor_phone VARCHAR(50) DEFAULT NULL,
			church_rep_name VARCHAR(255) DEFAULT NULL,
			church_rep_email VARCHAR(255) DEFAULT NULL,
			church_rep_phone VARCHAR(50) DEFAULT NULL,
			sports_ministry_level TINYINT UNSIGNED DEFAULT 1,
			registration_status VARCHAR(50) DEFAULT 'pending',
			insurance_status VARCHAR(50) DEFAULT 'pending',
			payment_status VARCHAR(50) DEFAULT 'pending',
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			PRIMARY KEY  (church_id),
			UNIQUE KEY church_code (church_code)
		) $charset_collate;";
		dbDelta($sql_churches);
        
		// Participants table - UPDATED with photo_url column
		$table_participants = $wpdb->prefix . self::TABLE_PREFIX . 'participants';
		$sql_participants = "CREATE TABLE $table_participants (
			participant_id BIGINT(20) UNSIGNED NOT NULL AUTO_INCREMENT,
			chmeetings_id VARCHAR(50) DEFAULT NULL,
			church_code VARCHAR(3) NOT NULL,
			first_name VARCHAR(255) NOT NULL,
			last_name VARCHAR(255) NOT NULL,
			email VARCHAR(255) DEFAULT NULL,
			phone VARCHAR(50) DEFAULT NULL,
			gender VARCHAR(10) DEFAULT NULL,
			birthdate DATE DEFAULT NULL,
			is_church_member TINYINT(1) DEFAULT 0,
			primary_sport VARCHAR(50) DEFAULT NULL,
			primary_format VARCHAR(50) DEFAULT NULL,
			primary_partner VARCHAR(255) DEFAULT NULL,
			secondary_sport VARCHAR(50) DEFAULT NULL,
			secondary_format VARCHAR(50) DEFAULT NULL,
			secondary_partner VARCHAR(255) DEFAULT NULL,
			other_events TEXT DEFAULT NULL,
			photo_url TEXT DEFAULT NULL,
			approval_status VARCHAR(50) DEFAULT 'pending',
			parent_info TEXT DEFAULT NULL,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			PRIMARY KEY  (participant_id),
			UNIQUE KEY chmeetings_id (chmeetings_id),
			KEY church_code (church_code)
		) $charset_collate;";
		dbDelta($sql_participants);

		// Rosters table
		$table_rosters = $wpdb->prefix . self::TABLE_PREFIX . 'rosters';
		$sql_rosters = "CREATE TABLE $table_rosters (
			roster_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
			church_code VARCHAR(3) NOT NULL,
			participant_id BIGINT UNSIGNED NOT NULL,
			sport_type VARCHAR(50) NOT NULL,
			sport_gender VARCHAR(20) NOT NULL,
			sport_format VARCHAR(20) NOT NULL,
			team_order VARCHAR(5),
			partner_name VARCHAR(50),
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			PRIMARY KEY (roster_id),
			FOREIGN KEY (church_code) REFERENCES {$wpdb->prefix}sf_churches(church_code) ON DELETE CASCADE,
			FOREIGN KEY (participant_id) REFERENCES {$wpdb->prefix}sf_participants(participant_id) ON DELETE CASCADE,
			KEY church_sport (church_code, sport_type, sport_gender, sport_format)
		) $charset_collate;";
		dbDelta($sql_rosters);
        
        // Approvals table
        $table_approvals = $wpdb->prefix . self::TABLE_PREFIX . 'approvals';
        $sql_approvals = "CREATE TABLE $table_approvals (
            approval_id BIGINT(20) UNSIGNED NOT NULL AUTO_INCREMENT,
            participant_id BIGINT(20) UNSIGNED NOT NULL,
            church_id BIGINT(20) UNSIGNED NOT NULL,
            approval_token VARCHAR(255) NOT NULL,
            token_expiry DATETIME NOT NULL,
            pastor_email VARCHAR(255) NOT NULL,
            approval_status VARCHAR(50) DEFAULT 'pending',
            approval_date DATETIME DEFAULT NULL,
            approval_notes TEXT DEFAULT NULL,
            synced_to_chmeetings TINYINT(1) DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY  (approval_id),
            UNIQUE KEY participant_church (participant_id, church_id),
            KEY approval_token (approval_token),
            KEY approval_status (approval_status)
        ) $charset_collate;";
        dbDelta($sql_approvals);

		// Validation Issues table
		$table_validation_issues = $wpdb->prefix . self::TABLE_PREFIX . 'validation_issues';
		$sql_validation_issues = "CREATE TABLE $table_validation_issues (
			issue_id BIGINT(20) UNSIGNED NOT NULL AUTO_INCREMENT,
			church_id BIGINT(20) UNSIGNED NOT NULL,
			participant_id BIGINT(20) UNSIGNED DEFAULT NULL,
			issue_type VARCHAR(50) NOT NULL,
			issue_description TEXT NOT NULL,
			rule_code VARCHAR(50) DEFAULT NULL,
			rule_level VARCHAR(20) DEFAULT NULL,
			severity VARCHAR(10) DEFAULT 'ERROR',
			sport_type VARCHAR(50) DEFAULT NULL,
			sport_format VARCHAR(20) DEFAULT NULL,
			status VARCHAR(50) DEFAULT 'open',
			reported_at DATETIME DEFAULT NULL,
			resolved_at DATETIME DEFAULT NULL,
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			PRIMARY KEY  (issue_id),
			KEY church_id (church_id),
			KEY participant_id (participant_id),
			KEY rule_code (rule_code),
			KEY rule_level (rule_level),
			KEY severity (severity),
			KEY sport_type (sport_type),
			KEY status (status)
		) $charset_collate;";
		dbDelta($sql_validation_issues);
                
        // Competitions table
        $table_competitions = $wpdb->prefix . self::TABLE_PREFIX . 'competitions';
        $sql_competitions = "CREATE TABLE $table_competitions (
            competition_id BIGINT(20) UNSIGNED NOT NULL AUTO_INCREMENT,
            sport_type VARCHAR(50) NOT NULL,
            category VARCHAR(50) NOT NULL,
            format VARCHAR(50) NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY  (competition_id),
            UNIQUE KEY sport_category_format (sport_type, category, format)
        ) $charset_collate;";
        dbDelta($sql_competitions);
        
        // Schedules table
        $table_schedules = $wpdb->prefix . self::TABLE_PREFIX . 'schedules';
        $sql_schedules = "CREATE TABLE $table_schedules (
            schedule_id BIGINT(20) UNSIGNED NOT NULL AUTO_INCREMENT,
            competition_id BIGINT(20) UNSIGNED NOT NULL,
            round_name VARCHAR(50) NOT NULL,
            match_number INT UNSIGNED NOT NULL,
            team_a_id BIGINT(20) UNSIGNED DEFAULT NULL,
            team_b_id BIGINT(20) UNSIGNED DEFAULT NULL,
            scheduled_time DATETIME DEFAULT NULL,
            scheduled_location VARCHAR(255) DEFAULT NULL,
            synced_to_chmeetings TINYINT(1) DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY  (schedule_id),
            KEY competition_id (competition_id),
            KEY scheduled_time (scheduled_time)
        ) $charset_collate;";
        dbDelta($sql_schedules);
        
        // Results table
        $table_results = $wpdb->prefix . self::TABLE_PREFIX . 'results';
        $sql_results = "CREATE TABLE $table_results (
            result_id BIGINT(20) UNSIGNED NOT NULL AUTO_INCREMENT,
            schedule_id BIGINT(20) UNSIGNED NOT NULL,
            score_team_a VARCHAR(50) DEFAULT NULL,
            score_team_b VARCHAR(50) DEFAULT NULL,
            winner_id BIGINT(20) UNSIGNED DEFAULT NULL,
            result_status VARCHAR(50) DEFAULT 'pending',
            notes TEXT DEFAULT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY  (result_id),
            UNIQUE KEY schedule_id (schedule_id),
            KEY result_status (result_status)
        ) $charset_collate;";
        dbDelta($sql_results);
        
        // Sync Log table
        $table_sync_log = $wpdb->prefix . self::TABLE_PREFIX . 'sync_log';
        $sql_sync_log = "CREATE TABLE $table_sync_log (
            log_id BIGINT(20) UNSIGNED NOT NULL AUTO_INCREMENT,
            sync_type VARCHAR(50) NOT NULL,
            direction VARCHAR(20) NOT NULL,
            status VARCHAR(50) DEFAULT 'pending',
            records_processed INT UNSIGNED DEFAULT 0,
            success_count INT UNSIGNED DEFAULT 0,
            error_count INT UNSIGNED DEFAULT 0,
            error_details TEXT DEFAULT NULL,
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME DEFAULT NULL,
            PRIMARY KEY  (log_id),
            KEY sync_type (sync_type),
            KEY direction (direction),
            KEY completed_at (completed_at)
        ) $charset_collate;";
        dbDelta($sql_sync_log);

		// Email log table
		$table_email_log = $wpdb->prefix . self::TABLE_PREFIX . 'email_log';
		$sql_email_log = "CREATE TABLE $table_email_log (
			log_id BIGINT(20) UNSIGNED NOT NULL AUTO_INCREMENT,
			to_email VARCHAR(255) NOT NULL,
			subject VARCHAR(255) NOT NULL,
			message TEXT NOT NULL,
			sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			status VARCHAR(50) DEFAULT 'sent',
			PRIMARY KEY  (log_id),
			KEY sent_at (sent_at)
		) $charset_collate;";
		dbDelta($sql_email_log);
        
        // Update version
        update_option(self::DB_VERSION_OPTION, self::DB_VERSION);
        
        // Check if photo_url column needs to be added to existing table
        $check_column = $wpdb->get_results("SHOW COLUMNS FROM {$table_participants} LIKE 'photo_url'");
        if (empty($check_column)) {
            $wpdb->query("ALTER TABLE {$table_participants} ADD COLUMN photo_url TEXT DEFAULT NULL AFTER other_events");
            // Log this change
            error_log('Added photo_url column to sf_participants table');
        }
    }
}

// Initialize plugin
function VAYSF_Integration_init() {
    return VAYSF_Integration::get_instance();
}

/**
 * It seems like rewrite rule doesn't work.
 */
 // Add this to vaysf.php
function pastor_approval_shortcode($atts) {
	ob_start();
	include plugin_dir_path(__FILE__) . 'templates/pastor-approval.php';
	return ob_get_clean();
}
add_shortcode('pastor_approval', 'pastor_approval_shortcode');

function vaysf_test_shortcode() {
    return '<p style="color:red;">Shortcode test successful!</p>';
}
add_shortcode('vaysf_test', 'vaysf_test_shortcode');

// Start the plugin
VAYSF_Integration_init();
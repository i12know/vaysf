<?php
/**
 * Plugin Name: VAYSF Integration
 * Description: Vietnamese Alliance Youth Sports Fest integration with ChMeetings via REST API (works with external Windows middleware)
 *              - The middleware will run on a scheduled basis (once a day during slow period, but higher frequency during rush period before deadlines)
 * Version: 1.0.16
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
    const VERSION = '1.0.16';

    /**
     * Database version
     */
    const DB_VERSION = '1.0.6';  // Issue #203 — event-day results schema (sf_schedules/sf_results
                                  // redesign + new sf_result_revisions/sf_result_files tables)
                                  // Issue #230 — removed the superseded sf_competitions table and
                                  // sf_schedules.competition_id (never populated, never referenced
                                  // outside schema definitions; replaced by event/sub_event columns)
    
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

		// Add rewrite rule for the public insurance upload page (Issue #154)
		add_rewrite_rule(
			'insurance-upload/?$',
			'index.php?vaysf_insurance_upload=1',
			'top'
		);
	}

	public function register_query_vars($vars) {
		$vars[] = 'vaysf_pastor_approval';
		$vars[] = 'vaysf_insurance_upload';
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

		if (get_query_var('vaysf_insurance_upload')) {
			$template_path = plugin_dir_path(__FILE__) . 'templates/insurance-upload.php';
			if (file_exists($template_path)) {
				include_once($template_path);
				exit;
			} else {
				wp_die('Insurance upload template not found. Please contact the site administrator.');
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

        register_setting('vaysf_settings', 'vaysf_sports_fest_date', array(
            'type' => 'string',
            'default' => '2026-07-18',
            'sanitize_callback' => 'sanitize_text_field'
        ));

        // Insurance upload settings (Issue #154)
        register_setting('vaysf_settings', 'vaysf_insurance_token_expiry_hours', array(
            'type' => 'integer',
            'default' => 48,
            'sanitize_callback' => 'absint'
        ));

        register_setting('vaysf_settings', 'vaysf_insurance_admin_notify', array(
            'type' => 'boolean',
            'default' => false,
            'sanitize_callback' => 'rest_sanitize_boolean'
        ));
    }
    
    /**
     * Initialize default settings
     */
    private function initialize_settings() {
        add_option('vaysf_token_expiry_days', 7);
        add_option('vaysf_email_from', get_option('admin_email'));
        add_option('vaysf_approval_email_subject', 'Sports Fest 2025: Approval Request');
        add_option('vaysf_sports_fest_date', '2026-07-18');
		add_option('vaysf_api_key', '');
        add_option('vaysf_insurance_token_expiry_hours', 48);
        add_option('vaysf_insurance_admin_notify', false);
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

        // Create the insurance upload directory (Issue #154)
        $insurance_dir = $vaysf_dir . '/insurance';
        if (!file_exists($insurance_dir)) {
            wp_mkdir_p($insurance_dir);
        }

        $insurance_index = $insurance_dir . '/index.php';
        if (!file_exists($insurance_index)) {
            file_put_contents($insurance_index, '<?php // Silence is golden');
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
			insurance_file_url VARCHAR(500) DEFAULT NULL,
			insurance_uploaded_at DATETIME DEFAULT NULL,
			insurance_token VARCHAR(64) DEFAULT NULL,
			insurance_token_expiry DATETIME DEFAULT NULL,
			payment_status VARCHAR(50) DEFAULT 'pending',
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			PRIMARY KEY  (church_id),
			UNIQUE KEY church_code (church_code),
			KEY insurance_token (insurance_token)
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
			membership_claim_at_approval TINYINT(1) NULL DEFAULT NULL,
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
                
        // Schedules table (redesigned for Issue #203 — string game_key scheduling model,
        // replaces the numeric team_a_id/team_b_id FK shape; table was confirmed unused
        // in production so no data-preserving migration is needed).
        // The pre-#203 sf_competitions taxonomy table and its competition_id FK on this
        // table were removed in Issue #230 — the new schema carries event/stage/sub_event
        // directly on each row instead, and sf_competitions was never populated.
        $table_schedules = $wpdb->prefix . self::TABLE_PREFIX . 'schedules';
        $sql_schedules = "CREATE TABLE $table_schedules (
            schedule_id BIGINT(20) UNSIGNED NOT NULL AUTO_INCREMENT,
            game_key VARCHAR(64) NOT NULL,
            schedule_version INT UNSIGNED NOT NULL DEFAULT 0,
            event VARCHAR(100) DEFAULT NULL,
            stage VARCHAR(50) DEFAULT NULL,
            pool_id VARCHAR(20) DEFAULT NULL,
            round_number INT UNSIGNED DEFAULT NULL,
            sub_event VARCHAR(50) DEFAULT NULL,
            team_a_key VARCHAR(64) DEFAULT NULL,
            team_a_label VARCHAR(255) DEFAULT NULL,
            team_b_key VARCHAR(64) DEFAULT NULL,
            team_b_label VARCHAR(255) DEFAULT NULL,
            team_c_key VARCHAR(64) DEFAULT NULL,
            team_c_label VARCHAR(255) DEFAULT NULL,
            team_ids_json TEXT DEFAULT NULL,
            resource_id VARCHAR(64) DEFAULT NULL,
            scheduled_slot VARCHAR(32) DEFAULT NULL,
            scheduled_time DATETIME DEFAULT NULL,
            scheduled_location VARCHAR(255) DEFAULT NULL,
            game_status VARCHAR(20) NOT NULL DEFAULT 'scheduled',
            source_hash CHAR(64) DEFAULT NULL,
            published_at DATETIME DEFAULT NULL,
            synced_to_chmeetings TINYINT(1) DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY  (schedule_id),
            UNIQUE KEY game_key (game_key),
            KEY schedule_version (schedule_version),
            KEY game_status (game_status),
            KEY event (event),
            KEY scheduled_time (scheduled_time)
        ) $charset_collate;";
        dbDelta($sql_schedules);

        // Results table (redesigned for Issue #203 — one current result per schedule row;
        // revision history moves to sf_result_revisions below)
        $table_results = $wpdb->prefix . self::TABLE_PREFIX . 'results';
        $sql_results = "CREATE TABLE $table_results (
            result_id BIGINT(20) UNSIGNED NOT NULL AUTO_INCREMENT,
            schedule_id BIGINT(20) UNSIGNED NOT NULL,
            score_json TEXT DEFAULT NULL,
            winner_keys_json TEXT DEFAULT NULL,
            submitted_by_user_id BIGINT(20) UNSIGNED DEFAULT NULL,
            certified_at DATETIME DEFAULT NULL,
            verified_by_user_id BIGINT(20) UNSIGNED DEFAULT NULL,
            verified_at DATETIME DEFAULT NULL,
            current_revision INT UNSIGNED NOT NULL DEFAULT 0,
            correction_reason TEXT DEFAULT NULL,
            public_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            scan_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            notes TEXT DEFAULT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY  (result_id),
            UNIQUE KEY schedule_id (schedule_id),
            KEY public_status (public_status),
            KEY scan_status (scan_status)
        ) $charset_collate;";
        dbDelta($sql_results);

        // Result revisions table — append-only submission/correction history (Issue #203)
        $table_result_revisions = $wpdb->prefix . self::TABLE_PREFIX . 'result_revisions';
        $sql_result_revisions = "CREATE TABLE $table_result_revisions (
            revision_id BIGINT(20) UNSIGNED NOT NULL AUTO_INCREMENT,
            result_id BIGINT(20) UNSIGNED NOT NULL,
            revision_number INT UNSIGNED NOT NULL,
            score_json TEXT DEFAULT NULL,
            winner_keys_json TEXT DEFAULT NULL,
            notes TEXT DEFAULT NULL,
            correction_reason TEXT DEFAULT NULL,
            submitted_by_user_id BIGINT(20) UNSIGNED NOT NULL,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            verification_state VARCHAR(20) NOT NULL DEFAULT 'unverified',
            source_ip VARCHAR(45) DEFAULT NULL,
            request_metadata TEXT DEFAULT NULL,
            PRIMARY KEY  (revision_id),
            UNIQUE KEY result_revision (result_id, revision_number),
            KEY submitted_by_user_id (submitted_by_user_id),
            KEY verification_state (verification_state)
        ) $charset_collate;";
        dbDelta($sql_result_revisions);

        // Result files table — protected scoresheet attachments, one row per file (Issue #203)
        $table_result_files = $wpdb->prefix . self::TABLE_PREFIX . 'result_files';
        $sql_result_files = "CREATE TABLE $table_result_files (
            file_id BIGINT(20) UNSIGNED NOT NULL AUTO_INCREMENT,
            result_revision_id BIGINT(20) UNSIGNED NOT NULL,
            file_path VARCHAR(500) NOT NULL,
            original_filename VARCHAR(255) NOT NULL,
            mime_type VARCHAR(100) NOT NULL,
            byte_size BIGINT(20) UNSIGNED NOT NULL,
            sha256_hash CHAR(64) NOT NULL,
            uploaded_by_user_id BIGINT(20) UNSIGNED NOT NULL,
            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY  (file_id),
            KEY result_revision_id (result_revision_id),
            KEY sha256_hash (sha256_hash)
        ) $charset_collate;";
        dbDelta($sql_result_files);

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
        
        // Check if photo_url column needs to be added to existing table
        $check_column = $wpdb->get_results("SHOW COLUMNS FROM {$table_participants} LIKE 'photo_url'");
        if (empty($check_column)) {
            $wpdb->query("ALTER TABLE {$table_participants} ADD COLUMN photo_url TEXT DEFAULT NULL AFTER other_events");
            // Log this change
            error_log('Added photo_url column to sf_participants table');
        }

        // Check if membership_claim_at_approval column needs to be added to existing table
        $check_column = $wpdb->get_results("SHOW COLUMNS FROM {$table_participants} LIKE 'membership_claim_at_approval'");
        if (empty($check_column)) {
            $wpdb->query(
                "ALTER TABLE {$table_participants} " .
                "ADD COLUMN membership_claim_at_approval TINYINT(1) NULL DEFAULT NULL AFTER is_church_member"
            );
            error_log('Added membership_claim_at_approval column to sf_participants table');
        }

        // Insurance upload columns on sf_churches (Issue #154).
        // dbDelta above adds these for fresh installs; ALTER covers upgrades from
        // an older schema where the columns did not yet exist.
        $insurance_columns = array(
            'insurance_file_url'     => "ADD COLUMN insurance_file_url VARCHAR(500) DEFAULT NULL AFTER insurance_status",
            'insurance_uploaded_at'  => "ADD COLUMN insurance_uploaded_at DATETIME DEFAULT NULL AFTER insurance_file_url",
            'insurance_token'        => "ADD COLUMN insurance_token VARCHAR(64) DEFAULT NULL AFTER insurance_uploaded_at",
            'insurance_token_expiry' => "ADD COLUMN insurance_token_expiry DATETIME DEFAULT NULL AFTER insurance_token",
        );
        foreach ($insurance_columns as $column => $alter) {
            $check_column = $wpdb->get_results("SHOW COLUMNS FROM {$table_churches} LIKE '{$column}'");
            if (empty($check_column)) {
                $wpdb->query("ALTER TABLE {$table_churches} {$alter}");
                error_log("Added {$column} column to sf_churches table");
            }
        }

        // Event-day results schema columns on sf_schedules (Issue #203).
        // dbDelta above adds these for fresh installs; ALTER covers upgrades from
        // the pre-#203 numeric team_a_id/team_b_id schema where they did not exist.
        $schedules_columns = array(
            'game_key'         => "ADD COLUMN game_key VARCHAR(64) NOT NULL DEFAULT '' AFTER schedule_id",
            'schedule_version' => "ADD COLUMN schedule_version INT UNSIGNED NOT NULL DEFAULT 0 AFTER game_key",
            'event'            => "ADD COLUMN event VARCHAR(100) DEFAULT NULL AFTER schedule_version",
            'stage'            => "ADD COLUMN stage VARCHAR(50) DEFAULT NULL AFTER event",
            'pool_id'          => "ADD COLUMN pool_id VARCHAR(20) DEFAULT NULL AFTER stage",
            'round_number'     => "ADD COLUMN round_number INT UNSIGNED DEFAULT NULL AFTER pool_id",
            'sub_event'        => "ADD COLUMN sub_event VARCHAR(50) DEFAULT NULL AFTER round_number",
            'team_a_key'       => "ADD COLUMN team_a_key VARCHAR(64) DEFAULT NULL AFTER sub_event",
            'team_a_label'     => "ADD COLUMN team_a_label VARCHAR(255) DEFAULT NULL AFTER team_a_key",
            'team_b_key'       => "ADD COLUMN team_b_key VARCHAR(64) DEFAULT NULL AFTER team_a_label",
            'team_b_label'     => "ADD COLUMN team_b_label VARCHAR(255) DEFAULT NULL AFTER team_b_key",
            'team_c_key'       => "ADD COLUMN team_c_key VARCHAR(64) DEFAULT NULL AFTER team_b_label",
            'team_c_label'     => "ADD COLUMN team_c_label VARCHAR(255) DEFAULT NULL AFTER team_c_key",
            'team_ids_json'    => "ADD COLUMN team_ids_json TEXT DEFAULT NULL AFTER team_c_label",
            'resource_id'      => "ADD COLUMN resource_id VARCHAR(64) DEFAULT NULL AFTER team_ids_json",
            'scheduled_slot'   => "ADD COLUMN scheduled_slot VARCHAR(32) DEFAULT NULL AFTER resource_id",
            'game_status'      => "ADD COLUMN game_status VARCHAR(20) NOT NULL DEFAULT 'scheduled' AFTER scheduled_location",
            'source_hash'      => "ADD COLUMN source_hash CHAR(64) DEFAULT NULL AFTER game_status",
            'published_at'     => "ADD COLUMN published_at DATETIME DEFAULT NULL AFTER source_hash",
        );
        foreach ($schedules_columns as $column => $alter) {
            $check_column = $wpdb->get_results("SHOW COLUMNS FROM {$table_schedules} LIKE '{$column}'");
            if (empty($check_column)) {
                $wpdb->query("ALTER TABLE {$table_schedules} {$alter}");
                error_log("Added {$column} column to sf_schedules table");
            }
        }

        // Existing pre-#203 schedule rows, if any, were created before game_key
        // existed. Give blank or duplicate legacy rows stable placeholder keys
        // before adding the unique index so migration cannot fail on repeated ''.
        $schedule_key_rows = $wpdb->get_results(
            "SELECT schedule_id, game_key FROM {$table_schedules} ORDER BY schedule_id",
            ARRAY_A
        );
        $seen_game_keys = array();
        foreach ($schedule_key_rows as $row) {
            $schedule_id = absint($row['schedule_id']);
            $game_key = isset($row['game_key']) ? trim((string) $row['game_key']) : '';
            if ($game_key === '' || isset($seen_game_keys[$game_key])) {
                $game_key = 'legacy-' . $schedule_id;
                $wpdb->update(
                    $table_schedules,
                    array('game_key' => $game_key),
                    array('schedule_id' => $schedule_id),
                    array('%s'),
                    array('%d')
                );
                error_log("Assigned legacy game_key {$game_key} to sf_schedules row {$schedule_id}");
            }
            $seen_game_keys[$game_key] = true;
        }

        // game_key must be unique once populated; add the index separately since dbDelta
        // cannot reliably add a UNIQUE KEY to an existing table via ALTER.
        $check_index = $wpdb->get_results("SHOW INDEX FROM {$table_schedules} WHERE Key_name = 'game_key'");
        if (empty($check_index)) {
            $wpdb->query("ALTER TABLE {$table_schedules} ADD UNIQUE KEY game_key (game_key)");
            error_log('Added game_key unique index to sf_schedules table');
        }

        // Event-day results schema columns on sf_results (Issue #203).
        $results_columns = array(
            'score_json'            => "ADD COLUMN score_json TEXT DEFAULT NULL AFTER schedule_id",
            'winner_keys_json'      => "ADD COLUMN winner_keys_json TEXT DEFAULT NULL AFTER score_json",
            'submitted_by_user_id'  => "ADD COLUMN submitted_by_user_id BIGINT(20) UNSIGNED DEFAULT NULL AFTER winner_keys_json",
            'certified_at'          => "ADD COLUMN certified_at DATETIME DEFAULT NULL AFTER submitted_by_user_id",
            'verified_by_user_id'   => "ADD COLUMN verified_by_user_id BIGINT(20) UNSIGNED DEFAULT NULL AFTER certified_at",
            'verified_at'           => "ADD COLUMN verified_at DATETIME DEFAULT NULL AFTER verified_by_user_id",
            'current_revision'      => "ADD COLUMN current_revision INT UNSIGNED NOT NULL DEFAULT 0 AFTER verified_at",
            'correction_reason'     => "ADD COLUMN correction_reason TEXT DEFAULT NULL AFTER current_revision",
            'public_status'         => "ADD COLUMN public_status VARCHAR(20) NOT NULL DEFAULT 'pending' AFTER correction_reason",
            'scan_status'           => "ADD COLUMN scan_status VARCHAR(20) NOT NULL DEFAULT 'pending' AFTER public_status",
        );
        foreach ($results_columns as $column => $alter) {
            $check_column = $wpdb->get_results("SHOW COLUMNS FROM {$table_results} LIKE '{$column}'");
            if (empty($check_column)) {
                $wpdb->query("ALTER TABLE {$table_results} {$alter}");
                error_log("Added {$column} column to sf_results table");
            }
        }

        // Update version after any fallback migrations run
        update_option(self::DB_VERSION_OPTION, self::DB_VERSION);
    }

    /**
     * Get formatted sports fest date
     * 
     * @param string $format PHP date format string
     * @return string Formatted date
     */
    public static function get_sports_fest_date_formatted($format = 'F j, Y') {
        $date = get_option('vaysf_sports_fest_date', '2026-07-18');
        return date($format, strtotime($date));
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

function insurance_upload_shortcode($atts) {
	ob_start();
	$GLOBALS['vaysf_rendering_insurance_shortcode'] = true;
	include plugin_dir_path(__FILE__) . 'templates/insurance-upload.php';
	unset($GLOBALS['vaysf_rendering_insurance_shortcode']);
	return ob_get_clean();
}
add_shortcode('insurance_upload', 'insurance_upload_shortcode');

// Start the plugin
VAYSF_Integration_init();

<?php
/**
 * File: admin/admin.php
 * Description: Admin bootstrap for VAYSF Integration - menu registration and
 *              delegation to the page modules under admin/ (Issue #284)
 * Version: 1.0.7: page modules
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

// Shared page base (status vocabularies, team formatting, admin notices)
require_once(plugin_dir_path(__FILE__) . 'class-vaysf-admin-page.php');

// Page modules, one file per admin screen
require_once(plugin_dir_path(__FILE__) . 'class-vaysf-admin-dashboard.php');
require_once(plugin_dir_path(__FILE__) . 'class-vaysf-admin-churches.php');
require_once(plugin_dir_path(__FILE__) . 'class-vaysf-admin-participants.php');
require_once(plugin_dir_path(__FILE__) . 'class-vaysf-admin-rosters.php');
require_once(plugin_dir_path(__FILE__) . 'class-vaysf-admin-approvals.php');
require_once(plugin_dir_path(__FILE__) . 'class-vaysf-admin-validation.php');
require_once(plugin_dir_path(__FILE__) . 'class-vaysf-admin-schedules.php');
require_once(plugin_dir_path(__FILE__) . 'class-vaysf-admin-results.php');
require_once(plugin_dir_path(__FILE__) . 'class-vaysf-admin-settings.php');

class VAYSF_Admin {

    /**
     * Page modules keyed by screen, each owning its renderer and form actions
     */
    private $pages = array();

    /**
     * Constructor
     */
    public function __construct() {
        $this->pages = array(
            'dashboard' => new VAYSF_Admin_Dashboard(),
            'churches' => new VAYSF_Admin_Churches(),
            'participants' => new VAYSF_Admin_Participants(),
            'rosters' => new VAYSF_Admin_Rosters(),
            'approvals' => new VAYSF_Admin_Approvals(),
            'validation' => new VAYSF_Admin_Validation(),
            'schedules' => new VAYSF_Admin_Schedules(),
            'results' => new VAYSF_Admin_Results(),
            'settings' => new VAYSF_Admin_Settings(),
        );

        // Add admin menu
        add_action('admin_menu', array($this, 'add_admin_menu'));

        // Register settings
        add_action('admin_init', array($this->pages['settings'], 'register_settings'));
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
            array($this->pages['dashboard'], 'display_dashboard_page'),
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
            array($this->pages['dashboard'], 'display_dashboard_page')
        );
        
        add_submenu_page(
            'vaysf',
            'Churches',
            'Churches',
            'sf2025_read',
            'vaysf-churches',
            array($this->pages['churches'], 'display_churches_page')
        );
        
        add_submenu_page(
            'vaysf',
            'Participants',
            'Participants',
            'sf2025_read',
            'vaysf-participants',
            array($this->pages['participants'], 'display_participants_page')
        );

		add_submenu_page(
			'vaysf',
			'Rosters',
			'Rosters',
			'sf2025_read',
			'vaysf-rosters',
			array($this->pages['rosters'], 'display_rosters_page')
		);
        
        add_submenu_page(
            'vaysf',
            'Approvals',
            'Approvals',
            'sf2025_read',
            'vaysf-approvals',
            array($this->pages['approvals'], 'display_approvals_page')
        );
        
        add_submenu_page(
            'vaysf',
            'Validation',
            'Validation',
            'sf2025_read',
            'vaysf-validation',
            array($this->pages['validation'], 'display_validation_page')
        );

        add_submenu_page(
            'vaysf',
            'Schedules',
            'Schedules',
            'sf2025_read',
            'vaysf-schedules',
            array($this->pages['schedules'], 'display_schedules_page')
        );

        add_submenu_page(
            'vaysf',
            'Results',
            'Results',
            'sf2025_read',
            'vaysf-results',
            array($this->pages['results'], 'display_results_page')
        );
        
        add_submenu_page(
            'vaysf',
            'Settings',
            'Settings',
            'sf2025_admin',
            'vaysf-settings',
            array($this->pages['settings'], 'display_settings_page')
        );
    }
}

// Initialize admin
new VAYSF_Admin();

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
require_once(plugin_dir_path(__FILE__) . 'class-vaysf-admin-bible-verses.php');
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
            'bible_verses' => new VAYSF_Admin_Bible_Verses(),
            'settings' => new VAYSF_Admin_Settings(),
        );

        // Add admin menu
        add_action('admin_menu', array($this, 'add_admin_menu'));

        // Register settings
        add_action('admin_init', array($this->pages['settings'], 'register_settings'));

        // Keep event-day admin screens fresh during plugin hotfix deploys.
        add_action('admin_init', array($this, 'send_vaysf_admin_no_cache_headers'));
        add_action('admin_enqueue_scripts', array($this, 'enqueue_admin_cache_guard'));
        add_action('wp_ajax_vaysf_plugin_version', array($this, 'ajax_plugin_version'));
    }

    /**
     * Whether the current wp-admin request is one of the Sports Fest screens.
     *
     * @return bool
     */
    private function is_vaysf_admin_request() {
        $page = isset($_GET['page']) ? sanitize_key(wp_unslash($_GET['page'])) : '';

        return $page === 'vaysf' || strpos($page, 'vaysf-') === 0;
    }

    /**
     * Send conservative no-cache headers for Sports Fest admin pages.
     *
     * @return void
     */
    public function send_vaysf_admin_no_cache_headers() {
        if (!$this->is_vaysf_admin_request() || headers_sent()) {
            return;
        }

        $this->send_no_cache_headers();
    }

    /**
     * Send conservative no-cache headers for a Sports Fest response.
     *
     * @return void
     */
    private function send_no_cache_headers() {
        if (headers_sent()) {
            return;
        }

        nocache_headers();
        header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
        header('Pragma: no-cache');
        header('X-VAYSF-Plugin-Version: ' . VAYSF_Integration::VERSION);
    }

    /**
     * Enqueue the admin version guard on Sports Fest admin pages.
     *
     * @return void
     */
    public function enqueue_admin_cache_guard() {
        if (!$this->is_vaysf_admin_request()) {
            return;
        }

        wp_enqueue_script(
            'vaysf-admin-cache-guard',
            plugins_url('assets/admin-cache-guard.js', dirname(__DIR__) . '/vaysf.php'),
            array(),
            VAYSF_Integration::VERSION,
            true
        );
        wp_localize_script(
            'vaysf-admin-cache-guard',
            'vaysfAdminCacheGuard',
            array(
                'ajaxUrl' => admin_url('admin-ajax.php'),
                'nonce' => wp_create_nonce('vaysf_plugin_version'),
                'renderedVersion' => VAYSF_Integration::VERSION,
                'reloadMessage' => __('Sports Fest was updated after this page loaded. Reload this page before saving so you do not submit an older screen.', 'vaysf'),
                'reloadLabel' => __('Reload now', 'vaysf'),
            )
        );
    }

    /**
     * Return the active plugin version for stale-page checks.
     *
     * @return void
     */
    public function ajax_plugin_version() {
        $this->send_no_cache_headers();

        if (!current_user_can('sf2025_read')) {
            wp_send_json_error(array('message' => __('You do not have permission to read Sports Fest status.', 'vaysf')), 403);
        }

        check_ajax_referer('vaysf_plugin_version', 'nonce');

        wp_send_json_success(array(
            'version' => VAYSF_Integration::VERSION,
        ));
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
            'Bible Verse Editor',
            'Bible Verses',
            VAYSF_BIBLE_VERSE_CAPABILITY,
            'vaysf-bible-verses',
            array($this->pages['bible_verses'], 'display_bible_verses_page')
        );

        if (current_user_can(VAYSF_BIBLE_VERSE_CAPABILITY) && !current_user_can('sf2025_read')) {
            add_menu_page(
                'Bible Verse Editor',
                'Bible Verses',
                VAYSF_BIBLE_VERSE_CAPABILITY,
                'vaysf-bible-verses',
                array($this->pages['bible_verses'], 'display_bible_verses_page'),
                'dashicons-book-alt',
                31
            );
        }
        
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

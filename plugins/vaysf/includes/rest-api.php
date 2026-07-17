<?php
/**
 * File: includes/rest-api.php
 * Description: REST API bootstrap for VAYSF Integration - route handlers
 *              live in the domain controllers under includes/rest-api/
 * Version: 1.0.9: domain controllers (Issue #265)
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

// Shared controller base (API namespace, API key + permission model)
require_once(plugin_dir_path(__FILE__) . 'rest-api/class-vaysf-rest-controller.php');

// Domain controllers, one file per route ownership boundary
require_once(plugin_dir_path(__FILE__) . 'rest-api/class-vaysf-rest-churches.php');
require_once(plugin_dir_path(__FILE__) . 'rest-api/class-vaysf-rest-participants.php');
require_once(plugin_dir_path(__FILE__) . 'rest-api/class-vaysf-rest-rosters.php');
require_once(plugin_dir_path(__FILE__) . 'rest-api/class-vaysf-rest-approvals.php');
require_once(plugin_dir_path(__FILE__) . 'rest-api/class-vaysf-rest-validation-issues.php');
require_once(plugin_dir_path(__FILE__) . 'rest-api/class-vaysf-rest-schedules.php');
require_once(plugin_dir_path(__FILE__) . 'rest-api/class-vaysf-rest-public-display.php');
require_once(plugin_dir_path(__FILE__) . 'rest-api/class-vaysf-rest-email.php');
require_once(plugin_dir_path(__FILE__) . 'rest-api/class-vaysf-rest-sync-logs.php');


class VAYSF_REST_API {

    /**
     * API namespace - kept on this class because external callers
     * (e.g. includes/shortcodes.php) reference VAYSF_REST_API::API_NAMESPACE.
     */
    const API_NAMESPACE = VAYSF_REST_Controller::API_NAMESPACE;

    /**
     * Domain controllers; each hooks rest_api_init and registers its own routes.
     */
    private $controllers = array();

    /**
     * Constructor
     */
    public function __construct() {
        $this->controllers = array(
            new VAYSF_REST_Churches(),
            new VAYSF_REST_Participants(),
            new VAYSF_REST_Rosters(),
            new VAYSF_REST_Approvals(),
            new VAYSF_REST_Validation_Issues(),
            new VAYSF_REST_Schedules(),
            new VAYSF_REST_Public_Display(),
            new VAYSF_REST_Email(),
            new VAYSF_REST_Sync_Logs(),
        );
    }
}

// Initialize REST API
new VAYSF_REST_API();

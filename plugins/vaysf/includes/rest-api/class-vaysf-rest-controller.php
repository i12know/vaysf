<?php
/**
 * File: includes/rest-api/class-vaysf-rest-controller.php
 * Description: Shared base for VAYSF REST domain controllers - API namespace,
 *              API-key verification, and the common permission callback
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

abstract class VAYSF_REST_Controller {

    /**
     * API namespace
     */
    const API_NAMESPACE = 'vaysf/v1';

    /**
     * Constructor
     */
    public function __construct() {
        // Register REST API routes
        add_action('rest_api_init', array($this, 'register_routes'));
    }

    /**
     * Register this controller's REST API routes
     */
    abstract public function register_routes();

	/**
	 * Verify API key from request header
	 *
	 * @param WP_REST_Request $request Request object
	 * @return bool True if API key is valid
	 */
	private function verify_api_key($request) {
		// Get API key from request header
		$api_key = $request->get_header('X-VAYSF-API-Key');
		
		// Get stored API key
		$stored_key = get_option('vaysf_api_key');
		
		// If no API key is set, this is a security risk
		if (empty($stored_key)) {
			// Log this security issue
			error_log('WARNING: No API key set in VAYSF plugin. API access should be restricted.');
			return false; // Don't allow access if no key is configured
		}
		
		// If no API key provided in request or keys don't match
		if (empty($api_key) || !hash_equals($stored_key, $api_key)) {
			return false;
		}
		
		return true;
	}

	public function check_api_permission($request) {
		// Enforce HTTPS for all API requests, not just in production
		if (!is_ssl()) {
			return new WP_Error(
				'rest_forbidden',
				esc_html__('API requests must be made over HTTPS.', 'vaysf'),
				array('status' => 403)
			);
		}
	
		// Verify API key
		if (!$this->verify_api_key($request)) {
			return new WP_Error(
				'rest_forbidden',
				esc_html__('Invalid API key.', 'vaysf'),
				array('status' => 401)
			);
		}
		
		// If API key is valid, grant access without WP user authentication
		// Remove or comment out the is_user_logged_in() check
		
		// Only perform capability checks for admin UI access
		// This section would only apply if accessed via WordPress admin
		if (is_admin()) {
			// Check if user has sf2025_read capability
			if (!current_user_can('sf2025_read')) {
				return new WP_Error(
					'rest_forbidden',
					esc_html__('You do not have permission to access this endpoint.', 'vaysf'),
					array('status' => 403)
				);
			}
			
			// Check if CRUD operations require sf2025_write capability
			$method = $request->get_method();
			if (in_array($method, array('POST', 'PUT', 'PATCH', 'DELETE')) && !current_user_can('sf2025_write')) {
				return new WP_Error(
					'rest_forbidden',
					esc_html__('You do not have permission to modify data.', 'vaysf'),
					array('status' => 403)
				);
			}
		}
		
		return true;
	}
}

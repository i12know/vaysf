<?php
/**
 * File: includes/rest-api/class-vaysf-rest-public-display.php
 * Description: Public spectator-facing schedule/advancement REST endpoints
 *              (Issue #206) - read-only, no API key
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_REST_Public_Display extends VAYSF_REST_Controller {

    /**
     * Register REST API routes
     */
    public function register_routes() {
		// Public spectator-facing schedule/results/advancement endpoints (Issue #206).
		// No API key or login, matching the existing public insurance-link pattern —
		// these are read-only and exclude scoresheet paths, coordinator identities,
		// notes, and revision history (see includes/public-display.php).
		register_rest_route(self::API_NAMESPACE, '/public/schedule', array(
			array(
				'methods' => WP_REST_Server::READABLE,
				'callback' => array($this, 'get_public_schedule'),
				'permission_callback' => '__return_true',
			),
		));

		register_rest_route(self::API_NAMESPACE, '/public/advancement', array(
			array(
				'methods' => WP_REST_Server::READABLE,
				'callback' => array($this, 'get_public_advancement'),
				'permission_callback' => '__return_true',
			),
		));
    }

    /**
     * Public read-only live schedule + reported/official scores (Issue #206).
     *
     * @param WP_REST_Request $request Request object
     * @return WP_REST_Response Response object
     */
    public function get_public_schedule($request) {
        $rows = vaysf_get_public_schedule_rows(array(
            'event' => $request->get_param('event'),
            'day' => $request->get_param('day'),
            'venue' => $request->get_param('venue'),
            'church' => $request->get_param('church'),
            'lookback_minutes' => $request->get_param('lookback_minutes'),
        ));

        return rest_ensure_response($rows);
    }

    /**
     * Public read-only confirmed semifinal/final advancement (Issue #206).
     *
     * @param WP_REST_Request $request Request object
     * @return WP_REST_Response Response object
     */
    public function get_public_advancement($request) {
        $rows = vaysf_get_public_advancement_rows(array(
            'event' => $request->get_param('event'),
        ));

        return rest_ensure_response($rows);
    }
}

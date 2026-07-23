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
     * Add no-cache headers for event-day public display endpoints.
     *
     * @param WP_REST_Response $response Response object
     * @return WP_REST_Response
     */
    private function add_public_no_cache_headers($response) {
        $response->header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
        $response->header('Pragma', 'no-cache');
        $response->header('Expires', 'Wed, 11 Jan 1984 05:00:00 GMT');
        $response->header('X-VAYSF-Plugin-Version', VAYSF_Integration::VERSION);

        return $response;
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
            'upcoming_only' => $request->get_param('upcoming_only'),
        ));

        return $this->add_public_no_cache_headers(rest_ensure_response($rows));
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

        return $this->add_public_no_cache_headers(rest_ensure_response($rows));
    }
}

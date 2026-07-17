<?php
/**
 * File: includes/rest-api/class-vaysf-rest-sync-logs.php
 * Description: Sync log REST endpoints (stubs)
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_REST_Sync_Logs extends VAYSF_REST_Controller {

    /**
     * Register REST API routes
     */
    public function register_routes() {
        // Sync log endpoints (stubs)
        register_rest_route(self::API_NAMESPACE, '/sync-logs', array(
            array(
                'methods' => WP_REST_Server::READABLE,
                'callback' => array($this, 'get_sync_logs'),
                'permission_callback' => array($this, 'check_api_permission'),
            ),
            array(
                'methods' => WP_REST_Server::CREATABLE,
                'callback' => array($this, 'create_sync_log'),
                'permission_callback' => array($this, 'check_api_permission'),
            ),
        ));
        
        register_rest_route(self::API_NAMESPACE, '/sync-logs/(?P<id>\d+)', array(
            array(
                'methods' => WP_REST_Server::EDITABLE,
                'callback' => array($this, 'update_sync_log'),
                'permission_callback' => array($this, 'check_api_permission'),
            ),
        ));
    }

    /**
     * Stub methods for sync log endpoints
     */
    public function get_sync_logs($request) {
        return rest_ensure_response(array(
            'message' => 'Get sync logs endpoint stub - Not yet implemented'
        ));
    }
    
    public function create_sync_log($request) {
        return rest_ensure_response(array(
            'message' => 'Create sync log endpoint stub - Not yet implemented'
        ));
    }
    
    public function update_sync_log($request) {
        return rest_ensure_response(array(
            'message' => 'Update sync log endpoint stub - Not yet implemented',
            'id' => $request['id']
        ));
    }
}

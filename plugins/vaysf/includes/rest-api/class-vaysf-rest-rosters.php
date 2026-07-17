<?php
/**
 * File: includes/rest-api/class-vaysf-rest-rosters.php
 * Description: Rosters REST endpoints - CRUD for church team rosters
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_REST_Rosters extends VAYSF_REST_Controller {

    /**
     * Register REST API routes
     */
    public function register_routes() {
		// Rosters endpoints
		register_rest_route(self::API_NAMESPACE, '/rosters', array(
			array(
				'methods' => WP_REST_Server::READABLE,
				'callback' => array($this, 'get_rosters'),
				'permission_callback' => array($this, 'check_api_permission'),
			),
			array(
				'methods' => WP_REST_Server::CREATABLE,
				'callback' => array($this, 'create_roster'),
				'permission_callback' => array($this, 'check_api_permission'),
			),
		));

		register_rest_route(self::API_NAMESPACE, '/rosters/(?P<id>\d+)', array(
			array(
				'methods' => WP_REST_Server::READABLE,
				'callback' => array($this, 'get_roster'),
				'permission_callback' => array($this, 'check_api_permission'),
			),
			array(
				'methods' => WP_REST_Server::EDITABLE,
				'callback' => array($this, 'update_roster'),
				'permission_callback' => array($this, 'check_api_permission'),
			),
			array(
				'methods' => WP_REST_Server::DELETABLE,
				'callback' => array($this, 'delete_roster'),
				'permission_callback' => array($this, 'check_api_permission'),
				'args' => array(
					'id' => array(
						'required' => true,
						'validate_callback' => function($param) {
							return is_numeric($param) && $param > 0;
						}
					)
				)
			),
		));
    }

    /** *******
     * Methods for rosters endpoints
     ******* */
/**
 * Get all rosters
 * 
 * @param WP_REST_Request $request Request object
 * @return WP_REST_Response Response object
 */
public function get_rosters($request) {
    global $wpdb;
    
    $table_rosters = vaysf_get_table_name('rosters');
    $table_participants = vaysf_get_table_name('participants');
    $table_churches = vaysf_get_table_name('churches');
    
    $params = $request->get_params();
    $church_code = isset($params['church_code']) ? sanitize_text_field($params['church_code']) : '';
    $participant_id = isset($params['participant_id']) ? absint($params['participant_id']) : 0;
    
    // Initialize WHERE clause array and format array
    $where = array();
    $where_format = array();
    
    // Filter by church_code if provided
    if (!empty($church_code)) {
        $where[] = "r.church_code = %s";
        $where_format[] = $church_code;
    }
    
    // Filter by participant_id if provided
    if ($participant_id > 0) {
        $where[] = "r.participant_id = %d";
        $where_format[] = $participant_id;
    }

    // *** Filter by sport_type if provided ***
    if (!empty($params['sport_type'])) {
        $where[] = "r.sport_type = %s";
        $where_format[] = sanitize_text_field($params['sport_type']);
    }

    // *** Filter by sport_format if provided ***
    if (!empty($params['sport_format'])) {
        $where[] = "r.sport_format = %s";
        $where_format[] = sanitize_text_field($params['sport_format']);
    }

    // *** NEW: Filter by sport_gender if provided ***
    if (!empty($params['sport_gender'])) {
        $where[] = "r.sport_gender = %s";
        $where_format[] = sanitize_text_field($params['sport_gender']);
    }

    $all_team_orders = !empty($params['all_team_orders']);

    // *** Filter by team_order (handles NULL effectively) ***
    if ($all_team_orders) {
        // Caller explicitly requested all team_order values for church-level analysis.
    } elseif (array_key_exists('team_order', $params)) {
        $team_order_value = $params['team_order'];
        // Treat null, 'null', 'None', or empty string from query param as DB IS NULL
        if ($team_order_value === null || 
            $team_order_value === '' || 
            strtolower((string)$team_order_value) === 'none' || 
            strtolower((string)$team_order_value) === 'null') {
            $where[] = "r.team_order IS NULL";
        } else {
            $where[] = "r.team_order = %s";
            $where_format[] = sanitize_text_field($team_order_value);
        }
    } else {
        // If team_order was NOT sent by Python (e.g., when it's None in roster_data),
        // assume it means match team_order IS NULL in the database.
        $where[] = "r.team_order IS NULL";
    }
    
    // Construct the WHERE clause string
    $where_clause = !empty($where) ? 'WHERE ' . implode(' AND ', $where) : '';
    
    // Prepare the SQL query
    // Note: $wpdb->prepare expects the base query string first, then an array of arguments.
    $query_sql = "SELECT r.*, p.first_name, p.last_name, c.church_name 
                  FROM $table_rosters r 
                  JOIN $table_participants p ON r.participant_id = p.participant_id 
                  JOIN $table_churches c ON r.church_code = c.church_code 
                  $where_clause 
                  ORDER BY r.sport_type, r.sport_gender, r.sport_format";
    
    $query = $wpdb->prepare($query_sql, $where_format);
    
    // Execute query
    $rosters = $wpdb->get_results($query, ARRAY_A);
    
    // For debugging, you can log the actual query run:
    // error_log('[VAYSF DEBUG] get_rosters SQL: ' . $wpdb->last_query);
    // error_log('[VAYSF DEBUG] get_rosters Results Count: ' . count($rosters));

    return rest_ensure_response($rosters);
}

/**
 * Get a specific roster by ID
 * 
 * @param WP_REST_Request $request Request object
 * @return WP_REST_Response|WP_Error Response object or error
 */
public function get_roster($request) {
    global $wpdb;
    
    $table_rosters = vaysf_get_table_name('rosters');
    $table_participants = vaysf_get_table_name('participants');
    $table_churches = vaysf_get_table_name('churches');
    $roster_id = absint($request['id']);
    
    $roster = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT r.*, p.first_name, p.last_name, c.church_name 
             FROM $table_rosters r 
             JOIN $table_participants p ON r.participant_id = p.participant_id 
             JOIN $table_churches c ON r.church_code = c.church_code 
             WHERE r.roster_id = %d",
            $roster_id
        ),
        ARRAY_A
    );
    
    if (!$roster) {
        return new WP_Error(
            'rest_roster_not_found',
            esc_html__('Roster not found.', 'vaysf'),
            array('status' => 404)
        );
    }
    
    return rest_ensure_response($roster);
}

/**
 * Create a new roster entry
 * 
 * @param WP_REST_Request $request Request object
 * @return WP_REST_Response|WP_Error Response object or error
 */
public function create_roster($request) {
    global $wpdb;
    
    $table_rosters = vaysf_get_table_name('rosters');
    $params = $request->get_params();
    
    $required_fields = array('church_code', 'participant_id', 'sport_type', 'sport_gender', 'sport_format');
    foreach ($required_fields as $field) {
        if (empty($params[$field])) {
            return new WP_Error(
                'rest_missing_field',
                sprintf(esc_html__('Missing required field: %s', 'vaysf'), $field),
                array('status' => 400)
            );
        }
    }
    
    $data = array(
        'church_code' => sanitize_text_field($params['church_code']),
        'participant_id' => absint($params['participant_id']),
        'sport_type' => sanitize_text_field($params['sport_type']),
        'sport_gender' => sanitize_text_field($params['sport_gender']),
        'sport_format' => sanitize_text_field($params['sport_format']),
        'team_order' => isset($params['team_order']) ? sanitize_text_field($params['team_order']) : null,
        'partner_name' => isset($params['partner_name']) ? sanitize_text_field($params['partner_name']) : null,
        'created_at' => current_time('mysql'),
        'updated_at' => current_time('mysql')
    );
    
    $result = $wpdb->insert($table_rosters, $data);
    if (false === $result) {
        return new WP_Error(
            'rest_roster_creation_failed',
            esc_html__('Failed to create roster entry.', 'vaysf'),
            array('status' => 500)
        );
    }
    
    $roster_id = $wpdb->insert_id;
    $roster = $this->get_roster(new WP_REST_Request('GET', "/vaysf/v1/rosters/$roster_id"));
    $response = rest_ensure_response($roster->data);
    $response->set_status(201);
    
    return $response;
}

/**
 * Update an existing roster entry
 * 
 * @param WP_REST_Request $request Request object
 * @return WP_REST_Response|WP_Error Response object or error
 */
public function update_roster($request) {
    global $wpdb;
    
    $table_rosters = vaysf_get_table_name('rosters');
    $roster_id = absint($request['id']);
    
    $roster = $wpdb->get_row(
        $wpdb->prepare("SELECT * FROM $table_rosters WHERE roster_id = %d", $roster_id)
    );
    
    if (!$roster) {
        return new WP_Error(
            'rest_roster_not_found',
            esc_html__('Roster not found.', 'vaysf'),
            array('status' => 404)
        );
    }
    
    $params = $request->get_params();
    $data = array();
    $format = array();
    
    if (isset($params['church_code'])) {
        $data['church_code'] = sanitize_text_field($params['church_code']);
        $format[] = '%s';
    }
    if (isset($params['participant_id'])) {
        $data['participant_id'] = absint($params['participant_id']);
        $format[] = '%d';
    }
    if (isset($params['sport_type'])) {
        $data['sport_type'] = sanitize_text_field($params['sport_type']);
        $format[] = '%s';
    }
    if (isset($params['sport_gender'])) {
        $data['sport_gender'] = sanitize_text_field($params['sport_gender']);
        $format[] = '%s';
    }
    if (isset($params['sport_format'])) {
        $data['sport_format'] = sanitize_text_field($params['sport_format']);
        $format[] = '%s';
    }
    if (isset($params['team_order'])) {
        $data['team_order'] = sanitize_text_field($params['team_order']);
        $format[] = '%s';
    }
    if (isset($params['partner_name'])) {
        $data['partner_name'] = sanitize_text_field($params['partner_name']);
        $format[] = '%s';
    }
    
    $data['updated_at'] = current_time('mysql');
    $format[] = '%s';
    
    if (empty($data)) {
        return $this->get_roster($request);
    }
    
    $result = $wpdb->update(
        $table_rosters,
        $data,
        array('roster_id' => $roster_id),
        $format,
        array('%d')
    );
    
    if (false === $result) {
        return new WP_Error(
            'rest_roster_update_failed',
            esc_html__('Failed to update roster entry.', 'vaysf'),
            array('status' => 500)
        );
    }
    
    return $this->get_roster($request);
}

/**
 * Delete a roster entry
 * 
 * @param WP_REST_Request $request Request object
 * @return WP_REST_Response|WP_Error Response object or error
 */
public function delete_roster($request) {
    global $wpdb;
    
    $table_rosters = vaysf_get_table_name('rosters');
    $roster_id = absint($request['id']);
    
    // Check if roster exists
    $roster = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT * FROM $table_rosters WHERE roster_id = %d",
            $roster_id
        )
    );
    
    if (!$roster) {
        return new WP_Error(
            'rest_roster_not_found',
            esc_html__('Roster not found.', 'vaysf'),
            array('status' => 404)
        );
    }
    
    // Delete the roster entry
    $result = $wpdb->delete(
        $table_rosters,
        array('roster_id' => $roster_id),
        array('%d')
    );
    
    if (false === $result) {
        return new WP_Error(
            'rest_roster_delete_failed',
            esc_html__('Failed to delete roster entry.', 'vaysf'),
            array('status' => 500)
        );
    }
    
    return new WP_REST_Response(
        array('message' => 'Roster deleted successfully'),
        200
    );
}
}

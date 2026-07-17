<?php
/**
 * File: includes/rest-api/class-vaysf-rest-participants.php
 * Description: Participants REST endpoints - CRUD with church join and pagination
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_REST_Participants extends VAYSF_REST_Controller {

    /**
     * Register REST API routes
     */
    public function register_routes() {
        // Participants endpoints
        register_rest_route(self::API_NAMESPACE, '/participants', array(
            array(
                'methods' => WP_REST_Server::READABLE,
                'callback' => array($this, 'get_participants'),
                'permission_callback' => array($this, 'check_api_permission'),
            ),
            array(
                'methods' => WP_REST_Server::CREATABLE,
                'callback' => array($this, 'create_participant'),
                'permission_callback' => array($this, 'check_api_permission'),
            ),
        ));
        
        register_rest_route(self::API_NAMESPACE, '/participants/(?P<id>\d+)', array(
            array(
                'methods' => WP_REST_Server::READABLE,
                'callback' => array($this, 'get_participant'),
                'permission_callback' => array($this, 'check_api_permission'),
            ),
            array(
                'methods' => WP_REST_Server::EDITABLE,
                'callback' => array($this, 'update_participant'),
                'permission_callback' => array($this, 'check_api_permission'),
            ),
        ));
    }

    /** *******
     * Methods for participant endpoints
     ******* */
/**
 * Get all participants
 * 
 * @param WP_REST_Request $request Request object
 * @return WP_REST_Response Response object
 *
 * Python hack to get participant by chm_id: participant = (self.wordpress_connector.get_participants({"chmeetings_id": chm_id}) or [None])[0]
 */
public function get_participants($request) {
    global $wpdb;
    
    $table_participants = vaysf_get_table_name('participants');
    $table_churches = vaysf_get_table_name('churches');
    
    // Parse query parameters
    $params = $request->get_params();
	$chmeetings_id = isset($params['chmeetings_id']) ? sanitize_text_field($params['chmeetings_id']) : '';  // <-- Add this line
    $church_code = isset($params['church_code']) ? sanitize_text_field($params['church_code']) : '';
    $approval_status = isset($params['approval_status']) ? sanitize_text_field($params['approval_status']) : '';
    $approval_status_not = isset($params['approval_status_not']) ? sanitize_text_field($params['approval_status_not']) : '';
    $page = isset($params['page']) ? max(1, intval($params['page'])) : 1;
    $per_page = isset($params['per_page']) ? min(100, max(1, intval($params['per_page']))) : 20;
    $search = isset($params['search']) ? sanitize_text_field($params['search']) : '';
    
    // Build WHERE clause
    $where = array();
    $where_format = array();

	if (!empty($chmeetings_id)) {  // <-- Add this condition block
		$where[] = "p.chmeetings_id = %s";
		$where_format[] = $chmeetings_id;
	}
    
    if (!empty($church_code)) {
        $where[] = "p.church_code = %s";
        $where_format[] = $church_code;
    }
    
    if (!empty($approval_status)) {
        $where[] = "p.approval_status = %s";
        $where_format[] = $approval_status;
    }
    
    if (!empty($approval_status_not)) {
        $where[] = "p.approval_status != %s";
        $where_format[] = $approval_status_not;
    }
    
    if (!empty($search)) {
        $where[] = "(p.first_name LIKE %s OR p.last_name LIKE %s OR p.email LIKE %s OR CONCAT(p.first_name, ' ', p.last_name) LIKE %s)";
        $search_term = '%' . $wpdb->esc_like($search) . '%';
        $where_format[] = $search_term;
        $where_format[] = $search_term;
        $where_format[] = $search_term;
        $where_format[] = $search_term;
    }
    
    // Combine WHERE clauses
    $where_clause = !empty($where) ? 'WHERE ' . implode(' AND ', $where) : '';
    
    // Calculate offset
    $offset = ($page - 1) * $per_page;
    
    // Prepare the query with a JOIN to get church name
    $query = $wpdb->prepare(
        "SELECT p.*, c.church_name 
        FROM $table_participants p 
        LEFT JOIN $table_churches c ON p.church_code = c.church_code 
        $where_clause 
        ORDER BY p.last_name, p.first_name 
        LIMIT %d OFFSET %d",
        array_merge($where_format, [$per_page, $offset])
    );
    
    // Get total count for pagination
    $count_query = "SELECT COUNT(*) FROM $table_participants p $where_clause";
    $total_items = $wpdb->get_var($wpdb->prepare($count_query, $where_format));
    
    // Execute query
    $participants = $wpdb->get_results($query, ARRAY_A);
    
    // Set headers for pagination
    $total_pages = ceil($total_items / $per_page);
    
    $response = rest_ensure_response($participants);
    $response->header('X-WP-Total', $total_items);
    $response->header('X-WP-TotalPages', $total_pages);
    
    return $response;
}

/**
 * Get a specific participant by ID
 * 
 * @param WP_REST_Request $request Request object
 * @return WP_REST_Response|WP_Error Response object or error
 */
public function get_participant($request) {
    global $wpdb;
    
    $table_participants = vaysf_get_table_name('participants');
    $table_churches = vaysf_get_table_name('churches');
    $participant_id = absint($request['id']);
    
    // Get participant with church name
    $participant = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT p.*, c.church_name 
            FROM $table_participants p 
            LEFT JOIN $table_churches c ON p.church_code = c.church_code 
            WHERE p.participant_id = %d",
            $participant_id
        ),
        ARRAY_A
    );
    
    // Check if participant exists
    if (!$participant) {
        return new WP_Error(
            'rest_participant_not_found',
            esc_html__('Participant not found.', 'vaysf'),
            array('status' => 404)
        );
    }
    
    return rest_ensure_response($participant);
}

/**
 * Create a new participant
 * 
 * @param WP_REST_Request $request Request object
 * @return WP_REST_Response|WP_Error Response object or error
 */
public function create_participant($request) {
    global $wpdb;
    
    $table_participants = vaysf_get_table_name('participants');
    $table_churches = vaysf_get_table_name('churches');
    
    // Get request parameters
    $params = $request->get_params();
    
    // Required fields validation
    $required_fields = array('church_code', 'first_name', 'last_name');
    
    foreach ($required_fields as $field) {
        if (empty($params[$field])) {
            return new WP_Error(
                'rest_missing_field',
                sprintf(esc_html__('Missing required field: %s', 'vaysf'), $field),
                array('status' => 400)
            );
        }
    }
    
    $church_code = sanitize_text_field($params['church_code']);
    
    // Verify church exists
    $church = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT * FROM $table_churches WHERE church_code = %s",
            $church_code
        )
    );
    
    if (!$church) {
        return new WP_Error(
            'rest_invalid_church',
            esc_html__('Invalid church code. Church does not exist.', 'vaysf'),
            array('status' => 400)
        );
    }
    
    // Check if participant with same chmeetings_id already exists
    if (!empty($params['chmeetings_id'])) {
        $existing = $wpdb->get_var(
            $wpdb->prepare(
                "SELECT participant_id FROM $table_participants WHERE chmeetings_id = %s",
                $params['chmeetings_id']
            )
        );
        
        if ($existing) {
            return new WP_Error(
                'rest_participant_exists',
                esc_html__('Participant with this ChMeetings ID already exists.', 'vaysf'),
                array('status' => 409)
            );
        }
    }
    
    // Process birthdate
    $birthdate = null;
    if (!empty($params['birthdate'])) {
        $birthdate = sanitize_text_field($params['birthdate']);
        // Validate date format (YYYY-MM-DD)
        if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $birthdate)) {
            return new WP_Error(
                'rest_invalid_date',
                esc_html__('Invalid birthdate format. Use YYYY-MM-DD.', 'vaysf'),
                array('status' => 400)
            );
        }
    }
    
    // Prepare data for insertion
    $data = array(
        'chmeetings_id' => isset($params['chmeetings_id']) ? sanitize_text_field($params['chmeetings_id']) : null,
        'church_code' => $church_code,
        'first_name' => sanitize_text_field($params['first_name']),
        'last_name' => sanitize_text_field($params['last_name']),
        'email' => isset($params['email']) ? sanitize_email($params['email']) : null,
        'phone' => isset($params['phone']) ? sanitize_text_field($params['phone']) : null,
        'gender' => isset($params['gender']) ? sanitize_text_field($params['gender']) : null,
        'birthdate' => $birthdate,
        'is_church_member' => isset($params['is_church_member']) ? (bool)$params['is_church_member'] : false,
        'primary_sport' => isset($params['primary_sport']) ? sanitize_text_field($params['primary_sport']) : null,
        'primary_format' => isset($params['primary_format']) ? sanitize_text_field($params['primary_format']) : null,
        'primary_partner' => isset($params['primary_partner']) ? sanitize_text_field($params['primary_partner']) : null,
        'secondary_sport' => isset($params['secondary_sport']) ? sanitize_text_field($params['secondary_sport']) : null,
        'secondary_format' => isset($params['secondary_format']) ? sanitize_text_field($params['secondary_format']) : null,
        'secondary_partner' => isset($params['secondary_partner']) ? sanitize_text_field($params['secondary_partner']) : null,
        'other_events' => isset($params['other_events']) ? sanitize_textarea_field($params['other_events']) : null,
	    'photo_url' => isset($params['photo_url']) ? esc_url_raw($params['photo_url']) : null,  // Add this line
        'approval_status' => isset($params['approval_status']) ? sanitize_text_field($params['approval_status']) : 'pending',
        'parent_info' => isset($params['parent_info']) ? sanitize_textarea_field($params['parent_info']) : null,
        'created_at' => current_time('mysql'),
        'updated_at' => current_time('mysql')
    );

    // Override updated_at if ChMeeting's update_on is provided
    if (isset($params['updated_at'])) {
        $updated_at = sanitize_text_field($params['updated_at']);
        if (preg_match('/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/', $updated_at)) {
            $data['updated_at'] = $updated_at;
        } else {
            return new WP_Error('invalid_datetime', 'Invalid updated_at format', array('status' => 400));
        }
    }

    // membership_claim_at_approval: only include when explicitly provided (0 or 1).
    // Omitting it lets MySQL use DEFAULT NULL for new participants who have no token yet.
    if (isset($params['membership_claim_at_approval'])) {
        $data['membership_claim_at_approval'] = (int)$params['membership_claim_at_approval'];
    }

    if (isset($params['consent_status'])) {
        $data['consent_status'] = (int)(bool)$params['consent_status'];
    }

    // Insert participant
    $result = $wpdb->insert($table_participants, $data);
    
    // Check if insertion was successful
    if (false === $result) {
        return new WP_Error(
            'rest_participant_creation_failed',
            esc_html__('Failed to create participant.', 'vaysf'),
            array('status' => 500)
        );
    }
    
    // Get the newly created participant
    $participant_id = $wpdb->insert_id;
    $participant = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT p.*, c.church_name 
            FROM $table_participants p 
            LEFT JOIN $table_churches c ON p.church_code = c.church_code 
            WHERE p.participant_id = %d",
            $participant_id
        ),
        ARRAY_A
    );
    
    // Create response
    $response = rest_ensure_response($participant);
    $response->set_status(201);
    
    return $response;
}

/**
 * Update an existing participant
 * 
 * @param WP_REST_Request $request Request object
 * @return WP_REST_Response|WP_Error Response object or error
 */
public function update_participant($request) {
    global $wpdb;
    
    $table_participants = vaysf_get_table_name('participants');
    $table_churches = vaysf_get_table_name('churches');
    $participant_id = absint($request['id']);
    
    // Check if participant exists
    $participant = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT * FROM $table_participants WHERE participant_id = %d",
            $participant_id
        )
    );
    
    if (!$participant) {
        return new WP_Error(
            'rest_participant_not_found',
            esc_html__('Participant not found.', 'vaysf'),
            array('status' => 404)
        );
    }
    
    // Get request parameters
    $params = $request->get_params();
    
    // Verify church code if provided
    if (!empty($params['church_code'])) {
        $church_code = sanitize_text_field($params['church_code']);
        $church = $wpdb->get_row(
            $wpdb->prepare(
                "SELECT * FROM $table_churches WHERE church_code = %s",
                $church_code
            )
        );
        
        if (!$church) {
            return new WP_Error(
                'rest_invalid_church',
                esc_html__('Invalid church code. Church does not exist.', 'vaysf'),
                array('status' => 400)
            );
        }
    }
    
    // Process birthdate
    $birthdate = null;
    if (!empty($params['birthdate'])) {
        $birthdate = sanitize_text_field($params['birthdate']);
        // Validate date format (YYYY-MM-DD)
        if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $birthdate)) {
            return new WP_Error(
                'rest_invalid_date',
                esc_html__('Invalid birthdate format. Use YYYY-MM-DD.', 'vaysf'),
                array('status' => 400)
            );
        }
    }
    
    // Prepare data for update
    $data = array();
    $format = array();
    
    // Only update provided fields
    if (isset($params['chmeetings_id'])) {
        $data['chmeetings_id'] = sanitize_text_field($params['chmeetings_id']);
        $format[] = '%s';
    }
    
    if (isset($params['church_code'])) {
        $data['church_code'] = sanitize_text_field($params['church_code']);
        $format[] = '%s';
    }
    
    if (isset($params['first_name'])) {
        $data['first_name'] = sanitize_text_field($params['first_name']);
        $format[] = '%s';
    }
    
    if (isset($params['last_name'])) {
        $data['last_name'] = sanitize_text_field($params['last_name']);
        $format[] = '%s';
    }
    
    if (isset($params['email'])) {
        $data['email'] = sanitize_email($params['email']);
        $format[] = '%s';
    }
    
    if (isset($params['phone'])) {
        $data['phone'] = sanitize_text_field($params['phone']);
        $format[] = '%s';
    }
    
    if (isset($params['gender'])) {
        $data['gender'] = sanitize_text_field($params['gender']);
        $format[] = '%s';
    }
    
    if (isset($params['birthdate'])) {
        $data['birthdate'] = $birthdate;
        $format[] = '%s';
    }
    
    if (isset($params['is_church_member'])) {
        $data['is_church_member'] = (bool)$params['is_church_member'];
        $format[] = '%d';
    }

    if (array_key_exists('membership_claim_at_approval', $params)) {
        $data['membership_claim_at_approval'] = is_null($params['membership_claim_at_approval'])
            ? null
            : (int)$params['membership_claim_at_approval'];
        $format[] = is_null($data['membership_claim_at_approval']) ? '%s' : '%d';
    }

    if (array_key_exists('consent_status', $params)) {
        $data['consent_status'] = is_null($params['consent_status'])
            ? null
            : (int)(bool)$params['consent_status'];
        $format[] = is_null($data['consent_status']) ? '%s' : '%d';
    }

    if (isset($params['primary_sport'])) {
        $data['primary_sport'] = sanitize_text_field($params['primary_sport']);
        $format[] = '%s';
    }
    
    if (isset($params['primary_format'])) {
        $data['primary_format'] = sanitize_text_field($params['primary_format']);
        $format[] = '%s';
    }
    
    if (isset($params['primary_partner'])) {
        $data['primary_partner'] = sanitize_text_field($params['primary_partner']);
        $format[] = '%s';
    }
    
    if (isset($params['secondary_sport'])) {
        $data['secondary_sport'] = sanitize_text_field($params['secondary_sport']);
        $format[] = '%s';
    }
    
    if (isset($params['secondary_format'])) {
        $data['secondary_format'] = sanitize_text_field($params['secondary_format']);
        $format[] = '%s';
    }
    
    if (isset($params['secondary_partner'])) {
        $data['secondary_partner'] = sanitize_text_field($params['secondary_partner']);
        $format[] = '%s';
    }
    
    if (isset($params['other_events'])) {
        $data['other_events'] = sanitize_textarea_field($params['other_events']);
        $format[] = '%s';
    }

	if (isset($params['photo_url'])) {
		$data['photo_url'] = esc_url_raw($params['photo_url']);
		$format[] = '%s';
	}
    
    if (isset($params['approval_status'])) {
        $data['approval_status'] = sanitize_text_field($params['approval_status']);
        $format[] = '%s';
    }
    
    if (isset($params['parent_info'])) {
        $data['parent_info'] = sanitize_textarea_field($params['parent_info']);
        $format[] = '%s';
    }
    
    // BUG: update the updated_at timestamp will override ChMeetings' data sent from update_on field 
    // $data['updated_at'] = current_time('mysql');
    // $format[] = '%s';

    // BUG FIX: Handle updated_at from the request
    if (isset($params['updated_at'])) {
        $updated_at = sanitize_text_field($params['updated_at']);
        // Validate datetime format (YYYY-MM-DD HH:MM:SS)
        if (preg_match('/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/', $updated_at)) {
            $data['updated_at'] = $updated_at;
            $format[] = '%s';
        } else {
            return new WP_Error('invalid_datetime', 'Invalid updated_at format', array('status' => 400));
        }
    }
    
    // If no data to update, return current participant
    if (empty($data)) {
        $participant = $wpdb->get_row(
            $wpdb->prepare(
                "SELECT p.*, c.church_name 
                FROM $table_participants p 
                LEFT JOIN $table_churches c ON p.church_code = c.church_code 
                WHERE p.participant_id = %d",
                $participant_id
            ),
            ARRAY_A
        );
        
        return rest_ensure_response($participant);
    }
    
    // Update participant
    $result = $wpdb->update(
        $table_participants,
        $data,
        array('participant_id' => $participant_id),
        $format,
        array('%d')
    );
    
    // Check if update was successful
    if (false === $result) {
        return new WP_Error(
            'rest_participant_update_failed',
            esc_html__('Failed to update participant.', 'vaysf'),
            array('status' => 500)
        );
    }
    
    // Get the updated participant
    $participant = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT p.*, c.church_name 
            FROM $table_participants p 
            LEFT JOIN $table_churches c ON p.church_code = c.church_code 
            WHERE p.participant_id = %d",
            $participant_id
        ),
        ARRAY_A
    );
    
    return rest_ensure_response($participant);
}
}

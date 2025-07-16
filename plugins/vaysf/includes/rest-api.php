<?php
/**
 * File: includes/rest-api.php
 * Description: REST API endpoints for VAYSF Integration
 * Version: 1.0.8: sf_rosters
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}


class VAYSF_REST_API {
    
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
     * Register REST API routes
     */
    public function register_routes() {
        // Churches endpoints
		register_rest_route(self::API_NAMESPACE, '/churches', array(
			array(
				'methods' => WP_REST_Server::READABLE,
				'callback' => array($this, 'get_churches'),
				'permission_callback' => array($this, 'check_api_permission'),
			),
			array(
				'methods' => WP_REST_Server::CREATABLE,
				'callback' => array($this, 'create_church'),
				'permission_callback' => array($this, 'check_api_permission'),
			),
		));

		register_rest_route(self::API_NAMESPACE, '/churches/(?P<code>[A-Za-z0-9]{3})', array(
			array(
				'methods' => WP_REST_Server::READABLE,
				'callback' => array($this, 'get_church'),
				'permission_callback' => array($this, 'check_api_permission'),
			),
			array(
				'methods' => WP_REST_Server::EDITABLE,
				'callback' => array($this, 'update_church'),
				'permission_callback' => array($this, 'check_api_permission'),
			),
		));
                
        register_rest_route(self::API_NAMESPACE, '/churches/sync-status', array(
            array(
                'methods' => WP_REST_Server::CREATABLE,
                'callback' => array($this, 'update_church_sync_status'),
                'permission_callback' => array($this, 'check_api_permission'),
            ),
        ));
        
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
                
		// Validation issues endpoints
		register_rest_route(self::API_NAMESPACE, '/validation-issues', array(
			array(
				'methods' => WP_REST_Server::READABLE,
				'callback' => array($this, 'get_validation_issues'),
				'permission_callback' => array($this, 'check_api_permission'),
			),
			array(
				'methods' => WP_REST_Server::CREATABLE,
				'callback' => array($this, 'create_validation_issue'),
				'permission_callback' => array($this, 'check_api_permission'),
			),
		));

		register_rest_route(self::API_NAMESPACE, '/validation-issues/(?P<id>\d+)', array(
			array(
				'methods' => WP_REST_Server::EDITABLE,
				'callback' => array($this, 'update_validation_issue'),
				'permission_callback' => array($this, 'check_api_permission'),
			),
		));

		register_rest_route(self::API_NAMESPACE, '/validation-issues/bulk', array(
			array(
				'methods' => WP_REST_Server::CREATABLE,
				'callback' => array($this, 'bulk_update_validation_issues'),
				'permission_callback' => array($this, 'check_api_permission'),
			),
		));

        // Approvals endpoints (stubs)
        register_rest_route(self::API_NAMESPACE, '/approvals', array(
            array(
                'methods' => WP_REST_Server::READABLE,
                'callback' => array($this, 'get_approvals'),
                'permission_callback' => array($this, 'check_api_permission'),
            ),
            array(
                'methods' => WP_REST_Server::CREATABLE,
                'callback' => array($this, 'create_approval'),
                'permission_callback' => array($this, 'check_api_permission'),
            ),
        ));

        // Add this route registration to your register_routes() method in rest-api.php
        // Insert this after the existing approval routes (around line 182)
        register_rest_route(self::API_NAMESPACE, '/approvals/(?P<id>\d+)', array(
            array(
                'methods' => WP_REST_Server::READABLE,
                'callback' => array($this, 'get_approval'),
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
            array(
                'methods' => WP_REST_Server::EDITABLE,
                'callback' => array($this, 'update_approval'),
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

		// Add route for token processing
		register_rest_route(self::API_NAMESPACE, '/approvals/process-token', array(
			array(
				'methods' => WP_REST_Server::READABLE,
				'callback' => array($this, 'process_approval_token'),
				'permission_callback' => '__return_true', // Public access
			),
		));
        
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

		// Add email endpoint in 1.0.5
		register_rest_route(self::API_NAMESPACE, '/send-email', array(
			array(
				'methods' => WP_REST_Server::CREATABLE,
				'callback' => array($this, 'send_email'),
				'permission_callback' => array($this, 'check_api_permission'),
			),
		));
    }

	/**
	 * Send email via WordPress
	 * 
	 * @param WP_REST_Request $request Request object
	 * @return WP_REST_Response|WP_Error Response object or error
	 */
public function send_email($request) {
    $params = $request->get_params();
    $required_fields = array('to', 'subject', 'message');
    foreach ($required_fields as $field) {
        if (empty($params[$field])) {
            return new WP_Error('missing_field', sprintf(__('Missing required field: %s', 'vaysf'), $field), array('status' => 400));
        }
    }

    $to = sanitize_email($params['to']);
    $subject = sanitize_text_field($params['subject']);
    $message = wp_kses_post($params['message']);
    $headers = array('Content-Type: text/html; charset=UTF-8');
    if (!empty($params['from'])) {
        $from_email = sanitize_email($params['from']);
        $headers[] = 'From: ' . $from_email;
    } else {
        $from_email = get_option('vaysf_email_from', get_option('admin_email'));
        $headers[] = 'From: Sports Fest <' . $from_email . '>';
    }

    // Add debug logging
    add_filter('wp_mail_failed', function($wp_error) {
        error_log('WP Mail Failed: ' . print_r($wp_error, true));
        return $wp_error;
    });

    $sent = wp_mail($to, $subject, $message, $headers);

    if (!$sent) {
        global $phpmailer;
        $error_info = $phpmailer ? $phpmailer->ErrorInfo : 'No PHPMailer error available';
        error_log("Email send failed details: To: $to, Subject: $subject, Error: $error_info");
        return new WP_Error('email_failed', __('Failed to send email.', 'vaysf') . " Details: $error_info", array('status' => 500));
    }

    if (get_option('vaysf_log_emails', false)) {
        global $wpdb;
        $table_name = $wpdb->prefix . 'sf_email_log';
        $wpdb->insert($table_name, array(
            'to_email' => $to,
            'subject' => $subject,
            'message' => $message,
            'sent_at' => current_time('mysql'),
            'status' => 'sent'
        ));
    }

    return rest_ensure_response(array('success' => true, 'message' => __('Email sent successfully.', 'vaysf')));
}

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

    /** *******
     * Methods for churches endpoints
     ******* */

	/**
	 * Get all churches
	 * 
	 * @param WP_REST_Request $request Request object
	 * @return WP_REST_Response Response object
	 */
	public function get_churches($request) {
		global $wpdb;
		
		$table_name = vaysf_get_table_name('churches');
		
		// Get all churches
		$churches = $wpdb->get_results("SELECT * FROM $table_name ORDER BY church_name", ARRAY_A);
		
		return rest_ensure_response($churches);
	}
        
	/**
	 * Get church by code
	 * 
	 * @param WP_REST_Request $request Request object
	 * @return WP_REST_Response|WP_Error Response object or error
	 */
	public function get_church($request) {
		global $wpdb;
		
		$table_name = vaysf_get_table_name('churches');
		$church_code = $request['code'];
		
		// Get church by code
		$church = $wpdb->get_row(
			$wpdb->prepare(
				"SELECT * FROM $table_name WHERE church_code = %s",
				$church_code
			),
			ARRAY_A
		);
		
		// Check if church exists
		if (!$church) {
			return new WP_Error(
				'rest_church_not_found',
				esc_html__('Church not found.', 'vaysf'),
				array('status' => 404)
			);
		}
		
		return rest_ensure_response($church);
	}
    
    /**
     * Create church
     * 
     * @param WP_REST_Request $request Request object
     * @return WP_REST_Response|WP_Error Response object or error
     */
    public function create_church($request) {
        global $wpdb;
        
        $table_name = vaysf_get_table_name('churches');
        
        // Get request params
        $params = $request->get_params();
        
        // Required fields
        $required_fields = array('church_code', 'church_name', 'pastor_name', 'pastor_email');
        
        // Check required fields
        foreach ($required_fields as $field) {
            if (empty($params[$field])) {
                return new WP_Error(
                    'rest_missing_field',
                    sprintf(esc_html__('Missing required field: %s', 'vaysf'), $field),
                    array('status' => 400)
                );
            }
        }
        
		// Check if church with same church_code already exists
		if (!empty($params['church_code'])) {
			$existing = $wpdb->get_var(
				$wpdb->prepare(
					"SELECT church_code FROM $table_name WHERE church_code = %s",
					$params['church_code']
				)
			);
			
			if ($existing) {
				return new WP_Error(
					'rest_church_exists',
					esc_html__('Church with this Church Code already exists.', 'vaysf'),
					array('status' => 409)
				);
			}
		}

		// Prepare data for insertion
		$data = array(
			'church_code' => isset($params['church_code']) ? sanitize_text_field($params['church_code']) : '',
			'church_name' => sanitize_text_field($params['church_name']),
			'pastor_name' => sanitize_text_field($params['pastor_name']),
			'pastor_email' => sanitize_email($params['pastor_email']),
			'pastor_phone' => isset($params['pastor_phone']) ? sanitize_text_field($params['pastor_phone']) : null,
			'church_rep_name' => isset($params['church_rep_name']) ? sanitize_text_field($params['church_rep_name']) : null,
			'church_rep_email' => isset($params['church_rep_email']) ? sanitize_email($params['church_rep_email']) : null,
			'church_rep_phone' => isset($params['church_rep_phone']) ? sanitize_text_field($params['church_rep_phone']) : null,
			'sports_ministry_level' => isset($params['sports_ministry_level']) ? absint($params['sports_ministry_level']) : 1,
			'registration_status' => isset($params['registration_status']) ? sanitize_text_field($params['registration_status']) : 'pending',
			'insurance_status' => isset($params['insurance_status']) ? sanitize_text_field($params['insurance_status']) : 'pending',
			'payment_status' => isset($params['payment_status']) ? sanitize_text_field($params['payment_status']) : 'pending',
			'created_at' => current_time('mysql'),
			'updated_at' => current_time('mysql')
		);        
        
        // Insert church
        $result = $wpdb->insert($table_name, $data);
        
        // Check if insertion was successful
        if (false === $result) {
            return new WP_Error(
                'rest_church_creation_failed',
                esc_html__('Failed to create church.', 'vaysf'),
                array('status' => 500)
            );
        }
        
        // Get the newly created church
        $church_id = $wpdb->insert_id;
        $church = $wpdb->get_row(
            $wpdb->prepare(
                "SELECT * FROM $table_name WHERE church_id = %d",
                $church_id
            ),
            ARRAY_A
        );
        
        // Create response
        $response = rest_ensure_response($church);
        $response->set_status(201);
        
        return $response;
    }

	/**
	 * Update church
	 * 
	 * @param WP_REST_Request $request Request object
	 * @return WP_REST_Response|WP_Error Response object or error
	 */
	public function update_church($request) {
		global $wpdb;
		
		$table_name = vaysf_get_table_name('churches');
		$church_code = $request['code'];
		
		// Check if church exists
		$church = $wpdb->get_row(
			$wpdb->prepare(
				"SELECT * FROM $table_name WHERE church_code = %s",
				$church_code
			)
		);
		
		if (!$church) {
			return new WP_Error(
				'rest_church_not_found',
				esc_html__('Church not found.', 'vaysf'),
				array('status' => 404)
			);
		}
		
		// Get request params
		$params = $request->get_params();
		
		// Prepare data for update - similar to before but now updating by church_code
		$data = array();
		$format = array();
		
		// Only update provided fields
		if (isset($params['church_code'])) {
			$data['church_code'] = sanitize_text_field($params['church_code']);
			$format[] = '%s';
		}

		if (isset($params['church_name'])) {
			$data['church_name'] = sanitize_text_field($params['church_name']);
			$format[] = '%s';
		}
        
        if (isset($params['pastor_name'])) {
            $data['pastor_name'] = sanitize_text_field($params['pastor_name']);
            $format[] = '%s';
        }
        
        if (isset($params['pastor_email'])) {
            $data['pastor_email'] = sanitize_email($params['pastor_email']);
            $format[] = '%s';
        }
        
        if (isset($params['pastor_phone'])) {
            $data['pastor_phone'] = sanitize_text_field($params['pastor_phone']);
            $format[] = '%s';
        }
        
        if (isset($params['church_rep_name'])) {
            $data['church_rep_name'] = sanitize_text_field($params['church_rep_name']);
            $format[] = '%s';
        }
        
        if (isset($params['church_rep_email'])) {
            $data['church_rep_email'] = sanitize_email($params['church_rep_email']);
            $format[] = '%s';
        }
        
        if (isset($params['church_rep_phone'])) {
            $data['church_rep_phone'] = sanitize_text_field($params['church_rep_phone']);
            $format[] = '%s';
        }
        
        if (isset($params['sports_ministry_level'])) {
            $data['sports_ministry_level'] = absint($params['sports_ministry_level']);
            $format[] = '%d';
        }
        
        if (isset($params['registration_status'])) {
            $data['registration_status'] = sanitize_text_field($params['registration_status']);
            $format[] = '%s';
        }
        
        if (isset($params['insurance_status'])) {
            $data['insurance_status'] = sanitize_text_field($params['insurance_status']);
            $format[] = '%s';
        }
        
        if (isset($params['payment_status'])) {
            $data['payment_status'] = sanitize_text_field($params['payment_status']);
            $format[] = '%s';
        }
     
		// Always update the updated_at timestamp
		$data['updated_at'] = current_time('mysql');
		$format[] = '%s';
		
		// Update church by church_code
		$result = $wpdb->update(
			$table_name,
			$data,
			array('church_code' => $church_code),
			$format,
			array('%s')  // Changed from %d to %s since church_code is a string
		);
		
		// Check if update was successful
		if (false === $result) {
			return new WP_Error(
				'rest_church_update_failed',
				esc_html__('Failed to update church.', 'vaysf'),
				array('status' => 500)
			);
		}
		
		// Get the updated church
		$church = $wpdb->get_row(
			$wpdb->prepare(
				"SELECT * FROM $table_name WHERE church_code = %s",
				$church_code
			),
			ARRAY_A
		);
		
		return rest_ensure_response($church);
	}
    
    /**
     * Update church sync status
     * 
     * @param WP_REST_Request $request Request object
     * @return WP_REST_Response|WP_Error Response object or error
     */
    public function update_church_sync_status($request) {
        global $wpdb;
        
        $table_name = vaysf_get_table_name('sync_log');
        
        // Get request params
        $params = $request->get_params();
        
        // Required fields
        $required_fields = array('sync_id', 'status');
        
        // Check required fields
        foreach ($required_fields as $field) {
            if (empty($params[$field])) {
                return new WP_Error(
                    'rest_missing_field',
                    sprintf(esc_html__('Missing required field: %s', 'vaysf'), $field),
                    array('status' => 400)
                );
            }
        }
        
        $sync_id = absint($params['sync_id']);
        $status = sanitize_text_field($params['status']);
        $records_processed = isset($params['records_processed']) ? absint($params['records_processed']) : 0;
        $success_count = isset($params['success_count']) ? absint($params['success_count']) : 0;
        $error_count = isset($params['error_count']) ? absint($params['error_count']) : 0;
        $error_details = isset($params['error_details']) ? sanitize_textarea_field($params['error_details']) : '';
        
        // Check if sync log exists
        $sync_log = $wpdb->get_row(
            $wpdb->prepare(
                "SELECT * FROM $table_name WHERE log_id = %d",
                $sync_id
            )
        );
        
        if (!$sync_log) {
            return new WP_Error(
                'rest_sync_log_not_found',
                esc_html__('Sync log not found.', 'vaysf'),
                array('status' => 404)
            );
        }
        
        // Prepare data for update
        $data = array(
            'status' => $status,
            'records_processed' => $records_processed,
            'success_count' => $success_count,
            'error_count' => $error_count,
            'error_details' => $error_details
        );
        
        // If status is 'completed' or 'failed', set completed_at timestamp
        if (in_array($status, array('completed', 'failed'))) {
            $data['completed_at'] = current_time('mysql');
        }
        
        // Update sync log
        $result = $wpdb->update(
            $table_name,
            $data,
            array('log_id' => $sync_id),
            array('%s', '%d', '%d', '%d', '%s', '%s'),
            array('%d')
        );
        
        // Check if update was successful
        if (false === $result) {
            return new WP_Error(
                'rest_sync_log_update_failed',
                esc_html__('Failed to update sync log.', 'vaysf'),
                array('status' => 500)
            );
        }
        
        // Get the updated sync log
        $sync_log = $wpdb->get_row(
            $wpdb->prepare(
                "SELECT * FROM $table_name WHERE log_id = %d",
                $sync_id
            ),
            ARRAY_A
        );
        
        return rest_ensure_response($sync_log);
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

    // *** NEW: Filter by sport_type if provided ***
    if (!empty($params['sport_type'])) {
        $where[] = "r.sport_type = %s";
        $where_format[] = sanitize_text_field($params['sport_type']);
    }

    // *** NEW: Filter by sport_format if provided ***
    if (!empty($params['sport_format'])) {
        $where[] = "r.sport_format = %s";
        $where_format[] = sanitize_text_field($params['sport_format']);
    }

    // *** NEW: Filter by team_order (handles NULL effectively) ***
    if (array_key_exists('team_order', $params)) {
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

/**
 * Get a single approval by ID
 * Add this method to your VAYSF_REST_API class (around line 1600, before get_approvals)
 */
public function get_approval($request) {
    global $wpdb;
    
    $table_approvals = vaysf_get_table_name('approvals');
    $table_participants = vaysf_get_table_name('participants');
    $approval_id = absint($request['id']);
    
    // Get approval with participant name
    $approval = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT a.*, p.first_name, p.last_name 
             FROM $table_approvals a
             LEFT JOIN $table_participants p ON a.participant_id = p.participant_id
             WHERE a.approval_id = %d",
            $approval_id
        ),
        ARRAY_A
    );
    
    // Check if approval exists
    if (!$approval) {
        return new WP_Error(
            'rest_approval_not_found',
            esc_html__('Approval not found.', 'vaysf'),
            array('status' => 404)
        );
    }
    
    return rest_ensure_response($approval);
}

/**
 * Get approvals - FIXED VERSION
 * Replace the get_approvals() method in your rest-api.php file (around line 1604)
 */
public function get_approvals($request) {
    global $wpdb;
    
    $table_approvals = vaysf_get_table_name('approvals');
    $table_participants = vaysf_get_table_name('participants');
    
    // Get parameters for filtering
    $params = $request->get_params();
    $participant_id = isset($params['participant_id']) ? absint($params['participant_id']) : 0;
    $church_id = isset($params['church_id']) ? absint($params['church_id']) : 0;
    $approval_status = isset($params['approval_status']) ? sanitize_text_field($params['approval_status']) : '';
    $synced = isset($params['synced_to_chmeetings']) ? (bool)$params['synced_to_chmeetings'] : null;
    
    // Build query conditions
    $where = array();
    $where_args = array();
    
    if ($participant_id > 0) {
        $where[] = 'a.participant_id = %d';
        $where_args[] = $participant_id;
    }
    
    // FIX: Add church_id filter that was missing
    if ($church_id > 0) {
        $where[] = 'a.church_id = %d';
        $where_args[] = $church_id;
    }
    
    if (!empty($approval_status)) {
        $where[] = 'a.approval_status = %s';
        $where_args[] = $approval_status;
    }
    
    if ($synced !== null) {
        $where[] = 'a.synced_to_chmeetings = %d';
        $where_args[] = $synced ? 1 : 0;
    }
    
    $where_clause = !empty($where) ? 'WHERE ' . implode(' AND ', $where) : '';
    
    // Get approvals
    $approvals = $wpdb->get_results(
        $wpdb->prepare(
            "SELECT a.*, p.first_name, p.last_name 
             FROM $table_approvals a
             LEFT JOIN $table_participants p ON a.participant_id = p.participant_id
             $where_clause
             ORDER BY a.created_at DESC",
            $where_args
        ),
        ARRAY_A
    );
    
    return rest_ensure_response($approvals);
}

/**
 * Create approval - FIXED VERSION
 * Replace the create_approval() method in your rest-api.php file (around line 1622)
 */
public function create_approval($request) {
    global $wpdb;
    
    $table_approvals = vaysf_get_table_name('approvals');
    $table_participants = vaysf_get_table_name('participants');
    
    // Get request parameters
    $params = $request->get_params();
    
    // Required fields validation
    $required_fields = array('participant_id', 'church_id', 'approval_token', 'token_expiry', 'pastor_email');
    
    foreach ($required_fields as $field) {
        if (empty($params[$field])) {
            return new WP_Error(
                'rest_missing_field',
                sprintf(esc_html__('Missing required field: %s', 'vaysf'), $field),
                array('status' => 400)
            );
        }
    }
    
    // Verify participant exists
    $participant = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT * FROM $table_participants WHERE participant_id = %d",
            $params['participant_id']
        )
    );
    
    if (!$participant) {
        return new WP_Error(
            'rest_invalid_participant',
            esc_html__('Invalid participant ID. Participant does not exist.', 'vaysf'),
            array('status' => 400)
        );
    }
    
    // Prepare data for insertion/update
    $participant_id = absint($params['participant_id']);
    $church_id = absint($params['church_id']);
    $approval_token = sanitize_text_field($params['approval_token']);
    $token_expiry = sanitize_text_field($params['token_expiry']);
    $pastor_email = sanitize_email($params['pastor_email']);
    $approval_status = isset($params['approval_status']) ? sanitize_text_field($params['approval_status']) : 'pending';
    $approval_notes = isset($params['approval_notes']) ? sanitize_textarea_field($params['approval_notes']) : null;
    $synced_to_chmeetings = isset($params['synced_to_chmeetings']) ? (bool)$params['synced_to_chmeetings'] : false;
    
    // Use INSERT ... ON DUPLICATE KEY UPDATE to handle UNIQUE constraint on (participant_id, church_id)
    $sql = "INSERT INTO $table_approvals 
            (participant_id, church_id, approval_token, token_expiry, pastor_email, approval_status, approval_date, approval_notes, synced_to_chmeetings, created_at, updated_at)
            VALUES (%d, %d, %s, %s, %s, %s, NULL, %s, %d, %s, %s)
            ON DUPLICATE KEY UPDATE
                approval_token = VALUES(approval_token),
                token_expiry = VALUES(token_expiry),
                pastor_email = VALUES(pastor_email),
                approval_status = VALUES(approval_status),
                approval_notes = VALUES(approval_notes),
                synced_to_chmeetings = VALUES(synced_to_chmeetings),
                updated_at = VALUES(updated_at)";
    
    $current_time = current_time('mysql');
    
    $result = $wpdb->query($wpdb->prepare($sql, 
        $participant_id, 
        $church_id, 
        $approval_token, 
        $token_expiry, 
        $pastor_email, 
        $approval_status, 
        $approval_notes, 
        $synced_to_chmeetings ? 1 : 0,
        $current_time,
        $current_time
    ));
    
    // Check if operation was successful
    if (false === $result) {
        error_log('Database error in create_approval: ' . $wpdb->last_error);
        return new WP_Error(
            'rest_approval_creation_failed',
            esc_html__('Failed to create approval.', 'vaysf'),
            array('status' => 500)
        );
    }
    
    // Get the approval_id - either from insert or existing record
    $approval_id = $wpdb->insert_id;
    if (!$approval_id) {
        // If insert_id is 0, it means we updated an existing record
        $approval_id = $wpdb->get_var($wpdb->prepare(
            "SELECT approval_id FROM $table_approvals WHERE participant_id = %d AND church_id = %d",
            $participant_id, $church_id
        ));
    }
    
    if (!$approval_id) {
        error_log('Could not retrieve approval_id after insert/update');
        return new WP_Error(
            'rest_approval_creation_failed',
            esc_html__('Could not retrieve approval record.', 'vaysf'),
            array('status' => 500)
        );
    }
    
    // Log successful operation
    error_log("Successfully upserted approval record - approval_id: $approval_id, participant_id: $participant_id, church_id: $church_id");
    
    // Get the complete approval record to return
    $approval = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT a.*, p.first_name, p.last_name 
             FROM $table_approvals a
             LEFT JOIN $table_participants p ON a.participant_id = p.participant_id
             WHERE a.approval_id = %d",
            $approval_id
        ),
        ARRAY_A
    );
    
    // Create response
    $response = rest_ensure_response($approval);
    $response->set_status(201);
    
    return $response;
}

/**
 * Update approval
 */
public function update_approval($request) {
    global $wpdb;
    
    $table_approvals = vaysf_get_table_name('approvals');
    $approval_id = absint($request['id']);
    
    // Check if approval exists
    $approval = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT * FROM $table_approvals WHERE approval_id = %d",
            $approval_id
        )
    );
    
    if (!$approval) {
        return new WP_Error(
            'rest_approval_not_found',
            esc_html__('Approval not found.', 'vaysf'),
            array('status' => 404)
        );
    }
    
    // Get request parameters
    $params = $request->get_params();
    
    // Prepare data for update
    $data = array();
    $format = array();
    
    if (isset($params['approval_status'])) {
        $data['approval_status'] = sanitize_text_field($params['approval_status']);
        $format[] = '%s';
        
        // If status is being updated, set approval_date
        if ($data['approval_status'] !== $approval->approval_status && 
            in_array($data['approval_status'], array('approved', 'denied'))) {
            $data['approval_date'] = current_time('mysql');
            $format[] = '%s';
        }
    }
    
    if (isset($params['approval_notes'])) {
        $data['approval_notes'] = sanitize_textarea_field($params['approval_notes']);
        $format[] = '%s';
    }
    
    if (isset($params['synced_to_chmeetings'])) {
        $data['synced_to_chmeetings'] = (bool)$params['synced_to_chmeetings'];
        $format[] = '%d';
    }
    
    // Always update updated_at
    $data['updated_at'] = current_time('mysql');
    $format[] = '%s';
    
    // If no data to update, return current approval
    if (empty($data)) {
        return new WP_Error(
            'rest_approval_no_changes',
            esc_html__('No changes provided for approval.', 'vaysf'),
            array('status' => 400)
        );
    }
    
    // Update approval
    $result = $wpdb->update(
        $table_approvals,
        $data,
        array('approval_id' => $approval_id),
        $format,
        array('%d')
    );
    
    // Check if update was successful
    if (false === $result) {
        return new WP_Error(
            'rest_approval_update_failed',
            esc_html__('Failed to update approval.', 'vaysf'),
            array('status' => 500)
        );
    }
    
    // Get the updated approval
    $approval = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT a.*, p.first_name, p.last_name 
             FROM $table_approvals a
             LEFT JOIN $table_participants p ON a.participant_id = p.participant_id
             WHERE a.approval_id = %d",
            $approval_id
        ),
        ARRAY_A
    );
    
    return rest_ensure_response($approval);
}

	/**
	 * Process approval token
	 */
	public function process_approval_token($request) {
		global $wpdb;
		
		$table_approvals = vaysf_get_table_name('approvals');
		$table_participants = vaysf_get_table_name('participants');
        $table_churches = vaysf_get_table_name('churches');

        //// Add debug logging
        error_log('DEBUG: process_approval_token - Starting token processing');

		// Get parameters
		$params = $request->get_params();
		$token = isset($params['token']) ? sanitize_text_field($params['token']) : '';
		$decision = isset($params['decision']) ? sanitize_text_field($params['decision']) : '';
		
        error_log('DEBUG: Token: ' . $token . ', Decision: ' . $decision); //// Add debug logging

		// Validate required parameters
		if (empty($token) || empty($decision)) {
            error_log('ERROR: Missing required parameters'); //// Add debug logging
			return new WP_Error(
				'rest_missing_parameter',
				esc_html__('Missing required parameters: token and decision', 'vaysf'),
				array('status' => 400)
			);
		}
		
		// Validate decision
		if (!in_array($decision, array('approve', 'deny'))) {
            error_log('ERROR: Invalid decision: ' . $decision); //// Add debug logging
			return new WP_Error(
				'rest_invalid_decision',
				esc_html__('Invalid decision. Must be approve or deny.', 'vaysf'),
				array('status' => 400)
			);
		}
		
		// Get approval by token
		$approval = $wpdb->get_row(
			$wpdb->prepare(
				"SELECT * FROM $table_approvals WHERE approval_token = %s",
				$token
			)
		);
		
		if (!$approval) {
            error_log('ERROR: Invalid token: ' . $token); //// Add debug logging
			return new WP_Error(
				'rest_invalid_token',
				esc_html__('Invalid approval token.', 'vaysf'),
				array('status' => 400)
			);
		}
	
        error_log('DEBUG: Found approval record - ID: ' . $approval->approval_id . ', Participant ID: ' . $approval->participant_id); //// Add debug logging
        
		// Check if token has expired
		$token_expiry = new DateTime($approval->token_expiry);
		$now = new DateTime();
		
		if ($token_expiry < $now) {
            error_log('ERROR: Token expired. Expiry: ' . $approval->token_expiry); //// Add debug logging
			return new WP_Error(
				'rest_token_expired',
				esc_html__('Approval token has expired.', 'vaysf'),
				array('status' => 400)
			);
		}
		
		// Check if already processed
		if ($approval->approval_status !== 'pending') {
            error_log('WARNING: Approval already processed. Current status: ' . $approval->approval_status); //// Add debug logging
			return new WP_Error(
				'rest_approval_already_processed',
				esc_html__('Approval has already been processed.', 'vaysf'),
				array('status' => 400)
			);
		}
		
		// Set approval status based on decision
		$status = $decision === 'approve' ? 'approved' : 'denied';
        error_log('DEBUG: Decision: ' . $decision . ', Setting status to: ' . $status); //// Add debug logging
        
		// Update approval
		$wpdb->update(
			$table_approvals,
			array(
				'approval_status' => $status,
				'approval_date' => current_time('mysql'),
				'updated_at' => current_time('mysql')
			),
			array('approval_id' => $approval->approval_id),
			array('%s', '%s', '%s'),
			array('%d')
		);

//// DEBUG CODE BEFORE PARTICIPANT UPDATE        
        if ($approval_result === false) {
            error_log('ERROR: Failed to update approval status: ' . $wpdb->last_error);
        } else {
            error_log('SUCCESS: Updated approval status for ID ' . $approval->approval_id . ' to ' . $status);
        }
        // Update participant status
        error_log('DEBUG: Updating participant ID: ' . $approval->participant_id . ' with status: ' . $status);
        // Verify participant exists before updating
        $participant_exists = $wpdb->get_var(
            $wpdb->prepare(
                "SELECT COUNT(*) FROM $table_participants WHERE participant_id = %d",
                $approval->participant_id
            )
        );
        if (!$participant_exists) {
            error_log('ERROR: Participant ID ' . $approval->participant_id . ' does not exist');
        } else {
            error_log('DEBUG: Participant ID ' . $approval->participant_id . ' exists, proceeding with update');        
//// DEBUG CODE BEFORE PARTICIPANT UPDATE

		// Update participant status
            $wpdb->update(
                $table_participants,
                array(
                    'approval_status' => $status,
                    'updated_at' => current_time('mysql')
                ),
                array('participant_id' => $approval->participant_id),
                array('%s', '%s'),
                array('%d')
            );

//// DEBUG CODE 
            if ($participant_result === false) {
                error_log('ERROR: Failed to update participant status: ' . $wpdb->last_error);
            } else {
                error_log('SUCCESS: Updated participant status for ID ' . $approval->participant_id . ' to ' . $status);
                // Double-check the update was applied
                $updated_status = $wpdb->get_var(
                    $wpdb->prepare(
                        "SELECT approval_status FROM $table_participants WHERE participant_id = %d",
                        $approval->participant_id
                    )
                );
                error_log('DEBUG: Verified participant status after update: ' . $updated_status);
            }
        }
//// DEBUG CODE 

		// Get participant and church data for notification
		$participant = $wpdb->get_row(
			$wpdb->prepare(
				"SELECT p.*, c.church_name, c.church_rep_name, c.church_rep_email, c.pastor_name 
				 FROM $table_participants p
				 JOIN $table_churches c ON p.church_code = c.church_code
				 WHERE p.participant_id = %d",
				$approval->participant_id
			),
			ARRAY_A
		);

//// DEBUG CODE 
        if (!$participant) {
            error_log('ERROR: Failed to retrieve participant data for notification');
        } else {
            error_log('DEBUG: Retrieved participant data for notification - Name: ' . $participant['first_name'] . ' ' . $participant['last_name']);
        }
//// DEBUG CODE 

		// Only send notification if we have the participant email
		if ($participant && !empty($participant['email'])) {
            error_log('DEBUG: Sending notification email to: ' . $participant['email']); //// Add debug logging
			// Build email content
			$subject = sprintf(
				__('Sports Fest: Your Participation Has Been %s', 'vaysf'),
				$status === 'approved' ? __('Approved', 'vaysf') : __('Denied', 'vaysf')
			);
			
			$message = sprintf(
				__('
				<h2>Sports Fest Participation Update</h2>
				
				<p>Dear %s,</p>
				
				<p>Your participation in Sports Fest has been <strong>%s</strong> by %s.</p>
				
				<p>%s</p>
				
				<p>If you have any questions, please contact your church representative, %s at %s.</p>
				
				<p>Thank you for your interest in Sports Fest!</p>
				
				<div style="margin-top: 30px; border-top: 1px solid #ccc; padding-top: 10px; font-size: 12px; color: #666;">
					<p>This is an automated message from the Sports Fest system. Please do not reply to this email.</p>
				</div>
				', 'vaysf'),
				$participant['first_name'] . ' ' . $participant['last_name'],
				$status === 'approved' ? __('approved', 'vaysf') : __('denied', 'vaysf'),
				$participant['pastor_name'],
				$status === 'approved' 
					? __('You are now officially registered for the event. Your church representative will provide you with further details about payment and participation.', 'vaysf')
					: __('If you believe this is an error, please contact your church representative for clarification.', 'vaysf'),
				$participant['church_rep_name'] ?: 'your church representative',
				$participant['church_rep_email'] ?: 'your church'
			);
			
			// Set up email headers
			$from_email = get_option('vaysf_email_from', get_option('admin_email'));
			$headers = array(
				'Content-Type: text/html; charset=UTF-8',
				'From: Sports Fest Staff <' . $from_email . '>'
			);
			
			// Add CC to church rep if available
			if (!empty($participant['church_rep_email'])) {
				$headers[] = 'Cc: ' . $participant['church_rep_name'] . ' <' . $participant['church_rep_email'] . '>';
			}
			
			// Send the email
			$email_sent = wp_mail(
				$participant['email'],
				$subject,
				$message,
				$headers
			);

//// DEBUG CODE 
            if ($email_sent) {
                error_log('SUCCESS: Email sent to ' . $participant['email']);
            } else {
                error_log('ERROR: Failed to send email to ' . $participant['email']);
            }
//// DEBUG CODE 

			// Optionally log the email if enabled
			if (get_option('vaysf_log_emails', false)) {
				global $wpdb;
				$table_email_log = $wpdb->prefix . 'sf_email_log';
				$wpdb->insert($table_email_log, array(
					'to_email' => $participant['email'],
					'subject' => $subject,
					'message' => $message,
					'sent_at' => current_time('mysql'),
					'status' => $email_sent ? 'sent' : 'failed'
				));
                error_log('DEBUG: Email logged in email_log table'); //// Add debug logging
			}
        } else { //// Add debug logging
            error_log('WARNING: Cannot send notification - missing participant email'); //// Add debug logging
		}

        // Ensure proper status return at the end of process_approval_token function
        error_log('DEBUG: Returning success response with status: ' . $status); //// Add debug logging
        return rest_ensure_response(array(
            'success' => true,
            'message' => sprintf(
                __('Participation has been %s.', 'vaysf'),
                $status === 'approved' ? __('approved', 'vaysf') : __('denied', 'vaysf')
            ),
            'status' => $status
        ));

	} // end of function process_approval_token

	/**
	 * Get validation issues
	 * 
	 * @param WP_REST_Request $request Request object
	 * @return WP_REST_Response Response object
	 */
	public function get_validation_issues($request) {
		global $wpdb;
		
		$table_issues = vaysf_get_table_name('validation_issues');
		$table_churches = vaysf_get_table_name('churches');
		$table_participants = vaysf_get_table_name('participants');
		
		// Parse query parameters
		$params = $request->get_params();
		$church_id = isset($params['church_id']) ? absint($params['church_id']) : 0;
		$participant_id = isset($params['participant_id']) ? absint($params['participant_id']) : 0;
		$issue_type = isset($params['issue_type']) ? sanitize_text_field($params['issue_type']) : '';
		$rule_level = isset($params['rule_level']) ? sanitize_text_field($params['rule_level']) : '';
		$severity = isset($params['severity']) ? sanitize_text_field($params['severity']) : '';
		$sport_type = isset($params['sport_type']) ? sanitize_text_field($params['sport_type']) : '';
		$status = isset($params['status']) ? sanitize_text_field($params['status']) : 'open';
		$page = isset($params['page']) ? max(1, intval($params['page'])) : 1;
		$per_page = isset($params['per_page']) ? min(100, max(1, intval($params['per_page']))) : 20;
		
		// Build WHERE clause
		$where = array();
		$where_format = array();
		
		if ($church_id > 0) {
			$where[] = "i.church_id = %d";
			$where_format[] = $church_id;
		}
		
		if ($participant_id > 0) {
			$where[] = "i.participant_id = %d";
			$where_format[] = $participant_id;
		}
		
		if (!empty($issue_type)) {
			$where[] = "i.issue_type = %s";
			$where_format[] = $issue_type;
		}
		
		if (!empty($rule_level)) {
			$where[] = "i.rule_level = %s";
			$where_format[] = $rule_level;
		}
		
		if (!empty($severity)) {
			$where[] = "i.severity = %s";
			$where_format[] = $severity;
		}
		
		if (!empty($sport_type)) {
			$where[] = "i.sport_type = %s";
			$where_format[] = $sport_type;
		}
		
		if (!empty($status)) {
			$where[] = "i.status = %s";
			$where_format[] = $status;
		}
		
		// Combine WHERE clauses
		$where_clause = !empty($where) ? 'WHERE ' . implode(' AND ', $where) : '';
		
		// Calculate offset
		$offset = ($page - 1) * $per_page;
		
		// Prepare the query with JOINs to get church and participant names
		$query = $wpdb->prepare(
			"SELECT i.*, c.church_name, p.first_name, p.last_name 
			 FROM $table_issues i 
			 LEFT JOIN $table_churches c ON i.church_id = c.church_id 
			 LEFT JOIN $table_participants p ON i.participant_id = p.participant_id 
			 $where_clause 
			 ORDER BY i.created_at DESC 
			 LIMIT %d OFFSET %d",
			array_merge($where_format, [$per_page, $offset])
		);
		
		// Get total count for pagination
		$count_query = "SELECT COUNT(*) FROM $table_issues i $where_clause";
		$total_items = $wpdb->get_var($wpdb->prepare($count_query, $where_format));
		
		// Execute query
		$issues = $wpdb->get_results($query, ARRAY_A);
		
		// Set headers for pagination
		$total_pages = ceil($total_items / $per_page);
		
		$response = rest_ensure_response($issues);
		$response->header('X-WP-Total', $total_items);
		$response->header('X-WP-TotalPages', $total_pages);
		
		return $response;
	}

	/**
	 * Create a validation issue
	 * 
	 * @param WP_REST_Request $request Request object
	 * @return WP_REST_Response|WP_Error Response object or error
	 */
	public function create_validation_issue($request) {
		global $wpdb;
		
		$table_issues = vaysf_get_table_name('validation_issues');
		$table_churches = vaysf_get_table_name('churches');
		
		// Get request parameters
		$params = $request->get_params();
		
		// Required fields validation
		$required_fields = array('church_id', 'issue_type', 'issue_description');
		
		foreach ($required_fields as $field) {
			if (empty($params[$field])) {
				return new WP_Error(
					'rest_missing_field',
					sprintf(esc_html__('Missing required field: %s', 'vaysf'), $field),
					array('status' => 400)
				);
			}
		}
		
		$church_id = absint($params['church_id']);
		
		// Verify church exists
		$church = $wpdb->get_row(
			$wpdb->prepare(
				"SELECT * FROM $table_churches WHERE church_id = %d",
				$church_id
			)
		);
		
		if (!$church) {
			return new WP_Error(
				'rest_invalid_church',
				esc_html__('Invalid church ID. Church does not exist.', 'vaysf'),
				array('status' => 400)
			);
		}
		
		// Prepare data for insertion
		$data = array(
			'church_id' => $church_id,
			'participant_id' => isset($params['participant_id']) ? absint($params['participant_id']) : null,
			'issue_type' => sanitize_text_field($params['issue_type']),
			'issue_description' => sanitize_textarea_field($params['issue_description']),
			'rule_code' => isset($params['rule_code']) ? sanitize_text_field($params['rule_code']) : null,
			'rule_level' => isset($params['rule_level']) ? sanitize_text_field($params['rule_level']) : null,
			'severity' => isset($params['severity']) ? sanitize_text_field($params['severity']) : 'ERROR',
			'sport_type' => isset($params['sport_type']) ? sanitize_text_field($params['sport_type']) : null,
			'sport_format' => isset($params['sport_format']) ? sanitize_text_field($params['sport_format']) : null,
			'status' => isset($params['status']) ? sanitize_text_field($params['status']) : 'open',
			'reported_at' => current_time('mysql'),
			'created_at' => current_time('mysql'),
			'updated_at' => current_time('mysql')
		);
		
		// Insert validation issue
		$result = $wpdb->insert($table_issues, $data);
		
		// Check if insertion was successful
		if (false === $result) {
			return new WP_Error(
				'rest_validation_issue_creation_failed',
				esc_html__('Failed to create validation issue.', 'vaysf'),
				array('status' => 500)
			);
		}
		
		// Get the newly created issue
		$issue_id = $wpdb->insert_id;
		$issue = $wpdb->get_row(
			$wpdb->prepare(
				"SELECT i.*, c.church_name 
				 FROM $table_issues i 
				 LEFT JOIN $table_churches c ON i.church_id = c.church_id 
				 WHERE i.issue_id = %d",
				$issue_id
			),
			ARRAY_A
		);
		
		// Create response
		$response = rest_ensure_response($issue);
		$response->set_status(201);
		
		return $response;
	}

	/**
	 * Update a validation issue
	 * 
	 * @param WP_REST_Request $request Request object
	 * @return WP_REST_Response|WP_Error Response object or error
	 */
	public function update_validation_issue($request) {
		global $wpdb;
		
		$table_issues = vaysf_get_table_name('validation_issues');
		$issue_id = absint($request['id']);
		
		// Check if issue exists
		$issue = $wpdb->get_row(
			$wpdb->prepare(
				"SELECT * FROM $table_issues WHERE issue_id = %d",
				$issue_id
			)
		);
		
		if (!$issue) {
			return new WP_Error(
				'rest_validation_issue_not_found',
				esc_html__('Validation issue not found.', 'vaysf'),
				array('status' => 404)
			);
		}
		
		// Get request parameters
		$params = $request->get_params();
		
		// Prepare data for update
		$data = array();
		$format = array();
		
		// Only update provided fields
		if (isset($params['issue_type'])) {
			$data['issue_type'] = sanitize_text_field($params['issue_type']);
			$format[] = '%s';
		}
		
		if (isset($params['issue_description'])) {
			$data['issue_description'] = sanitize_textarea_field($params['issue_description']);
			$format[] = '%s';
		}
		
		if (isset($params['rule_code'])) {
			$data['rule_code'] = sanitize_text_field($params['rule_code']);
			$format[] = '%s';
		}
		
		if (isset($params['rule_level'])) {
			$data['rule_level'] = sanitize_text_field($params['rule_level']);
			$format[] = '%s';
		}
		
		if (isset($params['severity'])) {
			$data['severity'] = sanitize_text_field($params['severity']);
			$format[] = '%s';
		}
		
		if (isset($params['sport_type'])) {
			$data['sport_type'] = sanitize_text_field($params['sport_type']);
			$format[] = '%s';
		}
		
		if (isset($params['sport_format'])) {
			$data['sport_format'] = sanitize_text_field($params['sport_format']);
			$format[] = '%s';
		}
		
		if (isset($params['status'])) {
			$data['status'] = sanitize_text_field($params['status']);
			$format[] = '%s';
			
			// If status is being set to 'resolved', set resolved_at timestamp
			if ($params['status'] === 'resolved' && $issue->status !== 'resolved') {
				$data['resolved_at'] = current_time('mysql');
				$format[] = '%s';
			} 
			// If status is being changed from 'resolved' to something else, clear resolved_at
			else if ($params['status'] !== 'resolved' && $issue->status === 'resolved') {
				$data['resolved_at'] = null;
				$format[] = '%s';
			}
		}
		
		// Always update the updated_at timestamp
		$data['updated_at'] = current_time('mysql');
		$format[] = '%s';
		
		// If no data to update, return current issue
		if (empty($data)) {
			return new WP_Error(
				'rest_validation_issue_no_changes',
				esc_html__('No changes provided for validation issue.', 'vaysf'),
				array('status' => 400)
			);
		}
		
		// Update validation issue
		$result = $wpdb->update(
			$table_issues,
			$data,
			array('issue_id' => $issue_id),
			$format,
			array('%d')
		);
		
		// Check if update was successful
		if (false === $result) {
			return new WP_Error(
				'rest_validation_issue_update_failed',
				esc_html__('Failed to update validation issue.', 'vaysf'),
				array('status' => 500)
			);
		}
		
		// Get the updated issue
		$issue = $wpdb->get_row(
			$wpdb->prepare(
				"SELECT i.*, c.church_name 
				 FROM $table_issues i 
				 LEFT JOIN $table_churches c ON i.church_id = c.church_id 
				 WHERE i.issue_id = %d",
				$issue_id
			),
			ARRAY_A
		);
		
		return rest_ensure_response($issue);
	}

	/**
	 * Bulk update validation issues
	 * 
	 * @param WP_REST_Request $request Request object
	 * @return WP_REST_Response|WP_Error Response object or error
	 */
	public function bulk_update_validation_issues($request) {
		global $wpdb;
		
		$table_issues = vaysf_get_table_name('validation_issues');
		
		// Get request parameters
		$params = $request->get_params();
		
		// Required fields validation
		$required_fields = array('issue_ids', 'status');
		
		foreach ($required_fields as $field) {
			if (empty($params[$field])) {
				return new WP_Error(
					'rest_missing_field',
					sprintf(esc_html__('Missing required field: %s', 'vaysf'), $field),
					array('status' => 400)
				);
			}
		}
		
		$issue_ids = $params['issue_ids'];
		$status = sanitize_text_field($params['status']);
		
		if (!is_array($issue_ids) || empty($issue_ids)) {
			return new WP_Error(
				'rest_invalid_parameter',
				esc_html__('Invalid issue_ids parameter. Must be a non-empty array.', 'vaysf'),
				array('status' => 400)
			);
		}
		
		// Sanitize issue IDs
		$issue_ids = array_map('absint', $issue_ids);
		
		// Prepare data for update
		$data = array(
			'status' => $status,
			'updated_at' => current_time('mysql')
		);
		
		// If status is 'resolved', set resolved_at timestamp
		if ($status === 'resolved') {
			$data['resolved_at'] = current_time('mysql');
		} else {
			// If changing to non-resolved status, clear resolved_at
			$data['resolved_at'] = null;
		}
		
		// Build IN clause for issue IDs
		$placeholders = implode(',', array_fill(0, count($issue_ids), '%d'));
		
		// Update validation issues
		$query = $wpdb->prepare(
			"UPDATE $table_issues SET 
			 status = %s, 
			 resolved_at = " . ($status === 'resolved' ? '%s' : 'NULL') . ", 
			 updated_at = %s 
			 WHERE issue_id IN ($placeholders)",
			array_merge(
				[$status],
				$status === 'resolved' ? [current_time('mysql')] : [],
				[current_time('mysql')],
				$issue_ids
			)
		);
		
		$result = $wpdb->query($query);
		
		// Check if update was successful
		if (false === $result) {
			return new WP_Error(
				'rest_validation_issues_update_failed',
				esc_html__('Failed to update validation issues.', 'vaysf'),
				array('status' => 500)
			);
		}
		
		return rest_ensure_response(array(
			'success' => true,
			'message' => sprintf(esc_html__('Successfully updated %d validation issues.', 'vaysf'), $result),
			'updated_count' => $result
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

// Initialize REST API
new VAYSF_REST_API();

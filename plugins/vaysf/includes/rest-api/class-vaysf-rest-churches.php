<?php
/**
 * File: includes/rest-api/class-vaysf-rest-churches.php
 * Description: Churches REST endpoints - CRUD, sync status, and the public
 *              insurance request-link/upload flow (Issue #154)
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_REST_Churches extends VAYSF_REST_Controller {

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
		// Insurance upload endpoints (Issue #154) - public, no API key.
		// Security rests on the per-church token, not on an API key.
		register_rest_route(self::API_NAMESPACE, '/insurance/request-link', array(
			array(
				'methods' => WP_REST_Server::CREATABLE,
				'callback' => array($this, 'request_insurance_link'),
				'permission_callback' => '__return_true',
			),
		));

		register_rest_route(self::API_NAMESPACE, '/insurance/upload', array(
			array(
				'methods' => WP_REST_Server::CREATABLE,
				'callback' => array($this, 'upload_insurance'),
				'permission_callback' => '__return_true',
			),
		));
    }

	/**
	 * Request a one-time insurance upload link (Issue #154, Path 1).
	 *
	 * Public endpoint. Always returns the same generic 200 response so that a
	 * caller cannot use it to enumerate which church codes or rep emails exist.
	 *
	 * @param WP_REST_Request $request Request object
	 * @return WP_REST_Response Response object
	 */
	public function request_insurance_link($request) {
		global $wpdb;

		$params = $request->get_params();
		$church_code = isset($params['church_code']) ? strtoupper(sanitize_text_field($params['church_code'])) : '';
		$email = isset($params['email']) ? sanitize_email($params['email']) : '';
		$upload_page_url = isset($params['upload_page_url']) ? esc_url_raw($params['upload_page_url']) : '';

		if (!empty($upload_page_url)) {
			$home_host = wp_parse_url(home_url(), PHP_URL_HOST);
			$page_host = wp_parse_url($upload_page_url, PHP_URL_HOST);
			if (empty($page_host) || strcasecmp($home_host, $page_host) !== 0) {
				$upload_page_url = '';
			}
		}

		// Generic response used for every outcome (found, not found, wrong email).
		$generic = rest_ensure_response(array(
			'message' => esc_html__('If we found your church, an email is on its way.', 'vaysf'),
		));

		if (empty($church_code) || empty($email)) {
			return $generic;
		}

		$table_churches = vaysf_get_table_name('churches');
		$church = $wpdb->get_row(
			$wpdb->prepare(
				"SELECT * FROM $table_churches WHERE church_code = %s",
				$church_code
			),
			ARRAY_A
		);

		// Only proceed when the church exists and the email matches the
		// registered church rep (case-insensitive). Do not reveal the outcome.
		if ($church && !empty($church['church_rep_email'])
			&& strcasecmp(trim($email), trim($church['church_rep_email'])) === 0) {

			$token = bin2hex(random_bytes(32)); // 64 hex chars, fits VARCHAR(64)
			$expiry_hours = absint(get_option('vaysf_insurance_token_expiry_hours', 48));
			if ($expiry_hours < 1) {
				$expiry_hours = 48;
			}
			$expiry = date('Y-m-d H:i:s', current_time('timestamp') + ($expiry_hours * HOUR_IN_SECONDS));

			$wpdb->update(
				$table_churches,
				array(
					'insurance_token'        => $token,
					'insurance_token_expiry' => $expiry,
					'updated_at'             => current_time('mysql'),
				),
				array('church_code' => $church_code),
				array('%s', '%s', '%s'),
				array('%s')
			);

			vaysf_send_insurance_link_email($church, $token, $expiry, $upload_page_url);
		}

		return $generic;
	}

	/**
	 * Accept a proof-of-insurance PDF upload via a one-time token (Issue #154).
	 *
	 * Public endpoint guarded by the per-church token. Validates the token and
	 * the uploaded file, stores the PDF under wp-content/uploads/vaysf/insurance/,
	 * and advances insurance_status to 'submitted'.
	 *
	 * @param WP_REST_Request $request Request object
	 * @return WP_REST_Response|WP_Error Response object or error
	 */
	public function upload_insurance($request) {
		global $wpdb;

		$params = $request->get_params();
		$token = isset($params['token']) ? sanitize_text_field($params['token']) : '';

		if (empty($token)) {
			return new WP_Error(
				'rest_missing_token',
				esc_html__('Missing upload token.', 'vaysf'),
				array('status' => 410)
			);
		}

		$table_churches = vaysf_get_table_name('churches');
		$church = $wpdb->get_row(
			$wpdb->prepare(
				"SELECT * FROM $table_churches WHERE insurance_token = %s",
				$token
			),
			ARRAY_A
		);

		// Treat an unknown token the same as an expired one (410) so the page
		// can offer to request a fresh link without leaking token validity.
		if (!$church) {
			return new WP_Error(
				'rest_invalid_token',
				esc_html__('This link has expired.', 'vaysf'),
				array('status' => 410)
			);
		}

		// Expiry check.
		if (empty($church['insurance_token_expiry'])
			|| strtotime($church['insurance_token_expiry']) < current_time('timestamp')) {
			return new WP_Error(
				'rest_token_expired',
				esc_html__('This link has expired.', 'vaysf'),
				array('status' => 410)
			);
		}

		// Fetch the uploaded file.
		$files = $request->get_file_params();
		if (empty($files['file']) || !isset($files['file']['tmp_name'])) {
			return new WP_Error(
				'rest_no_file',
				esc_html__('No file was uploaded.', 'vaysf'),
				array('status' => 400)
			);
		}

		$stored = vaysf_store_insurance_pdf_for_church($church, $files['file']);
		if (is_wp_error($stored)) {
			return $stored;
		}

		return rest_ensure_response(array(
			'success' => true,
			'message' => esc_html__('Thank you. Your proof of insurance has been received.', 'vaysf'),
		));
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

		if (isset($params['insurance_file_url'])) {
			$data['insurance_file_url'] = esc_url_raw($params['insurance_file_url']);
		}

		if (isset($params['insurance_uploaded_at'])) {
			$uploaded_at = sanitize_text_field($params['insurance_uploaded_at']);
			if (preg_match('/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/', $uploaded_at)) {
				$data['insurance_uploaded_at'] = $uploaded_at;
			} else {
				return new WP_Error('invalid_datetime', 'Invalid insurance_uploaded_at format', array('status' => 400));
			}
		}
        
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

        // Insurance file fields written by the middleware sync path (Issue #154,
        // Path 2). Token columns are intentionally NOT writable through this
        // API-key endpoint - they are managed only by the public upload flow.
        if (isset($params['insurance_file_url'])) {
            $data['insurance_file_url'] = esc_url_raw($params['insurance_file_url']);
            $format[] = '%s';
        }

        if (isset($params['insurance_uploaded_at'])) {
            $uploaded_at = sanitize_text_field($params['insurance_uploaded_at']);
            if (preg_match('/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/', $uploaded_at)) {
                $data['insurance_uploaded_at'] = $uploaded_at;
                $format[] = '%s';
            } else {
                return new WP_Error('invalid_datetime', 'Invalid insurance_uploaded_at format', array('status' => 400));
            }
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
}

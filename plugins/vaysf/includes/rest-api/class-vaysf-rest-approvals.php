<?php
/**
 * File: includes/rest-api/class-vaysf-rest-approvals.php
 * Description: Pastor approval REST endpoints - CRUD and public token processing
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_REST_Approvals extends VAYSF_REST_Controller {

    /**
     * Register REST API routes
     */
    public function register_routes() {
        // Approvals endpoints (stubs)
        register_rest_route(self::API_NAMESPACE, '/approvals', array(
            array(
                'methods' => WP_REST_Server::READABLE,
                'callback' => array($this, 'get_approvals'),
                'permission_callback' => array($this, 'check_api_permission'),
                // Without 'args', WordPress silently drops unrecognized query
                // parameters before the callback sees them (see Issue #61).
                'args' => array(
                    'participant_id'       => array('type' => 'integer', 'required' => false),
                    'church_id'            => array('type' => 'integer', 'required' => false),
                    'approval_status'      => array('type' => 'string',  'required' => false),
                    'synced_to_chmeetings' => array('type' => 'boolean', 'required' => false),
                ),
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
                approval_date = VALUES(approval_date),
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

    // Minimal success response. We deliberately skip a second SELECT with
    // JOIN on participants here — the caller only needs a truthy signal,
    // and the previous JOIN path referenced an undefined $table_participants
    // which produced a malformed response body (see Issue #61 follow-up).
    return rest_ensure_response(array(
        'approval_id' => $approval_id,
        'updated'     => true,
        'fields'      => array_keys($data),
    ));
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
		$approval_result = $wpdb->update(
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
            $participant_result = $wpdb->update(
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
}

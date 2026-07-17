<?php
/**
 * File: includes/rest-api/class-vaysf-rest-validation-issues.php
 * Description: Validation issue REST endpoints - CRUD and bulk status updates
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_REST_Validation_Issues extends VAYSF_REST_Controller {

    /**
     * Register REST API routes
     */
    public function register_routes() {
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
    }

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
}

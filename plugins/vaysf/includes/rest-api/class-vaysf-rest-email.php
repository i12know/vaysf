<?php
/**
 * File: includes/rest-api/class-vaysf-rest-email.php
 * Description: Send-email REST endpoint used by the middleware (v1.0.5)
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_REST_Email extends VAYSF_REST_Controller {

    /**
     * Register REST API routes
     */
    public function register_routes() {
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
    $email_args = array(
        'from' => isset($params['from']) ? $params['from'] : '',
        'cc'   => isset($params['cc']) ? $params['cc'] : array(),
        'bcc'  => isset($params['bcc']) ? $params['bcc'] : array(),
    );

    // Capture mail failures; use a variable so remove_filter() can clean up after use.
    $mail_fail_handler = function($wp_error) {
        error_log('WP Mail Failed: ' . print_r($wp_error, true));
        return $wp_error;
    };
    add_filter('wp_mail_failed', $mail_fail_handler);

    $sent = vaysf_send_email($to, $subject, $message, $email_args);

    remove_filter('wp_mail_failed', $mail_fail_handler);

    if (!$sent) {
        global $phpmailer;
        $error_info = $phpmailer ? $phpmailer->ErrorInfo : 'No PHPMailer error available';
        error_log("Email send failed details: To: $to, Subject: $subject, Error: $error_info");
        return new WP_Error('email_failed', __('Failed to send email.', 'vaysf') . " Details: $error_info", array('status' => 500));
    }

    return rest_ensure_response(array(
        'success' => true,
        'message' => __('Email sent successfully.', 'vaysf'),
        'cc_count' => count(vaysf_normalize_email_list($email_args['cc'])),
        'bcc_count' => count(vaysf_normalize_email_list($email_args['bcc'])),
    ));
}
}

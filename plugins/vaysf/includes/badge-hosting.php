<?php
/**
 * Public hosting endpoint for generated athlete badge PNGs.
 *
 * Badges are intentionally stored under WordPress uploads because they are
 * public event credentials, unlike result score-sheet scans.
 */

if (!defined('ABSPATH')) {
	exit;
}

const VAYSF_BADGE_MAX_BYTES = 5242880; // 5 MB.
const VAYSF_BADGE_WIDTH = 1080;
const VAYSF_BADGE_HEIGHT = 1920;

add_action('rest_api_init', 'vaysf_register_badge_hosting_routes');

function vaysf_register_badge_hosting_routes() {
	register_rest_route('vaysf/v1', '/badges', array(
		'methods' => 'POST',
		'callback' => 'vaysf_upload_badge_png',
		'permission_callback' => 'vaysf_badge_hosting_permission',
	));

	register_rest_route('vaysf/v1', '/badges/(?P<filename>[A-Za-z0-9_.-]+)', array(
		'methods' => 'DELETE',
		'callback' => 'vaysf_delete_badge_png',
		'permission_callback' => 'vaysf_badge_hosting_permission',
		'args' => array(
			'filename' => array(
				'required' => true,
				'validate_callback' => 'vaysf_is_safe_badge_filename',
			),
		),
	));
}

function vaysf_badge_hosting_permission($request) {
	if (is_user_logged_in() && current_user_can('manage_options')) {
		return true;
	}

	$stored_key = get_option('vaysf_api_key');
	if (empty($stored_key)) {
		error_log('WARNING: No API key set in VAYSF plugin. Badge upload API access is disabled.');
		return new WP_Error(
			'rest_forbidden',
			esc_html__('Badge upload API key is not configured.', 'vaysf'),
			array('status' => 401)
		);
	}

	$api_key = $request->get_header('X-VAYSF-API-Key');
	if (empty($api_key) || !hash_equals($stored_key, $api_key)) {
		return new WP_Error(
			'rest_forbidden',
			esc_html__('Invalid API key.', 'vaysf'),
			array('status' => 401)
		);
	}

	return true;
}

function vaysf_upload_badge_png($request) {
	$files = $request->get_file_params();
	$file = $files['badge'] ?? $files['file'] ?? null;

	if (empty($file) || empty($file['tmp_name'])) {
		return new WP_Error(
			'rest_no_file',
			esc_html__('No badge PNG was uploaded.', 'vaysf'),
			array('status' => 400)
		);
	}

	if (!empty($file['error'])) {
		return new WP_Error(
			'rest_upload_error',
			sprintf(esc_html__('Badge upload failed with PHP error code %d.', 'vaysf'), (int) $file['error']),
			array('status' => 400)
		);
	}

	$filename = $request->get_param('filename');
	$filename = $filename ? sanitize_file_name(wp_unslash($filename)) : sanitize_file_name($file['name']);
	if (!vaysf_is_safe_badge_filename($filename)) {
		return new WP_Error(
			'rest_bad_filename',
			esc_html__('Badge filename must be a safe .png filename.', 'vaysf'),
			array('status' => 400)
		);
	}

	if ((int) $file['size'] <= 0 || (int) $file['size'] > VAYSF_BADGE_MAX_BYTES) {
		return new WP_Error(
			'rest_bad_size',
			esc_html__('Badge PNG is empty or exceeds the size limit.', 'vaysf'),
			array('status' => 400)
		);
	}

	$image_info = @getimagesize($file['tmp_name']);
	if (
		!is_array($image_info)
		|| (int) $image_info[0] !== VAYSF_BADGE_WIDTH
		|| (int) $image_info[1] !== VAYSF_BADGE_HEIGHT
		|| ($image_info['mime'] ?? '') !== 'image/png'
	) {
		return new WP_Error(
			'rest_bad_image',
			sprintf(
				esc_html__('Badge must be a %1$dx%2$d PNG image.', 'vaysf'),
				VAYSF_BADGE_WIDTH,
				VAYSF_BADGE_HEIGHT
			),
			array('status' => 400)
		);
	}

	$filetype = wp_check_filetype_and_ext(
		$file['tmp_name'],
		$filename,
		array('png' => 'image/png')
	);
	if (($filetype['ext'] ?? '') !== 'png' || ($filetype['type'] ?? '') !== 'image/png') {
		return new WP_Error(
			'rest_bad_mime',
			esc_html__('Badge file type must be PNG.', 'vaysf'),
			array('status' => 400)
		);
	}

	$target = vaysf_badge_upload_target();
	if (is_wp_error($target)) {
		return $target;
	}

	$destination = trailingslashit($target['dir']) . $filename;
	if (file_exists($destination) && !wp_delete_file($destination)) {
		return new WP_Error(
			'rest_replace_failed',
			esc_html__('Could not replace the existing badge file.', 'vaysf'),
			array('status' => 500)
		);
	}

	if (!move_uploaded_file($file['tmp_name'], $destination)) {
		return new WP_Error(
			'rest_store_failed',
			esc_html__('Could not store uploaded badge file.', 'vaysf'),
			array('status' => 500)
		);
	}
	@chmod($destination, 0644);

	return rest_ensure_response(array(
		'filename' => $filename,
		'url' => trailingslashit($target['url']) . rawurlencode($filename),
		'size' => filesize($destination),
		'width' => VAYSF_BADGE_WIDTH,
		'height' => VAYSF_BADGE_HEIGHT,
		'sha256' => hash_file('sha256', $destination),
	));
}

function vaysf_delete_badge_png($request) {
	$filename = sanitize_file_name((string) $request['filename']);
	if (!vaysf_is_safe_badge_filename($filename)) {
		return new WP_Error(
			'rest_bad_filename',
			esc_html__('Badge filename must be a safe .png filename.', 'vaysf'),
			array('status' => 400)
		);
	}

	$target = vaysf_badge_upload_target();
	if (is_wp_error($target)) {
		return $target;
	}

	$path = trailingslashit($target['dir']) . $filename;
	$deleted = false;
	if (file_exists($path)) {
		$deleted = wp_delete_file($path);
	}

	return rest_ensure_response(array(
		'filename' => $filename,
		'deleted' => (bool) $deleted,
	));
}

function vaysf_is_safe_badge_filename($filename, $request = null, $key = null) {
	return is_string($filename) && 1 === preg_match('/^[A-Za-z0-9_.-]+\.png$/', $filename);
}

function vaysf_badge_upload_target() {
	$uploads = wp_upload_dir();
	if (!empty($uploads['error'])) {
		return new WP_Error(
			'rest_upload_dir',
			esc_html($uploads['error']),
			array('status' => 500)
		);
	}

	$dir = trailingslashit($uploads['basedir']) . 'vaysf/badges';
	$url = trailingslashit($uploads['baseurl']) . 'vaysf/badges';
	if (!wp_mkdir_p($dir)) {
		return new WP_Error(
			'rest_mkdir_failed',
			esc_html__('Could not create the badge upload directory.', 'vaysf'),
			array('status' => 500)
		);
	}

	$index_file = trailingslashit($dir) . 'index.php';
	if (!file_exists($index_file)) {
		file_put_contents($index_file, "<?php\n// Silence is golden.\n");
	}

	return array(
		'dir' => $dir,
		'url' => $url,
	);
}

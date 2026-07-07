<?php
/**
 * Public proof-of-insurance upload page (Issue #154).
 *
 * Two states:
 *   State A (no ?token): show the Church Code + Email request form.
 *   State B (?token=xxx): validate the token; show the PDF upload form if it is
 *                         valid, or an expiry notice with a path to request a
 *                         new link if it is not.
 *
 * Form submissions are handled client-side via the public REST endpoints:
 *   POST /wp-json/vaysf/v1/insurance/request-link
 *   POST /wp-json/vaysf/v1/insurance/upload
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

$vaysf_rendering_shortcode = !empty($GLOBALS['vaysf_rendering_insurance_shortcode']);

if (!$vaysf_rendering_shortcode) {
    get_header();
}

$token = isset($_GET['token']) ? sanitize_text_field(wp_unslash($_GET['token'])) : '';

// In State B, look up the token to decide which sub-state to render. We never
// expose the token, church identity, or file path beyond what the holder of a
// valid token already controls.
$token_valid = false;
$token_expired = false;
if (!empty($token)) {
    global $wpdb;
    $table_churches = vaysf_get_table_name('churches');
    $church = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT insurance_token_expiry FROM $table_churches WHERE insurance_token = %s",
            $token
        ),
        ARRAY_A
    );

    if ($church) {
        if (!empty($church['insurance_token_expiry'])
            && strtotime($church['insurance_token_expiry']) >= current_time('timestamp')) {
            $token_valid = true;
        } else {
            $token_expired = true;
        }
    } else {
        // Unknown token behaves like an expired one.
        $token_expired = true;
    }
}

$request_link_url = esc_url_raw(rest_url('vaysf/v1/insurance/request-link'));
$upload_url = esc_url_raw(rest_url('vaysf/v1/insurance/upload'));
$max_bytes = vaysf_get_insurance_max_bytes();
?>

<div class="vaysf-insurance-container" style="max-width: 640px; margin: 40px auto; padding: 20px; background: #fff; box-shadow: 0 0 10px rgba(0,0,0,0.1);">
    <h1><?php echo esc_html__('Proof of Insurance Upload', 'vaysf'); ?></h1>

    <div id="vaysf-insurance-message"></div>

    <?php if (empty($token)) : ?>
        <!-- State A: request an upload link -->
        <p><?php echo esc_html__('Enter your church code and the email on file for your church representative. If they match, we will email a secure upload link.', 'vaysf'); ?></p>
        <form id="vaysf-request-form">
            <p>
                <label for="vaysf-church-code"><strong><?php echo esc_html__('Church Code', 'vaysf'); ?></strong></label><br>
                <input type="text" id="vaysf-church-code" name="church_code" maxlength="3" required
                       style="width: 100%; padding: 8px; box-sizing: border-box;">
            </p>
            <p>
                <label for="vaysf-email"><strong><?php echo esc_html__('Church Representative Email', 'vaysf'); ?></strong></label><br>
                <input type="email" id="vaysf-email" name="email" required
                       style="width: 100%; padding: 8px; box-sizing: border-box;">
            </p>
            <p>
                <button type="submit" style="padding: 12px 24px; background-color: #2271b1; color: white; border: none; border-radius: 5px; font-weight: bold; cursor: pointer;">
                    <?php echo esc_html__('Send Upload Link', 'vaysf'); ?>
                </button>
            </p>
        </form>

    <?php elseif ($token_valid) : ?>
        <!-- State B (valid): upload a PDF -->
        <p><?php echo esc_html__('Please choose your proof-of-insurance document (PDF, max 10 MB) and upload it.', 'vaysf'); ?></p>
        <form id="vaysf-upload-form">
            <input type="hidden" id="vaysf-token" value="<?php echo esc_attr($token); ?>">
            <p>
                <input type="file" id="vaysf-file" name="file" accept="application/pdf,.pdf" required>
            </p>
            <p>
                <button type="submit" style="padding: 12px 24px; background-color: #00a32a; color: white; border: none; border-radius: 5px; font-weight: bold; cursor: pointer;">
                    <?php echo esc_html__('Upload PDF', 'vaysf'); ?>
                </button>
            </p>
        </form>

    <?php else : ?>
        <!-- State B (expired/invalid): offer to request a new link -->
        <div class="notice notice-error" style="background: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin-bottom: 20px;">
            <p><?php echo esc_html__('This link has expired.', 'vaysf'); ?></p>
        </div>
        <p>
            <a href="<?php echo esc_url(site_url('insurance-upload')); ?>"
               style="display: inline-block; padding: 12px 24px; background-color: #2271b1; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">
                <?php echo esc_html__('Request a New Link', 'vaysf'); ?>
            </a>
        </p>
    <?php endif; ?>

    <div style="margin-top: 40px; text-align: center;">
        <img src="<?php echo esc_url(plugins_url('assets/logo.png', dirname(__FILE__))); ?>" alt="VAY Sports Ministry Logo" style="max-width: 200px;">
    </div>
</div>

<script>
(function () {
    var requestUrl = <?php echo wp_json_encode($request_link_url); ?>;
    var uploadUrl = <?php echo wp_json_encode($upload_url); ?>;
    var uploadPageUrl = window.location.href.split('?')[0];
    var maxBytes = <?php echo (int) $max_bytes; ?>;
    var box = document.getElementById('vaysf-insurance-message');

    function showMessage(type, text) {
        var color = (type === 'success') ? '#00a32a' : '#d63638';
        var bg = (type === 'success') ? '#e6f4ea' : '#f8d7da';
        box.innerHTML = '<div style="background:' + bg + ';padding:15px;border-left:4px solid ' + color + ';margin-bottom:20px;"><p style="margin:0;">' + text + '</p></div>';
    }

    var requestForm = document.getElementById('vaysf-request-form');
    if (requestForm) {
        requestForm.addEventListener('submit', function (e) {
            e.preventDefault();
            var code = document.getElementById('vaysf-church-code').value.trim();
            var email = document.getElementById('vaysf-email').value.trim();
            fetch(requestUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ church_code: code, email: email, upload_page_url: uploadPageUrl })
            }).then(function (r) {
                return r.json();
            }).then(function (data) {
                showMessage('success', (data && data.message) ? data.message : 'If we found your church, an email is on its way.');
                requestForm.reset();
            }).catch(function () {
                showMessage('error', 'Something went wrong. Please try again.');
            });
        });
    }

    var uploadForm = document.getElementById('vaysf-upload-form');
    if (uploadForm) {
        uploadForm.addEventListener('submit', function (e) {
            e.preventDefault();
            var fileInput = document.getElementById('vaysf-file');
            var token = document.getElementById('vaysf-token').value;
            if (!fileInput.files.length) {
                showMessage('error', 'Please choose a PDF file.');
                return;
            }
            var file = fileInput.files[0];
            if (file.size > maxBytes) {
                showMessage('error', 'The file must be a PDF no larger than 10 MB.');
                return;
            }
            var fd = new FormData();
            fd.append('token', token);
            fd.append('file', file);
            fetch(uploadUrl, { method: 'POST', body: fd }).then(function (r) {
                return r.json().then(function (data) {
                    return { ok: r.ok, data: data };
                });
            }).then(function (res) {
                if (res.ok && res.data && res.data.success) {
                    showMessage('success', res.data.message || 'Thank you. Your proof of insurance has been received.');
                    uploadForm.style.display = 'none';
                } else {
                    showMessage('error', (res.data && res.data.message) ? res.data.message : 'Upload failed. Please try again.');
                }
            }).catch(function () {
                showMessage('error', 'Something went wrong. Please try again.');
            });
        });
    }
})();
</script>

<?php
if (!$vaysf_rendering_shortcode) {
    get_footer();
}

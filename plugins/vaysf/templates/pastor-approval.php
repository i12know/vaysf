<?php
// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

// Get header
get_header();
?>

<div class="vaysf-approval-container" style="max-width: 800px; margin: 40px auto; padding: 20px; background: #fff; box-shadow: 0 0 10px rgba(0,0,0,0.1);">
    <h1>Sports Fest Pastor Approval</h1>
    
    <?php
    $token = isset($_GET['token']) ? sanitize_text_field($_GET['token']) : '';
    $decision = isset($_GET['decision']) ? sanitize_text_field($_GET['decision']) : '';

    if (empty($token) || empty($decision)) {
        echo '<div class="notice notice-error" style="background: #f8d7da; padding: 15px; border-left: 4px solid #dc3545; margin-bottom: 20px;">';
        echo '<p>Invalid approval link. Please check your email and try again.</p>';
        echo '</div>';
    } else {
        // Call the REST API endpoint
        $response = wp_remote_get(
            rest_url('vaysf/v1/approvals/process-token') . 
            '?token=' . urlencode($token) . 
            '&decision=' . urlencode($decision),
            array(
                'method' => 'GET',
                'timeout' => 45,
                'redirection' => 5,
                'httpversion' => '1.0',
                'blocking' => true
            )
        );
        
        if (is_wp_error($response)) {
            echo '<div class="notice notice-error" style="background: #f8d7da; padding: 15px; border-left: 4px solid #dc3545; margin-bottom: 20px;">';
            echo '<p>Error processing approval: ' . esc_html($response->get_error_message()) . '</p>';
            echo '</div>';
        } else {
            $body = json_decode(wp_remote_retrieve_body($response), true);
            
            if (isset($body['success']) && $body['success']) {
                $status = $body['status'] === 'approved';
                $color = $status ? '#28a745' : '#ffc107';
                $icon = $status ? '✓' : '⚠';
                
                echo '<div class="notice" style="background: ' . $color . '1a; padding: 20px; border-left: 4px solid ' . $color . '; margin-bottom: 20px;">';
                echo '<h2 style="margin-top: 0;"><span style="color: ' . $color . '; margin-right: 10px;">' . $icon . '</span>' . esc_html($body['message']) . '</h2>';
                echo '<p>Thank you for your response. This window can now be closed.</p>';
                echo '</div>';
            } else {
                echo '<div class="notice notice-error" style="background: #f8d7da; padding: 15px; border-left: 4px solid #dc3545; margin-bottom: 20px;">';
                echo '<p>Error: ' . (isset($body['message']) ? esc_html($body['message']) : 'An unknown error occurred.') . '</p>';
                echo '</div>';
            }
        }
    }
    ?>
    
    <p>If you have any questions about this approval process, please contact the VAY Sports Ministry team.</p>
    
    <div style="margin-top: 40px; text-align: center;">
        <img src="<?php echo esc_url(plugins_url('assets/logo.png', dirname(__FILE__))); ?>" alt="VAY Sports Ministry Logo" style="max-width: 200px;">
    </div>
</div>

<?php
// Get footer
get_footer();
?>
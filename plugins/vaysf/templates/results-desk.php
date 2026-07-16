<?php
/**
 * Results Desk template (Issue #208).
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

if (!empty($GLOBALS['vaysf_rendering_results_desk_shortcode'])) {
    echo vaysf_render_results_desk($GLOBALS['vaysf_results_desk_shortcode_atts'] ?? array());
    return;
}

get_header();
echo vaysf_render_results_desk();
get_footer();

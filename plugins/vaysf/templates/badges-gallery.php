<?php
/**
 * Badge gallery public template (Issues #289/#290).
 */

if (!defined('ABSPATH')) {
    exit;
}

get_header();
echo do_shortcode('[vaysf_badges]');
get_footer();

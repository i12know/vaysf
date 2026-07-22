<?php
/**
 * File: includes/results-desk.php
 * Description: Manager/admin Results Desk loader for event-day operations (Issue #208, refactored in #333)
 * Version: 1.0.0
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

$vaysf_results_desk_dir = __DIR__ . '/results-desk';

require_once $vaysf_results_desk_dir . '/access.php';
require_once $vaysf_results_desk_dir . '/pool-progress.php';
require_once $vaysf_results_desk_dir . '/qf-seeding.php';
require_once $vaysf_results_desk_dir . '/playoff-preview.php';
require_once $vaysf_results_desk_dir . '/render.php';
require_once $vaysf_results_desk_dir . '/actions.php';

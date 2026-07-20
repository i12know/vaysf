<?php
/**
 * Coordinator score entry dashboard (Issues #239, #241, and #244).
 *
 * Provides the coordinator-facing dashboard plus supported sport score forms.
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

$vaysf_rendering_shortcode = !empty($GLOBALS['vaysf_rendering_coordinator_score_entry_shortcode']);

$view = isset($_GET['view']) ? sanitize_key(wp_unslash($_GET['view'])) : 'needs';
$page_action = isset($_GET['action']) ? sanitize_key(wp_unslash($_GET['action'])) : '';
$schedule_id = isset($_GET['schedule_id']) ? absint($_GET['schedule_id']) : 0;
$game_key = isset($_GET['game_key']) ? sanitize_text_field(wp_unslash($_GET['game_key'])) : '';
$requested_event = isset($_GET['event']) ? sanitize_text_field(wp_unslash($_GET['event'])) : '';
$notice_message = '';
$notice_is_error = false;
$tabs = array(
    'needs' => esc_html__('Needs Results', 'vaysf'),
    'submitted' => esc_html__('Submitted Today', 'vaysf'),
    'assigned' => esc_html__('Assigned Games', 'vaysf'),
);
if (!isset($tabs[$view])) {
    $view = 'needs';
}

if (!$schedule_id && $game_key !== '') {
    $game_key_schedule = vaysf_resolve_schedule_row_by_game_key($game_key);
    if ($game_key_schedule && !empty($game_key_schedule['schedule_id'])) {
        $schedule_id = absint($game_key_schedule['schedule_id']);
        if ($requested_event === '' && !empty($game_key_schedule['event'])) {
            $requested_event = sanitize_text_field($game_key_schedule['event']);
        }
    }
}

if (
    is_user_logged_in()
    && current_user_can('sf2025_submit_results')
    && isset($_POST['vaysf_score_entry_action'])
    && sanitize_key(wp_unslash($_POST['vaysf_score_entry_action'])) === 'submit_simple_score'
) {
    $posted_schedule_id = isset($_POST['schedule_id']) ? absint($_POST['schedule_id']) : 0;
    $posted_event = isset($_POST['event']) ? sanitize_text_field(wp_unslash($_POST['event'])) : '';
    $posted_view = isset($_POST['view']) ? sanitize_key(wp_unslash($_POST['view'])) : 'assigned';
    $posted_view = isset($tabs[$posted_view]) ? $posted_view : 'assigned';
    $score_form_type = isset($_POST['score_form_type']) ? sanitize_key(wp_unslash($_POST['score_form_type'])) : 'simple';
    $team_a_score_raw = isset($_POST['team_a_score']) ? trim((string) wp_unslash($_POST['team_a_score'])) : '';
    $team_b_score_raw = isset($_POST['team_b_score']) ? trim((string) wp_unslash($_POST['team_b_score'])) : '';
    $team_c_score_raw = isset($_POST['team_c_score']) ? trim((string) wp_unslash($_POST['team_c_score'])) : '';
    $volleyball_set_1_team_a_raw = isset($_POST['volleyball_set_1_team_a_score']) ? trim((string) wp_unslash($_POST['volleyball_set_1_team_a_score'])) : '';
    $volleyball_set_1_team_b_raw = isset($_POST['volleyball_set_1_team_b_score']) ? trim((string) wp_unslash($_POST['volleyball_set_1_team_b_score'])) : '';
    $volleyball_set_2_team_a_raw = isset($_POST['volleyball_set_2_team_a_score']) ? trim((string) wp_unslash($_POST['volleyball_set_2_team_a_score'])) : '';
    $volleyball_set_2_team_b_raw = isset($_POST['volleyball_set_2_team_b_score']) ? trim((string) wp_unslash($_POST['volleyball_set_2_team_b_score'])) : '';
    $volleyball_tiebreaker_team_a_raw = isset($_POST['volleyball_tiebreaker_team_a_score']) ? trim((string) wp_unslash($_POST['volleyball_tiebreaker_team_a_score'])) : '';
    $volleyball_tiebreaker_team_b_raw = isset($_POST['volleyball_tiebreaker_team_b_score']) ? trim((string) wp_unslash($_POST['volleyball_tiebreaker_team_b_score'])) : '';
    $volleyball_require_tiebreaker = !empty($_POST['volleyball_require_tiebreaker']);
    $placement_first_church = isset($_POST['placement_first_church']) ? sanitize_text_field(wp_unslash($_POST['placement_first_church'])) : '';
    $placement_second_church = isset($_POST['placement_second_church']) ? sanitize_text_field(wp_unslash($_POST['placement_second_church'])) : '';
    $placement_third_church = isset($_POST['placement_third_church']) ? sanitize_text_field(wp_unslash($_POST['placement_third_church'])) : '';

    if (
        empty($_POST['_wpnonce'])
        || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'])), 'vaysf_submit_simple_score_' . $posted_schedule_id)
    ) {
        $notice_message = __('Score submission expired. Please try again.', 'vaysf');
        $notice_is_error = true;
    } elseif ($score_form_type === 'volleyball') {
        $required_volleyball_scores = array(
            $volleyball_set_1_team_a_raw,
            $volleyball_set_1_team_b_raw,
            $volleyball_set_2_team_a_raw,
            $volleyball_set_2_team_b_raw,
        );
        $required_scores_valid = true;
        foreach ($required_volleyball_scores as $score_raw) {
            if ($score_raw === '' || !ctype_digit($score_raw)) {
                $required_scores_valid = false;
                break;
            }
        }
        $has_tiebreaker_score = $volleyball_tiebreaker_team_a_raw !== '' || $volleyball_tiebreaker_team_b_raw !== '';
        $tiebreaker_scores_valid = !$has_tiebreaker_score
            || (
                $volleyball_tiebreaker_team_a_raw !== ''
                && $volleyball_tiebreaker_team_b_raw !== ''
                && ctype_digit($volleyball_tiebreaker_team_a_raw)
                && ctype_digit($volleyball_tiebreaker_team_b_raw)
            );

        if (!$required_scores_valid || !$tiebreaker_scores_valid) {
            $notice_message = __('Scores must be whole numbers zero or greater. Enter both tiebreaker scores or leave both blank.', 'vaysf');
            $notice_is_error = true;
        } else {
            $submit_result = vaysf_submit_volleyball_score_result(
                get_current_user_id(),
                $posted_schedule_id,
                (int) $volleyball_set_1_team_a_raw,
                (int) $volleyball_set_1_team_b_raw,
                (int) $volleyball_set_2_team_a_raw,
                (int) $volleyball_set_2_team_b_raw,
                $has_tiebreaker_score ? (int) $volleyball_tiebreaker_team_a_raw : null,
                $has_tiebreaker_score ? (int) $volleyball_tiebreaker_team_b_raw : null,
                !empty($_POST['certify_score']),
                isset($_POST['notes']) ? wp_unslash($_POST['notes']) : '',
                $volleyball_require_tiebreaker
            );
        }
    } elseif ($score_form_type === 'placement') {
        $submit_result = vaysf_submit_placement_result(
            get_current_user_id(),
            $posted_schedule_id,
            $placement_first_church,
            $placement_second_church,
            $placement_third_church,
            !empty($_POST['certify_score']),
            isset($_POST['notes']) ? wp_unslash($_POST['notes']) : ''
        );
    } else {
        $score_values_valid = false;
        if ($score_form_type === 'three_team') {
            $score_values_valid = $team_a_score_raw !== ''
                && $team_b_score_raw !== ''
                && $team_c_score_raw !== ''
                && preg_match('/^-?\d+$/', $team_a_score_raw)
                && preg_match('/^-?\d+$/', $team_b_score_raw)
                && preg_match('/^-?\d+$/', $team_c_score_raw);
        } else {
            $score_values_valid = $team_a_score_raw !== ''
                && $team_b_score_raw !== ''
                && ctype_digit($team_a_score_raw)
                && ctype_digit($team_b_score_raw);
        }

        if (!$score_values_valid) {
            $notice_message = $score_form_type === 'three_team'
                ? __('Scores must be whole numbers. Negative scores are allowed for Bible Challenge.', 'vaysf')
                : __('Scores must be whole numbers zero or greater.', 'vaysf');
            $notice_is_error = true;
        } elseif ($score_form_type === 'three_team') {
            $submit_result = vaysf_submit_three_team_score_result(
                get_current_user_id(),
                $posted_schedule_id,
                (int) $team_a_score_raw,
                (int) $team_b_score_raw,
                (int) $team_c_score_raw,
                !empty($_POST['certify_score']),
                isset($_POST['notes']) ? wp_unslash($_POST['notes']) : ''
            );
        } else {
            $submit_result = vaysf_submit_simple_score_result(
                get_current_user_id(),
                $posted_schedule_id,
                (int) $team_a_score_raw,
                (int) $team_b_score_raw,
                !empty($_POST['certify_score']),
                isset($_POST['notes']) ? wp_unslash($_POST['notes']) : ''
            );
        }
    }

    if (!$notice_is_error) {
        if (is_wp_error($submit_result)) {
            $notice_message = $submit_result->get_error_message();
            $notice_is_error = true;
        } else {
            $redirect_args = array('score_submitted' => '1');
            if (
                !empty($_FILES['scoresheet_file'])
                && isset($_FILES['scoresheet_file']['error'])
                && (int) $_FILES['scoresheet_file']['error'] !== UPLOAD_ERR_NO_FILE
            ) {
                $stored_scan = vaysf_store_result_scoresheet_file(
                    isset($submit_result['result_id']) ? absint($submit_result['result_id']) : 0,
                    isset($submit_result['revision_id']) ? absint($submit_result['revision_id']) : 0,
                    get_current_user_id(),
                    $_FILES['scoresheet_file']
                );
                $redirect_args['scan_upload'] = is_wp_error($stored_scan) ? 'failed' : 'uploaded';
            }

            wp_safe_redirect(
                add_query_arg(
                    $redirect_args,
                    vaysf_get_coordinator_score_entry_url('submitted', $posted_event)
                )
            );
            exit;
        }
    }

    $page_action = 'score';
    $schedule_id = $posted_schedule_id;
    $view = $posted_view;
    $requested_event = $posted_event;
}

if (isset($_GET['score_submitted']) && $_GET['score_submitted'] === '1') {
    $notice_message = __('Score submitted and revision saved.', 'vaysf');
    if (isset($_GET['scan_upload']) && $_GET['scan_upload'] === 'uploaded') {
        $notice_message = __('Score submitted and score sheet scan saved.', 'vaysf');
    } elseif (isset($_GET['scan_upload']) && $_GET['scan_upload'] === 'failed') {
        $notice_message = __('Score submitted, but the score sheet scan could not be saved. You can edit the game and upload it later.', 'vaysf');
    }
}

$container_style = 'max-width: 960px; margin: 32px auto; padding: 20px;';
$score_entry_return_url = isset($_SERVER['REQUEST_URI'])
    ? esc_url_raw(home_url(wp_unslash($_SERVER['REQUEST_URI'])))
    : vaysf_get_coordinator_score_entry_url('assigned');

if (!$vaysf_rendering_shortcode) {
    get_header();
}
?>

<div class="vaysf-score-entry-dashboard" style="<?php echo esc_attr($container_style); ?>">
    <style>
        .vaysf-score-entry-dashboard * {
            box-sizing: border-box;
        }
        .vaysf-score-entry-dashboard h1 {
            margin: 0 0 8px;
            font-size: 2rem;
            line-height: 1.2;
        }
        .vaysf-score-entry-subtitle {
            margin: 0 0 24px;
            color: #50575e;
        }
        .vaysf-score-entry-notice {
            background: #fff8e5;
            border-left: 4px solid #dba617;
            margin: 20px 0;
            padding: 14px 16px;
        }
        .vaysf-score-entry-error {
            background: #fcf0f1;
            border-left-color: #d63638;
        }
        .vaysf-score-entry-tabs {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 0 0 20px;
        }
        .vaysf-score-entry-tabs a {
            border: 1px solid #c3c4c7;
            color: #1d2327;
            display: inline-block;
            padding: 10px 14px;
            text-decoration: none;
        }
        .vaysf-score-entry-tabs a.is-active {
            background: #1d4ed8;
            border-color: #1d4ed8;
            color: #fff;
        }
        .vaysf-score-entry-event-list {
            margin: 0 0 20px;
            color: #50575e;
            font-size: 0.95rem;
        }
        .vaysf-score-entry-pool-section {
            margin: 0 0 24px;
        }
        .vaysf-score-entry-pool-section h2 {
            font-size: 1.35rem;
            margin: 0 0 4px;
        }
        .vaysf-score-entry-pool-section p {
            color: #50575e;
            margin: 0 0 10px;
        }
        .vaysf-score-entry-pool-section .vaysf-results-desk-table {
            background: #fff;
            border: 1px solid #dcdcde;
            border-collapse: collapse;
            width: 100%;
        }
        .vaysf-score-entry-pool-section .vaysf-results-desk-table th,
        .vaysf-score-entry-pool-section .vaysf-results-desk-table td {
            border-bottom: 1px solid #dcdcde;
            padding: 10px;
            text-align: left;
            vertical-align: top;
        }
        .vaysf-score-entry-pool-section .vaysf-results-desk-table th {
            background: #f6f7f7;
        }
        .vaysf-score-entry-pool-section .vaysf-results-desk-help {
            align-items: center;
            background: #dcdcde;
            border-radius: 50%;
            color: #1d2327;
            cursor: help;
            display: inline-flex;
            font-size: 12px;
            font-weight: 700;
            height: 18px;
            justify-content: center;
            width: 18px;
        }
        .vaysf-score-entry-pool-section .vaysf-results-desk-muted {
            color: #646970;
            font-size: .9em;
        }
        .vaysf-score-entry-pool-section .vaysf-results-desk-warning {
            background: #fff8e5;
            border: 1px solid #dba617;
            border-radius: 4px;
            color: #674e00;
            cursor: help;
            display: inline-block;
            padding: 2px 6px;
        }
        .vaysf-score-entry-pool-section .vaysf-results-desk-pill {
            background: #ecf7ed;
            border: 1px solid #c3d9c8;
            border-radius: 4px;
            color: #1d5727;
            cursor: help;
            display: inline-block;
            padding: 2px 6px;
        }
        .vaysf-score-entry-pool-section .vaysf-results-desk-progress {
            background: #dcdcde;
            border-radius: 999px;
            cursor: help;
            height: 10px;
            margin: 0 0 6px;
            max-width: 100%;
            overflow: hidden;
            width: 160px;
        }
        .vaysf-score-entry-pool-section .vaysf-results-desk-progress span {
            background: #46b450;
            display: block;
            height: 100%;
        }
        .vaysf-score-entry-pool-section .vaysf-results-desk-rankings {
            margin: 0;
            padding-left: 26px;
        }
        .vaysf-score-entry-pool-section .vaysf-results-desk-rankings li {
            margin: 0 0 6px;
        }
        .vaysf-score-entry-pool-section .vaysf-results-desk-rankings li:last-child {
            margin-bottom: 0;
        }
        .vaysf-score-entry-filter {
            align-items: end;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin: 0 0 18px;
        }
        .vaysf-score-entry-filter label {
            display: block;
            font-size: 0.86rem;
            font-weight: 600;
            margin-bottom: 4px;
        }
        .vaysf-score-entry-filter select {
            min-width: 260px;
            padding: 8px;
        }
        .vaysf-score-entry-filter button {
            padding: 9px 14px;
        }
        .vaysf-score-entry-card {
            background: #fff;
            border: 1px solid #dcdcde;
            margin: 0 0 12px;
            padding: 16px;
        }
        .vaysf-score-entry-card-header {
            align-items: start;
            display: flex;
            gap: 12px;
            justify-content: space-between;
            margin-bottom: 10px;
        }
        .vaysf-score-entry-game-key {
            font-weight: 700;
            letter-spacing: 0;
        }
        .vaysf-score-entry-meta {
            color: #50575e;
            font-size: 0.92rem;
            margin-top: 2px;
        }
        .vaysf-score-entry-teams {
            font-size: 1.05rem;
            font-weight: 600;
            margin: 12px 0;
        }
        .vaysf-score-entry-status {
            background: #f0f0f1;
            color: #1d2327;
            display: inline-block;
            font-size: 0.84rem;
            padding: 4px 8px;
        }
        .vaysf-score-entry-button {
            background: #f0f0f1;
            border: 1px solid #c3c4c7;
            color: #646970;
            cursor: not-allowed;
            display: inline-block;
            padding: 9px 12px;
        }
        .vaysf-score-entry-action {
            background: #1d4ed8;
            border-color: #1d4ed8;
            color: #fff;
            cursor: pointer;
            text-decoration: none;
        }
        .vaysf-score-entry-form {
            background: #fff;
            border: 1px solid #dcdcde;
            margin-top: 24px;
            padding: 18px;
        }
        .vaysf-score-entry-score-grid {
            display: grid;
            gap: 14px;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            margin: 18px 0;
        }
        .vaysf-score-entry-score-grid-three {
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }
        .vaysf-score-entry-score-grid label,
        .vaysf-score-entry-form label {
            display: block;
            font-weight: 600;
            margin-bottom: 6px;
        }
        .vaysf-score-entry-score-grid input,
        .vaysf-score-entry-form textarea {
            border: 1px solid #8c8f94;
            padding: 9px;
            width: 100%;
        }
        .vaysf-score-entry-set-table {
            border-collapse: collapse;
            margin: 18px 0;
            width: 100%;
        }
        .vaysf-score-entry-set-table th,
        .vaysf-score-entry-set-table td {
            border: 1px solid #dcdcde;
            padding: 8px;
            text-align: left;
        }
        .vaysf-score-entry-set-table th {
            background: #f6f7f7;
            font-weight: 700;
        }
        .vaysf-score-entry-set-table input {
            border: 1px solid #8c8f94;
            max-width: 110px;
            padding: 8px;
            width: 100%;
        }
        .vaysf-score-entry-help {
            color: #646970;
            font-size: 0.9rem;
            margin: 8px 0 0;
        }
        .vaysf-score-entry-file-list {
            background: #f6f7f7;
            border: 1px solid #dcdcde;
            margin: 14px 0;
            padding: 12px;
        }
        .vaysf-score-entry-file-list ul {
            margin: 8px 0 0 18px;
        }
        .vaysf-score-entry-form textarea {
            min-height: 96px;
        }
        .vaysf-score-entry-checkbox {
            align-items: start;
            display: flex;
            gap: 8px;
            margin: 14px 0;
        }
        .vaysf-score-entry-checkbox input {
            margin-top: 3px;
        }
        .vaysf-score-entry-form-actions {
            align-items: center;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 16px;
        }
        .vaysf-score-entry-secondary-link {
            color: #1d4ed8;
            text-decoration: none;
        }
        @media (max-width: 640px) {
            .vaysf-score-entry-dashboard {
                margin: 16px auto !important;
                padding: 14px !important;
            }
            .vaysf-score-entry-pool-section .vaysf-results-desk-table {
                display: block;
                overflow-x: auto;
            }
            .vaysf-score-entry-card-header {
                display: block;
            }
            .vaysf-score-entry-button {
                margin-top: 12px;
                width: 100%;
            }
            .vaysf-score-entry-score-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>

    <h1><?php esc_html_e('Coordinator Score Entry', 'vaysf'); ?></h1>
    <p class="vaysf-score-entry-subtitle">
        <?php esc_html_e('Assigned games from the published Sports Fest schedule.', 'vaysf'); ?>
    </p>

    <?php if ($notice_message !== '') : ?>
        <div class="vaysf-score-entry-notice <?php echo $notice_is_error ? 'vaysf-score-entry-error' : ''; ?>">
            <p><?php echo esc_html($notice_message); ?></p>
        </div>
    <?php endif; ?>

    <?php if (!is_user_logged_in()) : ?>
        <div class="vaysf-score-entry-notice">
            <p><?php esc_html_e('Please log in with your coordinator account to view assigned games.', 'vaysf'); ?></p>
            <p>
                <a href="<?php echo esc_url(wp_login_url($score_entry_return_url)); ?>">
                    <?php esc_html_e('Log in', 'vaysf'); ?>
                </a>
            </p>
        </div>
    <?php elseif (!current_user_can('sf2025_submit_results')) : ?>
        <div class="vaysf-score-entry-notice vaysf-score-entry-error">
            <p><?php esc_html_e('Your account is not authorized for Sports Fest score entry.', 'vaysf'); ?></p>
        </div>
    <?php else : ?>
        <?php
        $user_id = get_current_user_id();
        $has_all_event_access = vaysf_user_has_all_score_entry_events($user_id);
        $authorized_events = vaysf_get_user_score_entry_events($user_id);
        $current_version = vaysf_get_current_published_schedule_version();
        $selected_event = in_array($requested_event, $authorized_events, true) ? $requested_event : '';
        $row_sets = array(
            'needs' => vaysf_get_coordinator_score_dashboard_rows($user_id, 'needs', $selected_event),
            'submitted' => vaysf_get_coordinator_score_dashboard_rows($user_id, 'submitted', $selected_event),
            'assigned' => vaysf_get_coordinator_score_dashboard_rows($user_id, 'assigned', $selected_event),
        );
        $pool_progress_rows = ($page_action === 'score' && $schedule_id)
            ? array()
            : vaysf_get_coordinator_score_pool_progress_rows($user_id, $selected_event);
        $rows = $row_sets[$view];
        ?>

        <?php if (!$authorized_events) : ?>
            <div class="vaysf-score-entry-notice">
                <p><?php esc_html_e('No schedule events have been assigned to your coordinator account yet.', 'vaysf'); ?></p>
            </div>
        <?php elseif ($current_version === null) : ?>
            <div class="vaysf-score-entry-notice">
                <p><?php esc_html_e('No published Sports Fest schedule is available yet.', 'vaysf'); ?></p>
            </div>
        <?php else : ?>
            <?php if ($page_action === 'score' && $schedule_id) : ?>
                <?php
                $score_schedule = vaysf_resolve_schedule_row($schedule_id);
                $score_result = vaysf_get_result_for_schedule($schedule_id);
                $score_files = $score_result ? vaysf_get_result_files_for_result($score_result['result_id']) : array();
                $score_payload = array();
                if ($score_result && !empty($score_result['score_json'])) {
                    $decoded_score = json_decode($score_result['score_json'], true);
                    if (is_array($decoded_score)) {
                        $score_payload = $decoded_score;
                    }
                }
                $can_score = $score_schedule
                    && vaysf_user_can_submit_schedule_result($user_id, $score_schedule)
                    && vaysf_is_supported_score_schedule($score_schedule);
                $back_url = vaysf_get_coordinator_score_entry_url($view, $selected_event);
                ?>

                <?php if (!$can_score) : ?>
                    <div class="vaysf-score-entry-notice vaysf-score-entry-error">
                        <p><?php esc_html_e('This game is not available for score entry from your account.', 'vaysf'); ?></p>
                    </div>
                    <p><a class="vaysf-score-entry-secondary-link" href="<?php echo esc_url($back_url); ?>"><?php esc_html_e('Back to dashboard', 'vaysf'); ?></a></p>
                <?php else : ?>
                    <?php
                    $team_a_label = $score_schedule['team_a_label'] ?: $score_schedule['team_a_key'];
                    $team_b_label = $score_schedule['team_b_label'] ?: $score_schedule['team_b_key'];
                    $team_c_label = $score_schedule['team_c_label'] ?: $score_schedule['team_c_key'];
                    $team_a_value = isset($score_payload['team_a_score']) ? (string) intval($score_payload['team_a_score']) : '';
                    $team_b_value = isset($score_payload['team_b_score']) ? (string) intval($score_payload['team_b_score']) : '';
                    $team_c_value = isset($score_payload['team_c_score']) ? (string) intval($score_payload['team_c_score']) : '';
                    $score_form_type = 'simple';
                    if (vaysf_is_three_team_score_schedule($score_schedule)) {
                        $score_form_type = 'three_team';
                    } elseif (vaysf_is_volleyball_score_schedule($score_schedule)) {
                        $score_form_type = 'volleyball';
                    } elseif (vaysf_is_placement_score_schedule($score_schedule)) {
                        $score_form_type = 'placement';
                    }
                    $placement_churches = $score_form_type === 'placement'
                        ? vaysf_get_public_schedule_churches($score_schedule['schedule_version'] ?? null)
                        : array();
                    $placement_first_value = isset($score_payload['first_church_code']) ? (string) $score_payload['first_church_code'] : '';
                    $placement_second_value = isset($score_payload['second_church_code']) ? (string) $score_payload['second_church_code'] : '';
                    $placement_third_value = isset($score_payload['third_church_code']) ? (string) $score_payload['third_church_code'] : '';
                    $volleyball_set_values = array(
                        1 => array('team_a' => '', 'team_b' => ''),
                        2 => array('team_a' => '', 'team_b' => ''),
                        3 => array('team_a' => '', 'team_b' => ''),
                    );
                    if ($score_form_type === 'volleyball' && !empty($score_payload['sets']) && is_array($score_payload['sets'])) {
                        foreach ($score_payload['sets'] as $set_payload) {
                            if (!is_array($set_payload) || empty($set_payload['number'])) {
                                continue;
                            }
                            $set_number = absint($set_payload['number']);
                            if (!isset($volleyball_set_values[$set_number])) {
                                continue;
                            }
                            $volleyball_set_values[$set_number]['team_a'] = isset($set_payload['team_a_score']) ? (string) absint($set_payload['team_a_score']) : '';
                            $volleyball_set_values[$set_number]['team_b'] = isset($set_payload['team_b_score']) ? (string) absint($set_payload['team_b_score']) : '';
                        }
                    }
                    $volleyball_strict_default = $score_form_type === 'volleyball'
                        && !vaysf_volleyball_allows_split_match($score_schedule);
                    $volleyball_strict_checked = $volleyball_strict_default;
                    if ($score_form_type === 'volleyball' && array_key_exists('strict_match_winner_required', $score_payload)) {
                        $volleyball_strict_checked = !empty($score_payload['strict_match_winner_required']);
                    }
                    $score_schedule_time = vaysf_format_schedule_display_time($score_schedule['scheduled_time'] ?? '', $score_schedule['scheduled_slot'] ?? '', 'D M j, g:i A');
                    if ($score_schedule_time === __('TBD', 'vaysf')) {
                        $score_schedule_time = esc_html__('Time TBD', 'vaysf');
                    }
                    $score_location_parts = array_filter(array($score_schedule['scheduled_location'] ?? '', $score_schedule['resource_id'] ?? '', $score_schedule['scheduled_slot'] ?? ''));
                    $score_location_text = $score_location_parts ? implode(' / ', $score_location_parts) : esc_html__('Location TBD', 'vaysf');
                    ?>
                    <div class="vaysf-score-entry-form">
                        <h2><?php echo esc_html($score_schedule['game_key']); ?></h2>
                        <p class="vaysf-score-entry-meta"><?php echo esc_html($score_schedule['event']); ?></p>
                        <p class="vaysf-score-entry-teams"><?php echo esc_html($score_form_type === 'placement' ? __('All churches', 'vaysf') : vaysf_format_schedule_teams($score_schedule)); ?></p>
                        <p class="vaysf-score-entry-meta"><?php echo esc_html($score_schedule_time); ?></p>
                        <p class="vaysf-score-entry-meta"><?php echo esc_html($score_location_text); ?></p>

                        <form method="post" enctype="multipart/form-data" action="<?php echo esc_url(vaysf_get_simple_score_form_url($score_schedule, $view, $selected_event)); ?>">
                            <?php wp_nonce_field('vaysf_submit_simple_score_' . absint($score_schedule['schedule_id'])); ?>
                            <input type="hidden" name="vaysf_score_entry_action" value="submit_simple_score">
                            <input type="hidden" name="schedule_id" value="<?php echo esc_attr($score_schedule['schedule_id']); ?>">
                            <input type="hidden" name="view" value="<?php echo esc_attr($view); ?>">
                            <input type="hidden" name="event" value="<?php echo esc_attr($selected_event); ?>">
                            <input type="hidden" name="score_form_type" value="<?php echo esc_attr($score_form_type); ?>">

                            <?php if ($score_form_type === 'volleyball') : ?>
                                <table class="vaysf-score-entry-set-table">
                                    <thead>
                                        <tr>
                                            <th><?php esc_html_e('Set', 'vaysf'); ?></th>
                                            <th><?php echo esc_html($team_a_label); ?></th>
                                            <th><?php echo esc_html($team_b_label); ?></th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        <tr>
                                            <th scope="row"><?php esc_html_e('Set 1', 'vaysf'); ?></th>
                                            <td><input name="volleyball_set_1_team_a_score" type="number" min="0" step="1" inputmode="numeric" required value="<?php echo esc_attr($volleyball_set_values[1]['team_a']); ?>"></td>
                                            <td><input name="volleyball_set_1_team_b_score" type="number" min="0" step="1" inputmode="numeric" required value="<?php echo esc_attr($volleyball_set_values[1]['team_b']); ?>"></td>
                                        </tr>
                                        <tr>
                                            <th scope="row"><?php esc_html_e('Set 2', 'vaysf'); ?></th>
                                            <td><input name="volleyball_set_2_team_a_score" type="number" min="0" step="1" inputmode="numeric" required value="<?php echo esc_attr($volleyball_set_values[2]['team_a']); ?>"></td>
                                            <td><input name="volleyball_set_2_team_b_score" type="number" min="0" step="1" inputmode="numeric" required value="<?php echo esc_attr($volleyball_set_values[2]['team_b']); ?>"></td>
                                        </tr>
                                        <tr>
                                            <th scope="row"><?php esc_html_e('Tiebreaker', 'vaysf'); ?></th>
                                            <td><input name="volleyball_tiebreaker_team_a_score" type="number" min="0" step="1" inputmode="numeric" value="<?php echo esc_attr($volleyball_set_values[3]['team_a']); ?>"></td>
                                            <td><input name="volleyball_tiebreaker_team_b_score" type="number" min="0" step="1" inputmode="numeric" value="<?php echo esc_attr($volleyball_set_values[3]['team_b']); ?>"></td>
                                        </tr>
                                    </tbody>
                                </table>
                                <p class="vaysf-score-entry-help">
                                    <?php esc_html_e('Time-capped set scores such as 25-24 or 21-18 are allowed. Leave the tiebreaker blank to record a preliminary split match, or enter it when a deciding set is played.', 'vaysf'); ?>
                                </p>
                                <label class="vaysf-score-entry-checkbox">
                                    <input type="checkbox" name="volleyball_require_tiebreaker" value="1" <?php checked($volleyball_strict_checked); ?>>
                                    <span><?php esc_html_e('Strict rule: require a tiebreaker winner if the first two sets are split.', 'vaysf'); ?></span>
                                </label>
                                <p class="vaysf-score-entry-help">
                                    <?php esc_html_e('House rule note: preliminary/pool volleyball may end as a 1-1 split match. Use the strict checkbox for playoff-style matches or whenever the referee requires one winner.', 'vaysf'); ?>
                                </p>
                            <?php elseif ($score_form_type === 'placement') : ?>
                                <div class="vaysf-score-entry-score-grid vaysf-score-entry-score-grid-three">
                                    <div>
                                        <label for="placement-first"><?php esc_html_e('1st place church', 'vaysf'); ?></label>
                                        <select id="placement-first" name="placement_first_church" required>
                                            <option value=""><?php esc_html_e('Select a church', 'vaysf'); ?></option>
                                            <?php foreach ($placement_churches as $church_code) : ?>
                                                <option value="<?php echo esc_attr($church_code); ?>" <?php selected($placement_first_value, $church_code); ?>><?php echo esc_html($church_code); ?></option>
                                            <?php endforeach; ?>
                                        </select>
                                    </div>
                                    <div>
                                        <label for="placement-second"><?php esc_html_e('2nd place church', 'vaysf'); ?></label>
                                        <select id="placement-second" name="placement_second_church" required>
                                            <option value=""><?php esc_html_e('Select a church', 'vaysf'); ?></option>
                                            <?php foreach ($placement_churches as $church_code) : ?>
                                                <option value="<?php echo esc_attr($church_code); ?>" <?php selected($placement_second_value, $church_code); ?>><?php echo esc_html($church_code); ?></option>
                                            <?php endforeach; ?>
                                        </select>
                                    </div>
                                    <div>
                                        <label for="placement-third"><?php esc_html_e('3rd place church (optional)', 'vaysf'); ?></label>
                                        <select id="placement-third" name="placement_third_church">
                                            <option value=""><?php esc_html_e('Select a church', 'vaysf'); ?></option>
                                            <?php foreach ($placement_churches as $church_code) : ?>
                                                <option value="<?php echo esc_attr($church_code); ?>" <?php selected($placement_third_value, $church_code); ?>><?php echo esc_html($church_code); ?></option>
                                            <?php endforeach; ?>
                                        </select>
                                    </div>
                                </div>
                                <p class="vaysf-score-entry-help">
                                    <?php esc_html_e('This event has no fixed matchup — pick the top finishing churches from the full church list.', 'vaysf'); ?>
                                </p>
                            <?php else : ?>
                                <div class="vaysf-score-entry-score-grid <?php echo $score_form_type === 'three_team' ? 'vaysf-score-entry-score-grid-three' : ''; ?>">
                                    <div>
                                        <label for="team-a-score"><?php echo esc_html($team_a_label); ?></label>
                                        <input id="team-a-score" name="team_a_score" type="number"<?php echo $score_form_type === 'three_team' ? '' : ' min="0" inputmode="numeric"'; ?> step="1" required value="<?php echo esc_attr($team_a_value); ?>">
                                    </div>
                                    <div>
                                        <label for="team-b-score"><?php echo esc_html($team_b_label); ?></label>
                                        <input id="team-b-score" name="team_b_score" type="number"<?php echo $score_form_type === 'three_team' ? '' : ' min="0" inputmode="numeric"'; ?> step="1" required value="<?php echo esc_attr($team_b_value); ?>">
                                    </div>
                                    <?php if ($score_form_type === 'three_team') : ?>
                                        <div>
                                            <label for="team-c-score"><?php echo esc_html($team_c_label); ?></label>
                                            <input id="team-c-score" name="team_c_score" type="number" step="1" required value="<?php echo esc_attr($team_c_value); ?>">
                                        </div>
                                    <?php endif; ?>
                                </div>
                            <?php endif; ?>

                            <?php if ($score_files) : ?>
                                <div class="vaysf-score-entry-file-list">
                                    <strong><?php esc_html_e('Uploaded score sheet scans', 'vaysf'); ?></strong>
                                    <ul>
                                        <?php foreach ($score_files as $score_file) : ?>
                                            <li>
                                                <?php echo esc_html($score_file['original_filename']); ?>
                                                <small>
                                                    <?php
                                                    printf(
                                                        esc_html__('Revision %1$d, %2$s', 'vaysf'),
                                                        absint($score_file['revision_number']),
                                                        esc_html(size_format(absint($score_file['byte_size'])))
                                                    );
                                                    ?>
                                                </small>
                                                <a href="<?php echo esc_url(vaysf_get_result_file_view_url($score_file['file_id'])); ?>" target="_blank" rel="noopener noreferrer"><?php esc_html_e('View', 'vaysf'); ?></a>
                                                |
                                                <a href="<?php echo esc_url(vaysf_get_result_file_download_url($score_file['file_id'])); ?>"><?php esc_html_e('Download', 'vaysf'); ?></a>
                                            </li>
                                        <?php endforeach; ?>
                                    </ul>
                                </div>
                            <?php endif; ?>

                            <label for="vaysf-score-sheet-file"><?php esc_html_e('Score sheet scan', 'vaysf'); ?></label>
                            <input id="vaysf-score-sheet-file" name="scoresheet_file" type="file" accept="application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png">
                            <p class="vaysf-score-entry-help">
                                <?php esc_html_e('Optional. Upload a PDF, JPEG, or PNG score sheet scan up to 32 MB. If upload fails, the score will still be saved and the scan can be attached later.', 'vaysf'); ?>
                            </p>

                            <label for="vaysf-score-notes"><?php esc_html_e('Notes', 'vaysf'); ?></label>
                            <textarea id="vaysf-score-notes" name="notes"><?php echo esc_textarea($score_result['notes'] ?? ''); ?></textarea>

                            <label class="vaysf-score-entry-checkbox">
                                <input type="checkbox" name="certify_score" value="1" required>
                                <span><?php esc_html_e('I certify this score is complete and accurate.', 'vaysf'); ?></span>
                            </label>

                            <div class="vaysf-score-entry-form-actions">
                                <button type="submit" class="vaysf-score-entry-button vaysf-score-entry-action">
                                    <?php echo $score_result ? esc_html__('Save Score Correction', 'vaysf') : esc_html__('Submit Score', 'vaysf'); ?>
                                </button>
                                <a class="vaysf-score-entry-secondary-link" href="<?php echo esc_url($back_url); ?>">
                                    <?php esc_html_e('Back to dashboard', 'vaysf'); ?>
                                </a>
                            </div>
                        </form>
                    </div>
                <?php endif; ?>
            <?php else : ?>
            <form class="vaysf-score-entry-filter" method="get">
                <input type="hidden" name="view" value="<?php echo esc_attr($view); ?>">
                <div>
                    <label for="vaysf-score-entry-event"><?php esc_html_e('Event filter', 'vaysf'); ?></label>
                    <select id="vaysf-score-entry-event" name="event" onchange="this.form.submit()">
                        <option value="">
                            <?php echo esc_html($has_all_event_access ? __('All events', 'vaysf') : __('All assigned events', 'vaysf')); ?>
                        </option>
                        <?php foreach ($authorized_events as $event) : ?>
                            <option value="<?php echo esc_attr($event); ?>" <?php selected($selected_event, $event); ?>>
                                <?php echo esc_html($event); ?>
                            </option>
                        <?php endforeach; ?>
                    </select>
                </div>
                <noscript>
                    <button type="submit"><?php esc_html_e('Filter', 'vaysf'); ?></button>
                </noscript>
            </form>

            <div class="vaysf-score-entry-tabs" role="tablist" aria-label="<?php echo esc_attr__('Score entry views', 'vaysf'); ?>">
                <?php foreach ($tabs as $tab_key => $tab_label) : ?>
                    <a
                        href="<?php echo esc_url(vaysf_get_coordinator_score_entry_url($tab_key, $selected_event)); ?>"
                        class="<?php echo $view === $tab_key ? 'is-active' : ''; ?>"
                        role="tab"
                        aria-selected="<?php echo $view === $tab_key ? 'true' : 'false'; ?>"
                    >
                        <?php echo esc_html($tab_label); ?>
                        (<?php echo esc_html(count($row_sets[$tab_key])); ?>)
                    </a>
                <?php endforeach; ?>
            </div>

            <p class="vaysf-score-entry-event-list">
                <?php
                if ($selected_event !== '') {
                    printf(
                        esc_html__('Schedule version %1$d. Showing: %2$s', 'vaysf'),
                        absint($current_version),
                        esc_html($selected_event)
                    );
                } else {
                    printf(
                        $has_all_event_access
                            ? esc_html__('Schedule version %1$d. Showing all events: %2$s', 'vaysf')
                            : esc_html__('Schedule version %1$d. Showing all assigned events: %2$s', 'vaysf'),
                        absint($current_version),
                        esc_html(implode(', ', $authorized_events))
                    );
                }
                ?>
            </p>

            <section class="vaysf-score-entry-pool-section">
                <h2>
                    <?php esc_html_e('Pools Progress For Review', 'vaysf'); ?>
                    <?php if (function_exists('vaysf_render_results_desk_tooltip')) : ?>
                        <?php vaysf_render_results_desk_tooltip('?', __('This section summarizes pool/prelim progress and provisional ranking signals for your score-entry events. It does not confirm advancement automatically.', 'vaysf')); ?>
                    <?php endif; ?>
                </h2>
                <p><?php esc_html_e('Use this as a quick review aid while entering or checking pool scores.', 'vaysf'); ?></p>
                <?php if (!$pool_progress_rows) : ?>
                    <div class="vaysf-score-entry-notice">
                        <p><?php esc_html_e('No pool progress is available for these assigned events.', 'vaysf'); ?></p>
                    </div>
                <?php elseif (function_exists('vaysf_render_results_desk_pool_progress_row')) : ?>
                    <table class="vaysf-results-desk-table">
                        <thead>
                            <tr>
                                <th><?php esc_html_e('Pool', 'vaysf'); ?></th>
                                <th><?php esc_html_e('Progress', 'vaysf'); ?></th>
                                <th><?php esc_html_e('Provisional Rankings', 'vaysf'); ?></th>
                                <th><?php esc_html_e('Review Status', 'vaysf'); ?></th>
                                <th><?php esc_html_e('Last Updated', 'vaysf'); ?></th>
                            </tr>
                        </thead>
                        <tbody>
                            <?php foreach ($pool_progress_rows as $pool) : ?>
                                <?php vaysf_render_results_desk_pool_progress_row($pool); ?>
                            <?php endforeach; ?>
                        </tbody>
                    </table>
                <?php endif; ?>
            </section>

            <?php if (!$rows) : ?>
                <div class="vaysf-score-entry-notice">
                    <p><?php esc_html_e('No games match this view.', 'vaysf'); ?></p>
                </div>
            <?php else : ?>
                <?php foreach ($rows as $row) : ?>
                    <?php
                    $scheduled_time = vaysf_format_schedule_display_time($row['scheduled_time'] ?? '', $row['scheduled_slot'] ?? '', 'D M j, g:i A');
                    if ($scheduled_time === __('TBD', 'vaysf')) {
                        $scheduled_time = esc_html__('Time TBD', 'vaysf');
                    }
                    $location_parts = array_filter(array($row['scheduled_location'] ?? '', $row['resource_id'] ?? '', $row['scheduled_slot'] ?? ''));
                    $location_text = $location_parts ? implode(' / ', $location_parts) : esc_html__('Location TBD', 'vaysf');
                    $teams_text = vaysf_format_schedule_teams($row);
                    if ($teams_text === '') {
                        $teams_text = esc_html__('Teams TBD', 'vaysf');
                    }
                    $has_result = !empty($row['result_id']);
                    $status_label = $has_result
                        ? sprintf(
                            esc_html__('Submitted: %s', 'vaysf'),
                            !empty($row['public_status']) ? $row['public_status'] : esc_html__('pending', 'vaysf')
                        )
                        : esc_html__('Needs result', 'vaysf');
                    ?>
                    <article class="vaysf-score-entry-card">
                        <div class="vaysf-score-entry-card-header">
                            <div>
                                <div class="vaysf-score-entry-game-key"><?php echo esc_html($row['game_key']); ?></div>
                                <div class="vaysf-score-entry-meta"><?php echo esc_html($row['event']); ?></div>
                            </div>
                            <span class="vaysf-score-entry-status"><?php echo esc_html($status_label); ?></span>
                        </div>
                        <div class="vaysf-score-entry-teams"><?php echo esc_html($teams_text); ?></div>
                        <div class="vaysf-score-entry-meta"><?php echo esc_html($scheduled_time); ?></div>
                        <div class="vaysf-score-entry-meta"><?php echo esc_html($location_text); ?></div>
                        <?php if (vaysf_is_supported_score_schedule($row)) : ?>
                            <a
                                class="vaysf-score-entry-button vaysf-score-entry-action"
                                href="<?php echo esc_url(vaysf_get_score_form_url_by_game_key($row, $view, $selected_event)); ?>"
                            >
                                <?php echo $has_result ? esc_html__('Edit Score', 'vaysf') : esc_html__('Enter Score', 'vaysf'); ?>
                            </a>
                        <?php else : ?>
                            <button type="button" class="vaysf-score-entry-button" disabled>
                                <?php esc_html_e('Score form coming soon', 'vaysf'); ?>
                            </button>
                        <?php endif; ?>
                    </article>
                <?php endforeach; ?>
            <?php endif; ?>
            <?php endif; ?>
        <?php endif; ?>
    <?php endif; ?>
</div>

<?php
if (!$vaysf_rendering_shortcode) {
    get_footer();
}

<?php
/**
 * Coordinator score entry dashboard (Issue #239).
 *
 * This first slice is read-only: it proves login, capability checks, event
 * authorization, and schedule filtering before any result-writing form exists.
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

$vaysf_rendering_shortcode = !empty($GLOBALS['vaysf_rendering_coordinator_score_entry_shortcode']);

if (!$vaysf_rendering_shortcode) {
    get_header();
}

$view = isset($_GET['view']) ? sanitize_key(wp_unslash($_GET['view'])) : 'needs';
$requested_event = isset($_GET['event']) ? sanitize_text_field(wp_unslash($_GET['event'])) : '';
$tabs = array(
    'needs' => esc_html__('Needs Results', 'vaysf'),
    'submitted' => esc_html__('Submitted Today', 'vaysf'),
    'assigned' => esc_html__('Assigned Games', 'vaysf'),
);
if (!isset($tabs[$view])) {
    $view = 'needs';
}

$container_style = 'max-width: 960px; margin: 32px auto; padding: 20px;';
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
            padding: 9px 12px;
        }
        @media (max-width: 640px) {
            .vaysf-score-entry-dashboard {
                margin: 16px auto !important;
                padding: 14px !important;
            }
            .vaysf-score-entry-card-header {
                display: block;
            }
            .vaysf-score-entry-button {
                margin-top: 12px;
                width: 100%;
            }
        }
    </style>

    <h1><?php esc_html_e('Coordinator Score Entry', 'vaysf'); ?></h1>
    <p class="vaysf-score-entry-subtitle">
        <?php esc_html_e('Assigned games from the published Sports Fest schedule.', 'vaysf'); ?>
    </p>

    <?php if (!is_user_logged_in()) : ?>
        <div class="vaysf-score-entry-notice">
            <p><?php esc_html_e('Please log in with your coordinator account to view assigned games.', 'vaysf'); ?></p>
            <p>
                <a href="<?php echo esc_url(wp_login_url(vaysf_get_coordinator_score_entry_url('assigned'))); ?>">
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

            <?php if (!$rows) : ?>
                <div class="vaysf-score-entry-notice">
                    <p><?php esc_html_e('No games match this view.', 'vaysf'); ?></p>
                </div>
            <?php else : ?>
                <?php foreach ($rows as $row) : ?>
                    <?php
                    $scheduled_time = !empty($row['scheduled_time'])
                        ? date_i18n('D M j, g:i A', strtotime($row['scheduled_time']))
                        : esc_html__('Time TBD', 'vaysf');
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
                        <button type="button" class="vaysf-score-entry-button" disabled>
                            <?php esc_html_e('Enter Score - coming soon', 'vaysf'); ?>
                        </button>
                    </article>
                <?php endforeach; ?>
            <?php endif; ?>
        <?php endif; ?>
    <?php endif; ?>
</div>

<?php
if (!$vaysf_rendering_shortcode) {
    get_footer();
}

<?php
/**
 * File: includes/results-desk/render.php
 * Description: Results Desk HTML, CSS, dashboard, and profile rendering helpers.
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}


/**
 * Render a tiny help marker using the browser's native hover tooltip.
 *
 * @param string $label Visible marker text
 * @param string $tooltip Tooltip text
 * @return void
 */
function vaysf_render_results_desk_tooltip($label, $tooltip) {
    ?>
    <span class="vaysf-results-desk-help" title="<?php echo esc_attr($tooltip); ?>"><?php echo esc_html($label); ?></span>
    <?php
}

/**
 * Convert an internal pool-review flag key to compact display text.
 *
 * @param string $flag_key Internal flag key
 * @return string Human-readable label
 */
function vaysf_results_desk_pool_flag_label($flag_key) {
    switch (sanitize_key($flag_key)) {
        case 'missing_results':
            return __('Missing results', 'vaysf');
        case 'invalid_payload':
            return __('Invalid score', 'vaysf');
        case 'unsupported_payload':
            return __('Unsupported score', 'vaysf');
        case 'split_match':
            return __('Split match', 'vaysf');
        case 'tie':
            return __('Tie', 'vaysf');
        case 'unresolved_tiebreak':
            return __('Needs tiebreak', 'vaysf');
        case 'incomplete':
            return __('Incomplete', 'vaysf');
        default:
            return ucwords(str_replace('_', ' ', sanitize_key($flag_key)));
    }
}

function vaysf_render_results_desk_playoff_suggestions($suggestions) {
    if (!$suggestions) {
        echo '<span class="vaysf-results-desk-muted">' . esc_html__('Pending rules / TBD', 'vaysf') . '</span>';
        return;
    }
    ?>
    <ol class="vaysf-playoff-preview-list">
        <?php foreach ($suggestions as $suggestion) : ?>
            <li>
                <?php if (!empty($suggestion['seed'])) : ?>
                    <span class="vaysf-results-desk-muted"><?php echo esc_html(sprintf(__('Seed %d', 'vaysf'), (int) $suggestion['seed'])); ?></span>
                <?php endif; ?>
                <strong><?php echo esc_html($suggestion['label'] ?? __('TBD', 'vaysf')); ?></strong>
            </li>
        <?php endforeach; ?>
    </ol>
    <?php
}

/**
 * Render existing schedule-row status for one playoff preview row.
 *
 * @param array<string,mixed>|null $row Schedule row
 * @return void
 */
function vaysf_render_results_desk_playoff_schedule_status($row) {
    if (!$row) {
        echo '<span class="vaysf-results-desk-warning" title="' . esc_attr__('This schedule row does not exist for the current schedule version.', 'vaysf') . '">' . esc_html__('Missing row', 'vaysf') . '</span>';
        return;
    }

    $status = (string) ($row['game_status'] ?? 'scheduled');
    $protected = in_array($status, array('reported', 'official', 'under_review'), true)
        || trim((string) ($row['score_json'] ?? '')) !== '';
    $class = $protected ? 'vaysf-results-desk-warning' : 'vaysf-results-desk-pill';
    $tooltip = $protected
        ? __('This row already has a protected/reported result; do not overwrite silently.', 'vaysf')
        : __('This row exists and has no submitted score payload.', 'vaysf');
    ?>
    <span class="<?php echo esc_attr($class); ?>" title="<?php echo esc_attr($tooltip); ?>"><?php echo esc_html($status); ?></span>
    <br><small><?php echo esc_html(sprintf(__('ID %d', 'vaysf'), absint($row['schedule_id'] ?? 0))); ?></small>
    <?php if (!empty($row['schedule_id'])) : ?>
        <br><a class="button button-small" href="<?php echo esc_url(admin_url('admin.php?page=vaysf-schedules&action=edit&id=' . absint($row['schedule_id']))); ?>"><?php esc_html_e('Edit row', 'vaysf'); ?></a>
    <?php endif; ?>
    <?php
}

/**
 * Render confirmed review chips for an event-level preview.
 *
 * @param array<int,array<string,mixed>> $reviews Confirmed reviews
 * @return void
 */
function vaysf_render_results_desk_playoff_reviews($reviews) {
    if (!$reviews) {
        echo '<p class="vaysf-results-desk-muted">' . esc_html__('No confirmed pool reviews yet.', 'vaysf') . '</p>';
        return;
    }
    ?>
    <div class="vaysf-playoff-preview-reviews">
        <?php foreach ($reviews as $review) : ?>
            <?php $confirmer = get_userdata((int) ($review['confirmed_by_user_id'] ?? 0)); ?>
            <span class="<?php echo esc_attr(!empty($review['stale']) ? 'vaysf-results-desk-warning' : 'vaysf-results-desk-pill'); ?>" title="<?php echo esc_attr(vaysf_format_results_desk_datetime($review['confirmed_at'] ?? '')); ?>">
                <?php
                echo esc_html(sprintf(
                    /* translators: 1: pool id, 2: user display name */
                    __('%1$s by %2$s', 'vaysf'),
                    (string) ($review['pool_id'] ?? ''),
                    $confirmer ? $confirmer->display_name : __('a Sports Fest admin', 'vaysf')
                ));
                ?>
            </span>
            <?php if (!empty($review['review_note'])) : ?>
                <span class="vaysf-results-desk-warning" title="<?php echo esc_attr($review['review_note']); ?>"><?php esc_html_e('note', 'vaysf'); ?></span>
            <?php endif; ?>
        <?php endforeach; ?>
    </div>
    <?php
}

/**
 * Render the event-level playoff/QF preview panel.
 *
 * @param array<string,mixed> $preview Preview model
 * @param array<string,mixed> $filters Current Results Desk filters
 * @param string $return_url Current page URL, used to build the Apply return link
 * @return void
 */
function vaysf_render_results_desk_playoff_preview($preview, $filters = array(), $return_url = '') {
    ?>
    <section class="vaysf-results-desk-section">
        <h2>
            <?php esc_html_e('Playoff / QF Preview', 'vaysf'); ?>
            <?php vaysf_render_results_desk_tooltip('?', __('Preview from confirmed pool reviews and current schedule rows. On its own it does not create, update, or delete schedule rows. For Bible Challenge, an explicit Apply action lets an operator write a chosen semifinal matchup directly into the schedule.', 'vaysf')); ?>
        </h2>
        <?php if (($preview['status'] ?? '') === 'select_event') : ?>
            <div class="vaysf-results-desk-notice">
                <p><?php esc_html_e('Select one event above to preview its QF/Semifinal schedule rows and confirmed pool-review inputs.', 'vaysf'); ?></p>
            </div>
            <?php return; ?>
        <?php endif; ?>
        <?php if (($preview['status'] ?? '') === 'unsupported') : ?>
            <div class="vaysf-results-desk-notice">
                <p><?php esc_html_e('This event does not have a playoff preview rule yet.', 'vaysf'); ?></p>
            </div>
            <?php return; ?>
        <?php endif; ?>
        <?php if (($preview['status'] ?? '') !== 'ok') : ?>
            <div class="vaysf-results-desk-notice vaysf-results-desk-error">
                <p><?php esc_html_e('No published schedule is available for playoff preview.', 'vaysf'); ?></p>
            </div>
            <?php return; ?>
        <?php endif; ?>

        <p>
            <?php
            echo esc_html(sprintf(
                /* translators: 1: event name, 2: schedule version */
                __('Previewing %1$s using schedule version %2$d. Nothing is applied from this panel.', 'vaysf'),
                (string) ($preview['event'] ?? ''),
                absint($preview['schedule_version'] ?? 0)
            ));
            ?>
        </p>
        <?php if (!empty($preview['warnings']) && is_array($preview['warnings'])) : ?>
            <div class="vaysf-results-desk-notice">
                <?php foreach ($preview['warnings'] as $warning) : ?>
                    <p><?php echo esc_html($warning); ?></p>
                <?php endforeach; ?>
            </div>
        <?php endif; ?>
        <?php vaysf_render_results_desk_playoff_reviews($preview['reviews'] ?? array()); ?>

        <?php if (($preview['mode'] ?? '') === 'team_qf') : ?>
            <?php vaysf_render_results_desk_event_qf_seeding_panel((string) ($preview['event'] ?? ''), absint($preview['schedule_version'] ?? 0), $return_url); ?>
        <?php endif; ?>

        <?php if (($preview['mode'] ?? '') === 'bible_challenge') : ?>
            <?php vaysf_render_results_desk_bible_challenge_reorder_form($preview, $filters); ?>
        <?php elseif (($preview['mode'] ?? '') === 'team_qf') : ?>
            <?php vaysf_render_results_desk_team_qf_reorder_form($preview, $filters); ?>
        <?php endif; ?>

        <?php if (empty($preview['rows'])) : ?>
            <div class="vaysf-results-desk-ok"><?php esc_html_e('No playoff schedule rows exist yet for this event.', 'vaysf'); ?></div>
        <?php else : ?>
            <table class="vaysf-results-desk-table vaysf-playoff-preview-table">
                <thead>
                    <tr>
                        <th><?php esc_html_e('Expected Row', 'vaysf'); ?></th>
                        <th><?php esc_html_e('Current Schedule', 'vaysf'); ?></th>
                        <th><?php esc_html_e('Preview Labels', 'vaysf'); ?></th>
                        <th><?php esc_html_e('Operator Note', 'vaysf'); ?></th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($preview['rows'] as $row) : ?>
                        <tr>
                            <td><strong><?php echo esc_html($row['game_key'] ?? ''); ?></strong><br><small><?php echo esc_html($row['stage'] ?? ''); ?></small></td>
                            <td><?php vaysf_render_results_desk_playoff_schedule_status($row['schedule_row'] ?? null); ?></td>
                            <td><?php vaysf_render_results_desk_playoff_suggestions($row['suggestion'] ?? array()); ?></td>
                            <td><?php echo esc_html($row['note'] ?? ''); ?></td>
                        </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
        <?php endif; ?>

        <?php if (($preview['mode'] ?? '') === 'bible_challenge' && !empty($preview['can_customize'])) : ?>
            <?php vaysf_render_results_desk_bible_challenge_apply_form($preview, $return_url); ?>
        <?php elseif (($preview['mode'] ?? '') === 'team_qf' && !empty($preview['can_customize'])) : ?>
            <?php vaysf_render_results_desk_team_qf_apply_form($preview, $return_url); ?>
        <?php endif; ?>
    </section>
    <?php
}

/**
 * Render the cross-pool QF-seeding review/confirm panel for one BB/VB event
 * (Issue #329): the live-computed ranking (recomputed fresh on every page
 * load, not just at confirm time, so the coordinator always sees current
 * standings), any confirmed/stale status, coin-toss prompts for any group
 * still tied after every deterministic tie-break, and the "Confirm All
 * Pools for QF Seeding" action itself â€” gated on every pool being complete
 * and every tie resolved. Replaces the need to individually confirm each of
 * this event's pools (per-pool "Confirm Pool Review" is suppressed for
 * BB/VB events in vaysf_render_results_desk_pool_progress_row()).
 *
 * @param string $event Schedule event name
 * @param int $schedule_version Published schedule version
 * @param string $return_url Current page URL to redirect back to
 * @return void
 */
function vaysf_render_results_desk_event_qf_seeding_panel($event, $schedule_version, $return_url) {
    $sport_type = vaysf_results_desk_seeding_sport_type($event);
    if ($sport_type === null) {
        return;
    }

    $seeding = vaysf_results_desk_get_event_seeding_rankings($event, $schedule_version);
    $pool_id = vaysf_results_desk_event_seeding_pool_id();
    $existing = vaysf_get_pool_advancement($event, $pool_id, $schedule_version);
    $is_stale = $existing ? vaysf_pool_advancement_is_stale($event, $pool_id, $schedule_version, $seeding['rankings']) : false;
    $diff_field = $sport_type === 'basketball' ? 'capped_diff' : 'diff';
    ?>
    <div class="vaysf-qf-seeding-panel">
        <h3>
            <?php esc_html_e('Cross-Pool QF Seeding', 'vaysf'); ?>
            <?php vaysf_render_results_desk_tooltip('?', __('Official 2026 rule: W-L record, then head-to-head, then difficulty of schedule, then point differential, then coin toss. Confirming here replaces confirming each pool individually for this event.', 'vaysf')); ?>
        </h3>

        <?php if (empty($seeding['complete'])) : ?>
            <div class="vaysf-results-desk-notice">
                <p><?php esc_html_e('Every pool for this event must be fully reported before QF seeding can be confirmed.', 'vaysf'); ?></p>
            </div>
        <?php endif; ?>

        <?php if ($existing) : ?>
            <?php $confirmer = get_userdata((int) $existing['confirmed_by_user_id']); ?>
            <p>
                <span class="<?php echo esc_attr($is_stale ? 'vaysf-results-desk-warning' : 'vaysf-results-desk-pill'); ?>" title="<?php echo esc_attr(vaysf_format_results_desk_datetime($existing['confirmed_at'] ?? '')); ?>">
                    <?php
                    if ($is_stale) {
                        esc_html_e('Needs re-confirm', 'vaysf');
                    } else {
                        printf(
                            /* translators: %s: user display name */
                            esc_html__('Confirmed by %s', 'vaysf'),
                            esc_html($confirmer ? $confirmer->display_name : __('a Sports Fest admin', 'vaysf'))
                        );
                    }
                    ?>
                </span>
            </p>
        <?php endif; ?>

        <?php if (!empty($seeding['rankings'])) : ?>
            <table class="vaysf-results-desk-table vaysf-qf-seeding-table">
                <thead>
                    <tr>
                        <th><?php esc_html_e('Seed', 'vaysf'); ?></th>
                        <th><?php esc_html_e('Team', 'vaysf'); ?></th>
                        <th><?php esc_html_e('W-L', 'vaysf'); ?></th>
                        <th>
                            <?php esc_html_e('SOS', 'vaysf'); ?>
                            <?php vaysf_render_results_desk_tooltip('?', __('Difficulty of schedule: sum of every opponent played\'s own final win-loss record.', 'vaysf')); ?>
                        </th>
                        <th><?php esc_html_e('Point Diff', 'vaysf'); ?></th>
                        <th><?php esc_html_e('Status', 'vaysf'); ?></th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($seeding['rankings'] as $team) : ?>
                        <tr>
                            <td><?php echo empty($team['needs_coin_toss']) ? esc_html((string) $team['rank']) : 'â€”'; ?></td>
                            <td><?php echo esc_html((string) ($team['label'] ?? $team['team_key'])); ?></td>
                            <td><?php echo esc_html(((int) ($team['wins'] ?? 0)) . '-' . ((int) ($team['losses'] ?? 0))); ?></td>
                            <td><?php echo esc_html((string) ($team['sos'] ?? 0)); ?></td>
                            <td><?php echo esc_html((string) ($team[$diff_field] ?? 0)); ?></td>
                            <td>
                                <?php if (!empty($team['needs_coin_toss'])) : ?>
                                    <span class="vaysf-results-desk-warning"><?php esc_html_e('Tied â€” needs coin toss', 'vaysf'); ?></span>
                                <?php elseif (!empty($team['advances'])) : ?>
                                    <span class="vaysf-results-desk-pill"><?php esc_html_e('Advances', 'vaysf'); ?></span>
                                <?php endif; ?>
                            </td>
                        </tr>
                    <?php endforeach; ?>
                </tbody>
            </table>
        <?php endif; ?>

        <?php $qf_unresolved_groups = $seeding['qf_unresolved_groups'] ?? $seeding['unresolved_groups']; ?>
        <?php foreach ($qf_unresolved_groups as $group_keys) : ?>
            <?php vaysf_render_results_desk_coin_toss_form($event, $schedule_version, $group_keys, $seeding['rankings'], $return_url); ?>
        <?php endforeach; ?>

        <?php if (!empty($seeding['complete']) && !empty($seeding['qf_fully_resolved']) && !empty($seeding['rankings'])) : ?>
            <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                <input type="hidden" name="action" value="vaysf_confirm_event_qf_seeding">
                <input type="hidden" name="event" value="<?php echo esc_attr($event); ?>">
                <input type="hidden" name="schedule_version" value="<?php echo esc_attr($schedule_version); ?>">
                <input type="hidden" name="return_url" value="<?php echo esc_attr($return_url); ?>">
                <?php wp_nonce_field('vaysf_confirm_event_qf_seeding_' . $event . '_' . $schedule_version); ?>
                <button type="submit" class="button button-primary" title="<?php echo esc_attr__('Record this cross-pool seeding as reviewed for QF assignment below. This does not create schedule rows by itself.', 'vaysf'); ?>">
                    <?php echo esc_html($existing ? __('Re-confirm All Pools for QF Seeding', 'vaysf') : __('Confirm All Pools for QF Seeding', 'vaysf')); ?>
                </button>
            </form>
        <?php endif; ?>
    </div>
    <?php
}

/**
 * Render one coin-toss flip form per still-undecided pair within an
 * unresolved tied group (Issue #329). A group larger than 2 (rare â€” every
 * deterministic criterion including difficulty-of-schedule and point
 * differential would all have to tie) gets one form per pair; the
 * coordinator flips as many as needed, and the ranking recomputes after
 * each submit.
 *
 * @param string $event
 * @param int $schedule_version
 * @param array<int,string> $group_keys Team keys still tied together
 * @param array<int,array<string,mixed>> $rankings Full ranking rows, for labels
 * @param string $return_url
 * @return void
 */
function vaysf_render_results_desk_coin_toss_form($event, $schedule_version, $group_keys, $rankings, $return_url) {
    $by_key = array();
    foreach ($rankings as $team) {
        $by_key[$team['team_key']] = $team;
    }

    for ($i = 0; $i < count($group_keys); $i++) {
        for ($j = $i + 1; $j < count($group_keys); $j++) {
            $key_a = $group_keys[$i];
            $key_b = $group_keys[$j];
            $label_a = (string) ($by_key[$key_a]['label'] ?? $key_a);
            $label_b = (string) ($by_key[$key_b]['label'] ?? $key_b);
            ?>
            <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>" class="vaysf-coin-toss-form">
                <input type="hidden" name="action" value="vaysf_flip_coin_toss">
                <input type="hidden" name="event" value="<?php echo esc_attr($event); ?>">
                <input type="hidden" name="schedule_version" value="<?php echo esc_attr($schedule_version); ?>">
                <input type="hidden" name="team_a_key" value="<?php echo esc_attr($key_a); ?>">
                <input type="hidden" name="team_a_label" value="<?php echo esc_attr($label_a); ?>">
                <input type="hidden" name="team_b_key" value="<?php echo esc_attr($key_b); ?>">
                <input type="hidden" name="team_b_label" value="<?php echo esc_attr($label_b); ?>">
                <input type="hidden" name="return_url" value="<?php echo esc_attr($return_url); ?>">
                <?php wp_nonce_field('vaysf_flip_coin_toss_' . $event . '_' . $schedule_version . '_' . $key_a . '_' . $key_b); ?>
                <p class="vaysf-results-desk-warning">
                    <?php echo esc_html(sprintf(
                        /* translators: 1: first tied team, 2: second tied team */
                        __('%1$s vs %2$s tied after every deterministic tie-break.', 'vaysf'),
                        $label_a,
                        $label_b
                    )); ?>
                </p>
                <label>
                    <?php esc_html_e('Calling team', 'vaysf'); ?>
                    <select name="call_by_key">
                        <option value="<?php echo esc_attr($key_a); ?>"><?php echo esc_html($label_a); ?></option>
                        <option value="<?php echo esc_attr($key_b); ?>"><?php echo esc_html($label_b); ?></option>
                    </select>
                </label>
                <label>
                    <?php esc_html_e('Call', 'vaysf'); ?>
                    <select name="call">
                        <option value="heads"><?php esc_html_e('Heads', 'vaysf'); ?></option>
                        <option value="tails"><?php esc_html_e('Tails', 'vaysf'); ?></option>
                    </select>
                </label>
                <button type="submit" class="button" title="<?php echo esc_attr__('The server generates the flip result for fairness â€” the call is human, the flip is not.', 'vaysf'); ?>">
                    <?php esc_html_e('Flip coin', 'vaysf'); ?>
                </button>
            </form>
            <?php
        }
    }
}

/**
 * Render the dropdown-based semifinal reassignment form for the Bible
 * Challenge preview. Session-only: selections travel as GET params
 * (`bc_seed[<game_key>][]`) and are never persisted, per operator request â€”
 * reloading without those params returns to the top-seed-protection default.
 *
 * @param array<string,mixed> $preview Preview model from
 *        vaysf_results_desk_build_bible_challenge_preview()
 * @param array<string,mixed> $filters Current Results Desk filters
 * @return void
 */
function vaysf_render_results_desk_bible_challenge_reorder_form($preview, $filters) {
    if (empty($preview['can_customize'])) {
        return;
    }

    $teams_by_key = $preview['teams_by_key'] ?? array();
    $arrangement = $preview['arrangement'] ?? array();
    ?>
    <form method="get" class="vaysf-bc-reorder-form">
        <input type="hidden" name="event" value="<?php echo esc_attr($filters['event'] ?? ''); ?>">
        <?php if (!empty($filters['church'])) : ?>
            <input type="hidden" name="church" value="<?php echo esc_attr($filters['church']); ?>">
        <?php endif; ?>
        <p class="vaysf-results-desk-muted">
            <?php esc_html_e('Reassign which confirmed Top-9 team plays in each semifinal, then click Update preview. This only changes what you see in this browser.', 'vaysf'); ?>
        </p>
        <div class="vaysf-bc-reorder-grid">
            <?php foreach ($arrangement as $game_key => $team_keys) : ?>
                <fieldset>
                    <legend><?php echo esc_html($game_key); ?></legend>
                    <?php foreach ($team_keys as $selected_key) : ?>
                        <select name="bc_seed[<?php echo esc_attr($game_key); ?>][]">
                            <?php foreach ($teams_by_key as $team_key => $team) : ?>
                                <option value="<?php echo esc_attr($team_key); ?>" <?php selected($selected_key, $team_key); ?>>
                                    <?php echo esc_html(sprintf(__('#%1$d %2$s', 'vaysf'), (int) $team['seed'], $team['label'])); ?>
                                </option>
                            <?php endforeach; ?>
                        </select>
                    <?php endforeach; ?>
                </fieldset>
            <?php endforeach; ?>
        </div>
        <button type="submit" class="button"><?php esc_html_e('Update preview', 'vaysf'); ?></button>
        <?php if (!empty($preview['custom_active'])) : ?>
            <a class="button" href="<?php echo esc_url(remove_query_arg('bc_seed')); ?>"><?php esc_html_e('Reset to top-seed protection', 'vaysf'); ?></a>
        <?php endif; ?>
    </form>
    <?php
}

/**
 * Render the Apply action for the Bible Challenge semifinal preview. This is
 * the one control on this panel that writes to the database: it submits the
 * arrangement currently shown (top-seed-protection default or the operator's custom
 * pick) to vaysf_handle_apply_bible_challenge_preview_request(), which writes
 * team_a/b/c directly into the BC-Semi-1/2/3 schedule rows, creating them if
 * missing. This deliberately bypasses the normal publish-schedule pipeline
 * (docs/SCHEDULING.md) at the operator's explicit request, so a later
 * schedule publish could still overwrite these rows if it targets the same
 * game_keys â€” Applying does not mark them protected.
 *
 * @param array<string,mixed> $preview Preview model
 * @param string $return_url Current page URL to redirect back to
 * @return void
 */
function vaysf_render_results_desk_bible_challenge_apply_form($preview, $return_url) {
    $event = (string) ($preview['event'] ?? '');
    $schedule_version = absint($preview['schedule_version'] ?? 0);
    ?>
    <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>" class="vaysf-bc-apply-form">
        <input type="hidden" name="action" value="vaysf_apply_bible_challenge_preview">
        <input type="hidden" name="event" value="<?php echo esc_attr($event); ?>">
        <input type="hidden" name="schedule_version" value="<?php echo esc_attr($schedule_version); ?>">
        <input type="hidden" name="return_url" value="<?php echo esc_attr($return_url); ?>">
        <?php foreach ($preview['arrangement'] ?? array() as $game_key => $team_keys) : ?>
            <?php foreach ($team_keys as $team_key) : ?>
                <input type="hidden" name="bc_seed[<?php echo esc_attr($game_key); ?>][]" value="<?php echo esc_attr($team_key); ?>">
            <?php endforeach; ?>
        <?php endforeach; ?>
        <?php wp_nonce_field('vaysf_apply_bible_challenge_preview_' . $event . '_' . $schedule_version); ?>
        <button
            type="submit"
            class="button button-primary"
            onclick="return confirm('<?php echo esc_js(__('Write this exact matchup into BC-Semi-1, BC-Semi-2, and BC-Semi-3, then prewire BC-Final with semifinal winner placeholders? This writes directly to the schedule, bypassing the normal publish-schedule pipeline, and rows already reported/official are skipped rather than overwritten.', 'vaysf')); ?>');"
        >
            <?php esc_html_e('Apply matchup to schedule', 'vaysf'); ?>
        </button>
        <p class="vaysf-results-desk-muted"><?php esc_html_e('Writes the teams shown above directly into the BC-Semi-1/2/3 schedule rows (creating them if missing), then prewires BC-Final with semifinal winner placeholders. Rows already reported, official, under review, or already scored are skipped, never overwritten. Court and time are left untouched.', 'vaysf'); ?></p>
    </form>
    <?php
}

/**
 * Render the QF reassignment form for Basketball/Volleyball.
 *
 * @param array<string,mixed> $preview Preview model
 * @param array<string,mixed> $filters Current Results Desk filters
 * @return void
 */
function vaysf_render_results_desk_team_qf_reorder_form($preview, $filters) {
    if (empty($preview['can_customize'])) {
        return;
    }

    $teams_by_key = $preview['teams_by_key'] ?? array();
    $arrangement = $preview['arrangement'] ?? array();
    ?>
    <form method="get" class="vaysf-playoff-assignment-form">
        <input type="hidden" name="event" value="<?php echo esc_attr($filters['event'] ?? ''); ?>">
        <?php if (!empty($filters['church'])) : ?>
            <input type="hidden" name="church" value="<?php echo esc_attr($filters['church']); ?>">
        <?php endif; ?>
        <p class="vaysf-results-desk-muted">
            <?php esc_html_e('Assign confirmed pool-review teams into QF matchups, then click Update preview. This only changes what you see in this browser until Apply is clicked.', 'vaysf'); ?>
        </p>
        <div class="vaysf-playoff-assignment-grid">
            <?php foreach ($arrangement as $game_key => $team_keys) : ?>
                <fieldset>
                    <legend><?php echo esc_html($game_key); ?></legend>
                    <?php foreach ($team_keys as $slot_index => $selected_key) : ?>
                        <label>
                            <span class="vaysf-results-desk-muted"><?php echo esc_html($slot_index === 0 ? __('Slot A', 'vaysf') : __('Slot B', 'vaysf')); ?></span>
                            <select name="qf_seed[<?php echo esc_attr($game_key); ?>][]">
                                <?php foreach ($teams_by_key as $team_key => $team) : ?>
                                    <option value="<?php echo esc_attr($team_key); ?>" <?php selected($selected_key, $team_key); ?>>
                                        <?php echo esc_html(vaysf_results_desk_team_qf_option_label($team)); ?>
                                    </option>
                                <?php endforeach; ?>
                            </select>
                        </label>
                    <?php endforeach; ?>
                </fieldset>
            <?php endforeach; ?>
        </div>
        <button type="submit" class="button"><?php esc_html_e('Update preview', 'vaysf'); ?></button>
        <?php if (!empty($preview['custom_active'])) : ?>
            <a class="button" href="<?php echo esc_url(remove_query_arg('qf_seed')); ?>"><?php esc_html_e('Reset to default QF order', 'vaysf'); ?></a>
        <?php endif; ?>
    </form>
    <?php
}

/**
 * Render the Apply action for the Basketball/Volleyball QF preview.
 *
 * @param array<string,mixed> $preview Preview model
 * @param string $return_url Current page URL to redirect back to
 * @return void
 */
function vaysf_render_results_desk_team_qf_apply_form($preview, $return_url) {
    $event = (string) ($preview['event'] ?? '');
    $schedule_version = absint($preview['schedule_version'] ?? 0);
    ?>
    <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>" class="vaysf-playoff-apply-form">
        <input type="hidden" name="action" value="vaysf_apply_team_qf_preview">
        <input type="hidden" name="event" value="<?php echo esc_attr($event); ?>">
        <input type="hidden" name="schedule_version" value="<?php echo esc_attr($schedule_version); ?>">
        <input type="hidden" name="return_url" value="<?php echo esc_attr($return_url); ?>">
        <?php foreach ($preview['arrangement'] ?? array() as $game_key => $team_keys) : ?>
            <?php foreach ($team_keys as $team_key) : ?>
                <input type="hidden" name="qf_seed[<?php echo esc_attr($game_key); ?>][]" value="<?php echo esc_attr($team_key); ?>">
            <?php endforeach; ?>
        <?php endforeach; ?>
        <?php wp_nonce_field('vaysf_apply_team_qf_preview_' . $event . '_' . $schedule_version); ?>
        <button
            type="submit"
            class="button button-primary"
            onclick="return confirm('<?php echo esc_js(__('Write this exact QF matchup into the Basketball/Volleyball QF-1..4 schedule rows (creating them if missing), then prewire Semifinal/Final/3rd-Place placeholders? Rows already reported, official, or under review are skipped rather than overwritten.', 'vaysf')); ?>');"
        >
            <?php esc_html_e('Apply QF matchup to schedule', 'vaysf'); ?>
        </button>
        <p class="vaysf-results-desk-muted"><?php esc_html_e('Writes team A/team B into the QF-1..4 schedule rows (creating them if missing), then prewires Semifinal/Final/3rd-Place rows with winner/loser placeholders. Court and time are preserved when a row already exists.', 'vaysf'); ?></p>
    </form>
    <?php
}

/**
 * Render compact provisional rankings for one pool.
 *
 * @param array<int,array<string,mixed>> $rankings Ranking rows
 * @param string $event Schedule event name
 * @return void
 */
function vaysf_render_results_desk_pool_rankings($rankings, $event = '') {
    if (!$rankings) {
        echo '<span class="vaysf-results-desk-muted">' . esc_html__('No scored games yet.', 'vaysf') . '</span>';
        return;
    }
    $rule_note = vaysf_results_desk_pool_ranking_rule_note($event);
    ?>
    <?php if ($rule_note !== '') : ?>
        <p class="vaysf-results-desk-muted" style="margin: 0 0 8px;"><?php echo esc_html($rule_note); ?></p>
    <?php endif; ?>
    <ol class="vaysf-results-desk-rankings">
        <?php foreach ($rankings as $team) : ?>
            <?php
            $is_total_score_ranking = (($team['ranking_basis'] ?? '') === 'total_score');
            if ($is_total_score_ranking) {
                $record = sprintf(
                    /* translators: %d: cumulative Bible Challenge preliminary score */
                    __('Total %d', 'vaysf'),
                    (int) ($team['for'] ?? 0)
                );
                $metric = sprintf(
                    /* translators: %d: number of preliminary rows scored for this team */
                    _n('%d prelim scored', '%d prelims scored', (int) ($team['played'] ?? 0), 'vaysf'),
                    (int) ($team['played'] ?? 0)
                );
                $record_tooltip = __('Bible Challenge ranks by cumulative preliminary score. The top 9 advance.', 'vaysf');
                $metric_tooltip = __('Number of submitted preliminary score rows included in this team total.', 'vaysf');
            } else {
                $record = sprintf(
                    '%d-%d-%d',
                    (int) ($team['wins'] ?? 0),
                    (int) ($team['losses'] ?? 0),
                    (int) ($team['ties'] ?? 0)
                );
                $metric = sprintf(
                    'PF %d / PA %d / %+d',
                    (int) ($team['for'] ?? 0),
                    (int) ($team['against'] ?? 0),
                    (int) ($team['diff'] ?? 0)
                );
                $record_tooltip = __('Record is wins-losses-ties from scored pool games.', 'vaysf');
                $metric_tooltip = __('PF/PA are points for and points against from the score payload. For volleyball this uses match score units, usually sets won/lost.', 'vaysf');
            }
            $notes = !empty($team['notes']) && is_array($team['notes']) ? implode('; ', $team['notes']) : '';
            ?>
            <li value="<?php echo esc_attr((string) ($team['rank'] ?? 1)); ?>">
                <strong><?php echo esc_html($team['label'] ?? $team['team_key'] ?? ''); ?></strong>
                <span class="vaysf-results-desk-pill" title="<?php echo esc_attr($record_tooltip); ?>"><?php echo esc_html($record); ?></span>
                <?php if (!empty($team['advances'])) : ?>
                    <span class="vaysf-results-desk-pill" title="<?php echo esc_attr__('Top 9 by cumulative Bible Challenge preliminary score advance.', 'vaysf'); ?>"><?php esc_html_e('Advances', 'vaysf'); ?></span>
                <?php endif; ?>
                <span class="vaysf-results-desk-muted" title="<?php echo esc_attr($metric_tooltip); ?>"><?php echo esc_html($metric); ?></span>
                <?php if ($notes !== '') : ?>
                    <span class="vaysf-results-desk-warning" title="<?php echo esc_attr($notes); ?>"><?php echo esc_html__('note', 'vaysf'); ?></span>
                <?php endif; ?>
            </li>
        <?php endforeach; ?>
    </ol>
    <?php
}

/**
 * Render one pool progress row.
 *
 * @param array<string,mixed> $pool Pool progress row
 * @param string $return_url Results Desk URL to redirect back to after
 *        confirming advancement (Issue #207)
 * @return void
 */
function vaysf_render_results_desk_pool_progress_row($pool, $return_url = '') {
    if ($return_url === '') {
        $return_url = vaysf_results_desk_current_request_url();
    }

    $game_count = max(0, (int) ($pool['game_count'] ?? 0));
    $reported_count = max(0, (int) ($pool['reported_count'] ?? 0));
    $missing_count = max(0, (int) ($pool['missing_count'] ?? 0));
    $percent = $game_count > 0 ? round(($reported_count / $game_count) * 100) : 0;
    $pool_flags = !empty($pool['flags']) && is_array($pool['flags']) ? $pool['flags'] : array();
    $flag_messages = array_values($pool_flags);
    $flag_tooltip = $flag_messages ? implode(' ', $flag_messages) : __('No ranking flags for this pool.', 'vaysf');
    ?>
    <tr>
        <td>
            <strong><?php echo esc_html($pool['event'] ?? ''); ?></strong><br>
            <small><?php echo esc_html(trim(($pool['stage'] ?? '') . ' ' . ($pool['pool_id'] ?? ''))); ?></small>
        </td>
        <td>
            <div class="vaysf-results-desk-progress" title="<?php echo esc_attr__('Reported games divided by total published pool/prelim games. A complete pool is ready for human advancement review, not automatic advancement.', 'vaysf'); ?>">
                <span style="width: <?php echo esc_attr((string) $percent); ?>%;"></span>
            </div>
            <strong><?php echo esc_html(sprintf(__('%1$d / %2$d scored', 'vaysf'), $reported_count, $game_count)); ?></strong>
            <?php if ($missing_count > 0) : ?>
                <br><small><?php echo esc_html(sprintf(_n('%d missing result', '%d missing results', $missing_count, 'vaysf'), $missing_count)); ?></small>
            <?php else : ?>
                <br><small><?php echo esc_html__('complete', 'vaysf'); ?></small>
            <?php endif; ?>
        </td>
        <td>
            <?php vaysf_render_results_desk_pool_rankings($pool['rankings'] ?? array(), $pool['event'] ?? ''); ?>
        </td>
        <td>
            <span class="<?php echo esc_attr(!empty($pool['complete']) ? 'vaysf-results-desk-pill' : 'vaysf-results-desk-warning'); ?>" title="<?php echo esc_attr($flag_tooltip); ?>">
                <?php echo !empty($pool['complete']) ? esc_html__('Ready', 'vaysf') : esc_html__('In progress', 'vaysf'); ?>
            </span>
            <?php if ($pool_flags) : ?>
                <br>
                <?php foreach ($pool_flags as $flag_key => $flag_message) : ?>
                    <small class="vaysf-results-desk-warning vaysf-results-desk-flag" title="<?php echo esc_attr($flag_message); ?>">
                        <?php echo esc_html(vaysf_results_desk_pool_flag_label($flag_key)); ?>
                    </small>
                <?php endforeach; ?>
            <?php endif; ?>
        </td>
        <td><?php echo esc_html(vaysf_format_results_desk_datetime($pool['last_updated_at'] ?? '')); ?></td>
        <td>
            <?php
            $pool_event = (string) ($pool['event'] ?? '');
            $pool_id_value = (string) ($pool['pool_id'] ?? '');
            $pool_schedule_version = absint($pool['schedule_version'] ?? 0);
            $advancement = vaysf_get_pool_advancement($pool_event, $pool_id_value, $pool_schedule_version);
            $is_stale = $advancement ? vaysf_pool_advancement_is_stale($pool_event, $pool_id_value, $pool_schedule_version, $pool['rankings'] ?? array()) : false;
            ?>
            <?php if ($advancement && $is_stale) : ?>
                <span class="vaysf-results-desk-warning" title="<?php esc_attr_e('A result contributing to this pool was corrected after advancement was confirmed. Re-confirm after reviewing the standings.', 'vaysf'); ?>">
                    <?php esc_html_e('Needs re-confirm', 'vaysf'); ?>
                </span>
            <?php elseif ($advancement) : ?>
                <?php $confirmer = get_userdata((int) $advancement['confirmed_by_user_id']); ?>
                <span class="vaysf-results-desk-pill" title="<?php echo esc_attr(vaysf_format_results_desk_datetime($advancement['confirmed_at'] ?? '')); ?>">
                    <?php
                    printf(
                        /* translators: %s: user display name */
                        esc_html__('Confirmed by %s', 'vaysf'),
                        esc_html($confirmer ? $confirmer->display_name : __('a Sports Fest admin', 'vaysf'))
                    );
                    ?>
                </span>
                <?php if (!empty($advancement['review_note'])) : ?>
                    <br><small class="vaysf-results-desk-note-display" title="<?php echo esc_attr($advancement['review_note']); ?>">
                        <?php echo esc_html(sprintf(__('Note: %s', 'vaysf'), $advancement['review_note'])); ?>
                    </small>
                <?php endif; ?>
            <?php endif; ?>
            <?php if (vaysf_results_desk_seeding_sport_type($pool_event) !== null) : ?>
                <?php if (!empty($pool['complete'])) : ?>
                    <p class="vaysf-results-desk-muted"><?php esc_html_e('Confirmed together with the event\'s other pools via "Confirm All Pools for QF Seeding" below.', 'vaysf'); ?></p>
                <?php endif; ?>
            <?php elseif (!empty($pool['complete'])) : ?>
                <?php
                $has_unresolved_tie = !empty($pool['needs_manual_tiebreak']);
                $existing_review_note = is_array($advancement) && isset($advancement['review_note'])
                    ? (string) $advancement['review_note']
                    : '';
                $is_bible_challenge_pool = vaysf_results_desk_is_bible_challenge_event($pool_event);
                if ($is_bible_challenge_pool) {
                    $confirm_label = $advancement ? __('Re-confirm Top 9', 'vaysf') : __('Confirm Top 9', 'vaysf');
                    if ($has_unresolved_tie) {
                        $confirm_tooltip = $advancement
                            ? __('Update the saved Bible Challenge review note while the cutoff tie remains available for the next-page finalization step. This does not change scores or automatically populate semifinal/final games.', 'vaysf')
                            : __('Save the current Bible Challenge rankings and cutoff-tie note as reviewed for the next-page finalization step. This does not change scores or automatically populate semifinal/final games.', 'vaysf');
                    } else {
                        $confirm_tooltip = $advancement
                            ? __('Update the saved Bible Challenge advancement confirmation using the current top 9 teams by cumulative preliminary score. This does not change scores or automatically populate semifinal/final games.', 'vaysf')
                            : __('Save the current Bible Challenge top 9 teams by cumulative preliminary score as reviewed for advancement. This does not change scores or automatically populate semifinal/final games.', 'vaysf');
                    }
                } else {
                    $confirm_label = $advancement ? __('Re-confirm Pool Review', 'vaysf') : __('Confirm Pool Review', 'vaysf');
                    if ($has_unresolved_tie) {
                        $confirm_tooltip = $advancement
                            ? __('Update this pool review note and keep the unresolved tie available for the next-page QF/playoff finalization step. This does not choose wildcards, assign seeds, submit QF matchups, change scores, or populate schedule rows.', 'vaysf')
                            : __('Record this pool ranking and tie note as reviewed for the next-page QF/playoff finalization step. This does not choose wildcards, assign seeds, submit QF matchups, change scores, or populate schedule rows.', 'vaysf');
                    } else {
                        $confirm_tooltip = $advancement
                            ? __('Update this pool ranking as reviewed for event-level QF/playoff finalization. This does not choose wildcards, assign seeds, submit QF matchups, change scores, or populate schedule rows.', 'vaysf')
                            : __('Record this pool ranking as reviewed for event-level QF/playoff finalization. This does not choose wildcards, assign seeds, submit QF matchups, change scores, or populate schedule rows.', 'vaysf');
                    }
                }
                ?>
                <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                    <input type="hidden" name="action" value="vaysf_confirm_pool_advancement">
                    <input type="hidden" name="event" value="<?php echo esc_attr($pool_event); ?>">
                    <input type="hidden" name="pool_id" value="<?php echo esc_attr($pool_id_value); ?>">
                    <input type="hidden" name="return_url" value="<?php echo esc_attr($return_url); ?>">
                    <?php wp_nonce_field('vaysf_confirm_pool_advancement_' . $pool_event . '_' . $pool_id_value); ?>
                    <?php if ($has_unresolved_tie) : ?>
                        <label class="vaysf-pool-review-note-label">
                            <?php esc_html_e('Tie review note', 'vaysf'); ?>
                            <textarea class="vaysf-pool-review-note" name="review_note" rows="2" required placeholder="<?php echo esc_attr__('Example: FVC/NSD/RPC tied; resolve manually on QF page.', 'vaysf'); ?>"><?php echo esc_textarea($existing_review_note); ?></textarea>
                        </label>
                    <?php endif; ?>
                    <button type="submit" class="button button-primary button-small" title="<?php echo esc_attr($confirm_tooltip); ?>" aria-label="<?php echo esc_attr($confirm_tooltip); ?>">
                        <?php echo esc_html($confirm_label); ?>
                    </button>
                </form>
            <?php endif; ?>
        </td>
    </tr>
    <?php
}

/**
 * Render one schedule/result row in a Results Desk table.
 *
 * @param array<string,mixed> $row Row data
 * @param string $mode Display mode
 * @return void
 */
function vaysf_render_results_desk_game_row($row, $mode = 'default') {
    $teams = vaysf_format_schedule_teams($row);
    if ($teams === '') {
        $teams = __('Teams TBD', 'vaysf');
    }
    $scheduled = vaysf_format_schedule_display_time($row['scheduled_time'] ?? '', $row['scheduled_slot'] ?? '', 'D M j, g:i A');
    $result_url = !empty($row['result_id'])
        ? admin_url('admin.php?page=vaysf-results&action=edit&id=' . absint($row['result_id']))
        : admin_url('admin.php?page=vaysf-results&action=new');
    ?>
    <tr>
        <td><strong><?php echo esc_html($row['game_key'] ?? ''); ?></strong><br><small><?php echo esc_html($row['event'] ?? ''); ?></small></td>
        <td><?php echo esc_html($teams); ?></td>
        <td><?php echo esc_html($scheduled); ?><br><small><?php echo esc_html($row['scheduled_location'] ?? $row['resource_id'] ?? ''); ?></small></td>
        <td>
            <?php echo esc_html($row['public_status'] ?? $row['game_status'] ?? 'scheduled'); ?>
            <?php if (!empty($row['scan_status'])) : ?>
                <br><small><?php echo esc_html__('Scan:', 'vaysf'); ?> <?php echo esc_html($row['scan_status']); ?></small>
            <?php endif; ?>
            <?php if ($mode === 'correction' && !empty($row['verification_state'])) : ?>
                <br><small><?php echo esc_html__('Revision:', 'vaysf'); ?> <?php echo esc_html($row['revision_number']); ?> / <?php echo esc_html($row['verification_state']); ?></small>
            <?php endif; ?>
        </td>
        <td>
            <a class="button button-small" href="<?php echo esc_url($result_url); ?>">
                <?php echo !empty($row['result_id']) ? esc_html__('Review', 'vaysf') : esc_html__('Create Result', 'vaysf'); ?>
            </a>
        </td>
    </tr>
    <?php
}

/**
 * Render a Results Desk section table.
 *
 * @param string $title Section title
 * @param string $description Section description
 * @param array<int,array<string,mixed>> $rows Rows
 * @param string $empty_message Empty state
 * @param string $mode Display mode
 * @return void
 */
function vaysf_render_results_desk_section($title, $description, $rows, $empty_message, $mode = 'default') {
    ?>
    <section class="vaysf-results-desk-section">
        <h2><?php echo esc_html($title); ?></h2>
        <p><?php echo esc_html($description); ?></p>
        <?php if (!$rows) : ?>
            <div class="vaysf-results-desk-ok"><?php echo esc_html($empty_message); ?></div>
        <?php else : ?>
            <table class="vaysf-results-desk-table">
                <thead>
                    <tr>
                        <th><?php esc_html_e('Game', 'vaysf'); ?></th>
                        <th><?php esc_html_e('Matchup', 'vaysf'); ?></th>
                        <th><?php esc_html_e('Time / Location', 'vaysf'); ?></th>
                        <th><?php esc_html_e('Status', 'vaysf'); ?></th>
                        <th><?php esc_html_e('Action', 'vaysf'); ?></th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($rows as $row) : ?>
                        <?php vaysf_render_results_desk_game_row($row, $mode); ?>
                    <?php endforeach; ?>
                </tbody>
            </table>
        <?php endif; ?>
    </section>
    <?php
}

/**
 * Render the Results Desk dashboard.
 *
 * @param array<string,mixed> $atts Shortcode/template attributes
 * @return string HTML
 */
function vaysf_render_results_desk($atts = array()) {
    $filters = vaysf_sanitize_results_desk_filters($atts);
    $return_url = vaysf_results_desk_current_request_url();

    ob_start();
    ?>
    <div class="vaysf-results-desk">
        <style>
            .vaysf-results-desk * { box-sizing: border-box; }
            .vaysf-results-desk { max-width: 1180px; margin: 32px auto; padding: 20px; }
            .vaysf-results-desk h1 { margin: 0 0 8px; font-size: 2rem; line-height: 1.2; }
            .vaysf-results-desk-subtitle { margin: 0 0 20px; color: #50575e; }
            .vaysf-results-desk-notice { background: #fff8e5; border-left: 4px solid #dba617; margin: 20px 0; padding: 14px 16px; }
            .vaysf-results-desk-error { background: #fde8e8; border-left-color: #cc1818; }
            .vaysf-results-desk-toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: end; margin: 20px 0; padding: 14px; background: #f6f7f7; border: 1px solid #dcdcde; }
            .vaysf-results-desk-toolbar label { display: flex; flex-direction: column; gap: 4px; font-weight: 600; }
            .vaysf-results-desk-toolbar select { min-width: 240px; }
            .vaysf-results-desk-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 20px 0; }
            .vaysf-results-desk-card { background: #fff; border: 1px solid #dcdcde; border-radius: 8px; padding: 14px; box-shadow: 0 1px 2px rgba(0,0,0,.04); }
            .vaysf-results-desk-card strong { display: block; font-size: 1.6rem; line-height: 1.2; }
            .vaysf-results-desk-card span { color: #50575e; font-size: .9rem; }
            .vaysf-results-desk-section { margin: 28px 0; }
            .vaysf-results-desk-section h2 { margin-bottom: 4px; }
            .vaysf-results-desk-table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #dcdcde; }
            .vaysf-results-desk-table th, .vaysf-results-desk-table td { border-bottom: 1px solid #dcdcde; padding: 10px; text-align: left; vertical-align: top; }
            .vaysf-results-desk-table th { background: #f6f7f7; }
            .vaysf-results-desk-ok { background: #ecf7ed; border-left: 4px solid #46b450; padding: 12px 14px; }
            .vaysf-results-desk-heartbeat { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px; margin: 14px 0 24px; color: #50575e; }
            .vaysf-results-desk-help { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; background: #dcdcde; color: #1d2327; font-size: 12px; font-weight: 700; cursor: help; }
            .vaysf-results-desk-muted { color: #646970; font-size: .9em; }
            .vaysf-results-desk-warning { display: inline-block; border: 1px solid #dba617; border-radius: 4px; background: #fff8e5; color: #674e00; padding: 2px 6px; cursor: help; }
            .vaysf-results-desk-pill { display: inline-block; border: 1px solid #c3d9c8; border-radius: 4px; background: #ecf7ed; color: #1d5727; padding: 2px 6px; cursor: help; }
            .vaysf-results-desk-flag { margin: 4px 4px 0 0; font-size: .85em; }
            .vaysf-results-desk-progress { width: 160px; max-width: 100%; height: 10px; margin: 0 0 6px; overflow: hidden; border-radius: 999px; background: #dcdcde; cursor: help; }
            .vaysf-results-desk-progress span { display: block; height: 100%; background: #46b450; }
            .vaysf-results-desk-rankings { margin: 0; padding-left: 26px; }
            .vaysf-results-desk-rankings li { margin: 0 0 6px; }
            .vaysf-results-desk-rankings li:last-child { margin-bottom: 0; }
            .vaysf-pool-review-note-label { display: block; margin: 6px 0; max-width: 230px; font-size: .85em; color: #50575e; }
            .vaysf-pool-review-note { display: block; width: 100%; min-height: 44px; margin-top: 3px; font-size: 12px; }
            .vaysf-results-desk-note-display { display: inline-block; max-width: 260px; margin-top: 4px; color: #50575e; }
            .vaysf-playoff-preview-reviews { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 14px; }
            .vaysf-playoff-preview-list { margin: 0; padding-left: 22px; }
            .vaysf-playoff-preview-list li { margin: 0 0 5px; }
            .vaysf-playoff-preview-list li:last-child { margin-bottom: 0; }
            .vaysf-playoff-preview-table td:nth-child(3) { min-width: 220px; }
            .vaysf-bc-reorder-form { margin: 12px 0; padding: 10px; border: 1px solid #dcdcde; border-radius: 4px; background: #f9f9f9; }
            .vaysf-bc-reorder-grid { display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 10px; }
            .vaysf-bc-reorder-grid fieldset { display: flex; flex-direction: column; gap: 4px; min-width: 200px; padding: 8px; border: 1px solid #dcdcde; border-radius: 4px; }
            .vaysf-bc-reorder-grid legend { font-weight: 600; padding: 0 4px; }
            .vaysf-bc-apply-form { margin: 12px 0; padding: 10px; border: 1px solid #dba617; border-radius: 4px; background: #fff8e5; }
            .vaysf-playoff-assignment-form { margin: 12px 0; padding: 10px; border: 1px solid #dcdcde; border-radius: 4px; background: #f9f9f9; }
            .vaysf-playoff-assignment-grid { display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 10px; }
            .vaysf-playoff-assignment-grid fieldset { display: flex; flex-direction: column; gap: 6px; min-width: 220px; padding: 8px; border: 1px solid #dcdcde; border-radius: 4px; }
            .vaysf-playoff-assignment-grid label { display: flex; flex-direction: column; gap: 2px; }
            .vaysf-playoff-assignment-grid legend { font-weight: 600; padding: 0 4px; }
            .vaysf-playoff-apply-form { margin: 12px 0; padding: 10px; border: 1px solid #dba617; border-radius: 4px; background: #fff8e5; }
            .vaysf-qf-seeding-panel { margin: 12px 0; padding: 10px; border: 1px solid #dcdcde; border-radius: 4px; background: #f9f9f9; }
            .vaysf-qf-seeding-table { margin: 10px 0; }
            .vaysf-coin-toss-form { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 10px; margin: 10px 0; padding: 10px; border: 1px solid #dba617; border-radius: 4px; background: #fff8e5; }
            .vaysf-coin-toss-form p { flex-basis: 100%; margin: 0 0 4px; }
            .vaysf-coin-toss-form label { display: flex; flex-direction: column; gap: 2px; }
            @media (max-width: 768px) {
                .vaysf-results-desk-table { display: block; overflow-x: auto; }
            }
        </style>

        <h1><?php esc_html_e('Sports Fest Results Desk', 'vaysf'); ?></h1>
        <p class="vaysf-results-desk-subtitle"><?php esc_html_e('Read-only command center for missing, disputed, corrected, and scan-pending event-day results.', 'vaysf'); ?></p>

        <?php if (!is_user_logged_in()) : ?>
            <div class="vaysf-results-desk-notice">
                <p><?php esc_html_e('Please log in with a Sports Fest Manager or Admin account to view the Results Desk.', 'vaysf'); ?></p>
                <p><a href="<?php echo esc_url(wp_login_url($return_url)); ?>"><?php esc_html_e('Log in', 'vaysf'); ?></a></p>
            </div>
        <?php elseif (!vaysf_user_can_view_results_desk()) : ?>
            <div class="vaysf-results-desk-notice vaysf-results-desk-error">
                <p><?php esc_html_e('Your account is not authorized to view the Sports Fest Results Desk.', 'vaysf'); ?></p>
            </div>
        <?php else : ?>
            <?php
            $advancement_status = isset($_GET['vaysf_advancement_status']) ? sanitize_key(wp_unslash($_GET['vaysf_advancement_status'])) : '';
            $advancement_message = isset($_GET['vaysf_advancement_message']) ? sanitize_text_field(wp_unslash($_GET['vaysf_advancement_message'])) : '';
            if ($advancement_status !== '' && $advancement_message !== '') :
                $notice_class = $advancement_status === 'error' ? 'vaysf-results-desk-notice vaysf-results-desk-error' : 'vaysf-results-desk-notice vaysf-results-desk-ok';
                ?>
                <div class="<?php echo esc_attr($notice_class); ?>">
                    <p><?php echo esc_html($advancement_message); ?></p>
                </div>
            <?php endif; ?>
            <?php
            $summary = vaysf_get_results_desk_summary($filters);
            $events = vaysf_get_published_schedule_events($summary['schedule_version']);
            $churches = function_exists('vaysf_get_public_schedule_churches')
                ? vaysf_get_public_schedule_churches($summary['schedule_version'])
                : array();
            $manifest_url = wp_nonce_url(
                add_query_arg(
                    array_filter(
                        array(
                            'action' => 'vaysf_download_results_manifest',
                            'event' => $filters['event'],
                            'church' => $filters['church'],
                        )
                    ),
                    admin_url('admin-post.php')
                ),
                'vaysf_download_results_manifest'
            );
            ?>
            <form method="get" class="vaysf-results-desk-toolbar">
                <label>
                    <?php esc_html_e('Event', 'vaysf'); ?>
                    <select name="event">
                        <option value=""><?php esc_html_e('All events', 'vaysf'); ?></option>
                        <?php foreach ($events as $event) : ?>
                            <option value="<?php echo esc_attr($event); ?>" <?php selected($filters['event'], $event); ?>><?php echo esc_html($event); ?></option>
                        <?php endforeach; ?>
                    </select>
                </label>
                <?php if (!empty($churches)) : ?>
                    <label>
                        <?php esc_html_e('Church', 'vaysf'); ?>
                        <select name="church">
                            <option value=""><?php esc_html_e('All churches', 'vaysf'); ?></option>
                            <?php foreach ($churches as $code) : ?>
                                <option value="<?php echo esc_attr($code); ?>" <?php selected($filters['church'], $code); ?>><?php echo esc_html($code); ?></option>
                            <?php endforeach; ?>
                        </select>
                    </label>
                <?php endif; ?>
                <button type="submit" class="button button-primary"><?php esc_html_e('Filter', 'vaysf'); ?></button>
                <a class="button" href="<?php echo esc_url(vaysf_get_results_desk_url()); ?>"><?php esc_html_e('Reset', 'vaysf'); ?></a>
                <a class="button" href="<?php echo esc_url($manifest_url); ?>"><?php esc_html_e('Download Results Manifest CSV', 'vaysf'); ?></a>
            </form>

            <div class="vaysf-results-desk-cards">
                <div class="vaysf-results-desk-card"><strong><?php echo esc_html($summary['total_games']); ?></strong><span><?php esc_html_e('Published games', 'vaysf'); ?></span></div>
                <div class="vaysf-results-desk-card"><strong><?php echo esc_html($summary['reported_results']); ?></strong><span><?php esc_html_e('With score payloads', 'vaysf'); ?></span></div>
                <div class="vaysf-results-desk-card"><strong><?php echo esc_html($summary['late_missing']); ?></strong><span><?php esc_html_e('Late / missing', 'vaysf'); ?></span></div>
                <div class="vaysf-results-desk-card"><strong><?php echo esc_html($summary['attention']); ?></strong><span><?php esc_html_e('Need review', 'vaysf'); ?></span></div>
                <div class="vaysf-results-desk-card"><strong><?php echo esc_html($summary['missing_scans']); ?></strong><span><?php esc_html_e('Missing scans', 'vaysf'); ?></span></div>
                <div class="vaysf-results-desk-card"><strong><?php echo esc_html($summary['complete_pools']); ?></strong><span><?php esc_html_e('Ready pools', 'vaysf'); ?></span></div>
            </div>

            <div class="vaysf-results-desk-heartbeat">
                <div><strong><?php esc_html_e('Schedule version:', 'vaysf'); ?></strong> <?php echo esc_html($summary['schedule_version'] ?: '-'); ?></div>
                <div><strong><?php esc_html_e('Public data updated:', 'vaysf'); ?></strong> <?php echo esc_html(vaysf_format_results_desk_datetime($summary['public_data_updated_at'])); ?></div>
                <div><strong><?php esc_html_e('Sports Fest time:', 'vaysf'); ?></strong> <?php echo esc_html(vaysf_format_results_desk_datetime($summary['sports_fest_time'], vaysf_get_sports_fest_timezone())); ?></div>
            </div>

            <?php
            vaysf_render_results_desk_section(
                __('Late / Missing Results', 'vaysf'),
                sprintf(__('Games scheduled at least %d minutes ago with no score payload.', 'vaysf'), absint($filters['late_grace_minutes'])),
                vaysf_get_results_desk_rows('late_missing', $filters),
                __('No late missing results in this filter.', 'vaysf')
            );

            vaysf_render_results_desk_section(
                __('Recent Corrections', 'vaysf'),
                sprintf(__('Revision history from the last %d hours.', 'vaysf'), absint($filters['revision_hours'])),
                vaysf_get_results_desk_rows('recent_corrections', $filters),
                __('No recent corrections in this filter.', 'vaysf'),
                'correction'
            );

            vaysf_render_results_desk_section(
                __('Needs Review / Disputed', 'vaysf'),
                __('A first submission is accepted immediately; a game only lands here once a correction (a second, different score) has come in and needs a human to resolve the mismatch.', 'vaysf'),
                vaysf_get_results_desk_rows('attention', $filters),
                __('No results currently need review in this filter.', 'vaysf')
            );

            vaysf_render_results_desk_section(
                __('Missing Score Sheet Scans', 'vaysf'),
                __('Results with score payloads but no protected scan/photo attachment yet.', 'vaysf'),
                vaysf_get_results_desk_rows('missing_scans', $filters),
                __('No missing score sheet scans in this filter.', 'vaysf')
            );
            ?>

            <section class="vaysf-results-desk-section">
                <h2>
                    <?php esc_html_e('Pools Progress For Review', 'vaysf'); ?>
                    <?php vaysf_render_results_desk_tooltip('?', __('This section is a review aid. It summarizes pool/prelim progress and provisional ranking signals from submitted score payloads, but it does not confirm advancement automatically.', 'vaysf')); ?>
                </h2>
                <p><?php esc_html_e('Pool/prelim progress and provisional ranking signals from current score payloads. Use this to decide advancement manually.', 'vaysf'); ?></p>
                <?php $pool_progress = vaysf_get_results_desk_rows('pool_progress', $filters); ?>
                <?php if (!$pool_progress) : ?>
                    <div class="vaysf-results-desk-ok"><?php esc_html_e('No pool progress is available in this filter.', 'vaysf'); ?></div>
                <?php else : ?>
                    <table class="vaysf-results-desk-table">
                        <thead>
                            <tr>
                                <th><?php esc_html_e('Pool', 'vaysf'); ?></th>
                                <th>
                                    <?php esc_html_e('Progress', 'vaysf'); ?>
                                    <?php vaysf_render_results_desk_tooltip('?', __('Reported games divided by total published pool/prelim games.', 'vaysf')); ?>
                                </th>
                                <th>
                                    <?php esc_html_e('Provisional Rankings', 'vaysf'); ?>
                                    <?php vaysf_render_results_desk_tooltip('?', __('Default rankings sort by wins, then ties, point differential, and points for. Bible Challenge ranks by cumulative preliminary score, and the top 9 advance. Cutoff ties still require human review.', 'vaysf')); ?>
                                </th>
                                <th>
                                    <?php esc_html_e('Review Status', 'vaysf'); ?>
                                    <?php vaysf_render_results_desk_tooltip('?', __('Ready means all games in this pool have a score payload. It does not mean semifinal/final slots were confirmed.', 'vaysf')); ?>
                                </th>
                                <th><?php esc_html_e('Last Updated', 'vaysf'); ?></th>
                                <th>
                                    <?php esc_html_e('Advancement', 'vaysf'); ?>
                                    <?php vaysf_render_results_desk_tooltip('?', __('Confirming advancement records who confirmed it and when. It does not move teams into Semifinal/Final schedule rows for you â€” use the schedule editor for that once you trust the ranking shown here.', 'vaysf')); ?>
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            <?php foreach ($pool_progress as $pool) : ?>
                                <?php vaysf_render_results_desk_pool_progress_row($pool, $return_url); ?>
                            <?php endforeach; ?>
                        </tbody>
                    </table>
                <?php endif; ?>
            </section>

            <?php vaysf_render_results_desk_playoff_preview(vaysf_get_results_desk_playoff_preview($filters), $filters, $return_url); ?>
        <?php endif; ?>
    </div>
    <?php

    return ob_get_clean();
}

/**
 * Render a Results Desk link on user profile screens, for Sports Fest
 * Managers/Admins, right above the "Update Profile" button.
 *
 * @param WP_User $user User being viewed
 * @return void
 */
function vaysf_render_results_desk_profile_link($user) {
    if (!is_object($user) || !vaysf_user_can_view_results_desk($user->ID)) {
        return;
    }

    if ((int) get_current_user_id() !== (int) $user->ID && !current_user_can('edit_user', $user->ID)) {
        return;
    }

    ?>
    <h2><?php esc_html_e('Sports Fest Results Desk', 'vaysf'); ?></h2>
    <table class="form-table" role="presentation">
        <tr>
            <th scope="row"><?php esc_html_e('Results Desk', 'vaysf'); ?></th>
            <td>
                <p>
                    <a class="button button-primary" href="<?php echo esc_url(vaysf_get_results_desk_url()); ?>">
                        <?php esc_html_e('Open Results Desk', 'vaysf'); ?>
                    </a>
                </p>
                <p class="description">
                    <?php esc_html_e('Read-only command center for missing, disputed, corrected, and scan-pending event-day results.', 'vaysf'); ?>
                </p>
            </td>
        </tr>
    </table>
    <?php
}

/**
 * Register a wp-admin dashboard widget for Sports Fest Managers/Admins.
 *
 * @return void
 */
function vaysf_register_results_desk_dashboard_widget() {
    if (!vaysf_user_can_view_results_desk()) {
        return;
    }

    wp_add_dashboard_widget(
        'vaysf_results_desk',
        esc_html__('Sports Fest Results Desk', 'vaysf'),
        'vaysf_render_results_desk_dashboard_widget'
    );
}

/**
 * Render the wp-admin Results Desk dashboard widget.
 *
 * @return void
 */
function vaysf_render_results_desk_dashboard_widget() {
    $summary = vaysf_get_results_desk_summary();
    ?>
    <p><?php esc_html_e('Review event-day results that are missing, disputed, corrected, scan-pending, or ready for advancement review.', 'vaysf'); ?></p>
    <ul>
        <li><strong><?php echo esc_html($summary['late_missing']); ?></strong> <?php esc_html_e('late/missing results', 'vaysf'); ?></li>
        <li><strong><?php echo esc_html($summary['attention']); ?></strong> <?php esc_html_e('results needing review', 'vaysf'); ?></li>
        <li><strong><?php echo esc_html($summary['missing_scans']); ?></strong> <?php esc_html_e('missing score sheet scans', 'vaysf'); ?></li>
        <li><strong><?php echo esc_html($summary['complete_pools']); ?></strong> <?php esc_html_e('pools ready for human advancement review', 'vaysf'); ?></li>
    </ul>
    <p>
        <a class="button button-primary" href="<?php echo esc_url(vaysf_get_results_desk_url()); ?>">
            <?php esc_html_e('Open Results Desk', 'vaysf'); ?>
        </a>
    </p>
    <?php
}

<?php
/**
 * File: includes/shortcodes.php
 * Description: Shortcodes for VAYSF Integration
 * Version: 1.0.0
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

// Include statistics class
require_once plugin_dir_path(__FILE__) . 'class-vaysf-statistics.php';

class VAYSF_Shortcodes {

    /**
     * Constructor
     */
    public function __construct() {
        // Register shortcodes
        add_shortcode('vaysf_stats', array($this, 'stats_shortcode'));
        add_shortcode('vaysf_churches', array($this, 'churches_shortcode'));
        add_shortcode('vaysf_participants', array($this, 'participants_shortcode'));
        add_shortcode('vaysf_live_schedule', array($this, 'live_schedule_shortcode'));
        add_shortcode('vaysf_advancement', array($this, 'advancement_shortcode'));
        add_shortcode('vaysf_results_desk', array($this, 'results_desk_shortcode'));
        add_shortcode('vaysf_badges', array($this, 'badges_shortcode'));
    }
    
    /**
     * Shortcode for overall statistics
     * 
     * @param array $atts Shortcode attributes
     * @return string Shortcode output
     */
    public function stats_shortcode($atts) {
        // Parse attributes
        $atts = shortcode_atts(array(
            'display' => 'all', // all, churches, participants, approvals, issues
            'layout' => 'grid', // grid, list
        ), $atts);
        
        // Get stats
        $stats = VAYSF_Statistics::get_overall_stats();
        
        // Start output buffering
        ob_start();
        
        // Output stats based on display attribute
        if ($atts['layout'] == 'grid') {
            echo '<div class="vaysf-stats-grid">';
        } else {
            echo '<div class="vaysf-stats-list">';
        }
        
        // Churches stats
        if ($atts['display'] == 'all' || $atts['display'] == 'churches') {
            $this->render_stat_box(
                $stats['churches']['label'], 
                $stats['churches']['count'], 
                $stats['churches']['icon']
            );
        }
        
        // Participants stats
        if ($atts['display'] == 'all' || $atts['display'] == 'participants') {
            $this->render_stat_box(
                $stats['participants']['label'], 
                $stats['participants']['count'], 
                $stats['participants']['icon']
            );
            $this->render_stat_box(
                $stats['approved']['label'], 
                $stats['approved']['count'], 
                $stats['approved']['icon']
            );
            $this->render_stat_box(
                $stats['denied']['label'], 
                $stats['denied']['count'], 
                $stats['denied']['icon']
            );
        }
        
        // Approvals stats
        if ($atts['display'] == 'all' || $atts['display'] == 'approvals') {
            $this->render_stat_box(
                $stats['pending_approvals']['label'], 
                $stats['pending_approvals']['count'], 
                $stats['pending_approvals']['icon']
            );
        }
        
        // Validation issues stats
        if ($atts['display'] == 'all' || $atts['display'] == 'issues') {
            $this->render_stat_box(
                $stats['validation_issues']['label'], 
                $stats['validation_issues']['count'], 
                $stats['validation_issues']['icon']
            );
        }
        
        echo '</div>';
        
        // Include CSS
        $this->include_frontend_styles();
        
        // Return the buffered output
        return ob_get_clean();
    }
    
    /**
     * Shortcode for churches list
     * 
     * @param array $atts Shortcode attributes
     * @return string Shortcode output
     */
    public function churches_shortcode($atts) {
        // Parse attributes
        $atts = shortcode_atts(array(
            'limit' => 10,
            'orderby' => 'church_name',
            'order' => 'ASC',
            'status' => '',
            'insurance_status' => '',
            'show_stats' => 'yes',
            'stats' => 'participants,approval_ratio',
            'badges_page_url' => '',
        ), $atts);

        $church_stat_keys = $this->get_requested_church_stats($atts['stats']);
        if (!$this->is_truthy($atts['show_stats'])) {
            $church_stat_keys = array();
        }

        $atts['include_stats'] = !empty($church_stat_keys);
        $badges_page_url = $this->resolve_badges_page_url($atts['badges_page_url']);
        
        // Get churches
        $churches = VAYSF_Statistics::get_churches($atts);
        
        // Start output buffering
        ob_start();
        
        if (empty($churches)) {
            echo '<p>No churches found.</p>';
        } else {
            echo '<table class="vaysf-churches-table">';
            echo '<thead><tr>';
            echo '<th>Church</th>';
            echo '<th>Pastor</th>';
            echo '<th>Participants</th>';
            echo '<th>Insurance</th>';
            echo '</tr></thead>';
            echo '<tbody>';
            
            foreach ($churches as $church) {
                echo '<tr>';
                echo '<td>';
                echo '<div class="vaysf-church-name">' . esc_html($church['church_name']) . ' (' . esc_html($church['church_code']) . ')</div>';
                $this->render_church_stats($church, $church_stat_keys);
                echo '</td>';
                echo '<td>' . esc_html($church['pastor_name']) . '</td>';
                echo '<td><a class="vaysf-participants-button" href="' . esc_url($this->build_church_badges_url($badges_page_url, $church['church_code'])) . '">' . esc_html__('Participants', 'vaysf') . '</a></td>';
                echo '<td>';
                if (function_exists('vaysf_format_insurance_status')) {
                    echo vaysf_format_insurance_status($church['insurance_status']);
                } else {
                    echo esc_html(ucfirst($church['insurance_status']));
                }
                if (!empty($church['insurance_uploaded_at'])) {
                    echo '<br><small>' . esc_html(date_i18n('M j, Y', strtotime($church['insurance_uploaded_at']))) . '</small>';
                }
                echo '</td>';
                echo '</tr>';
            }
            
            echo '</tbody></table>';
        }
        
        // Include CSS
        $this->include_frontend_styles();
        
        // Return the buffered output
        return ob_get_clean();
    }
    
    /**
     * Shortcode for participants list
     * 
     * @param array $atts Shortcode attributes
     * @return string Shortcode output
     */
    public function participants_shortcode($atts) {
        // Parse attributes
        $atts = shortcode_atts(array(
            'limit' => 10,
            'orderby' => 'last_name',
            'order' => 'ASC',
            'church_code' => '',
            'status' => '',
            'sport' => '',
        ), $atts);
        
        // Get participants
        $participants = VAYSF_Statistics::get_participants($atts);
        
        // Start output buffering
        ob_start();
        
        if (empty($participants)) {
            echo '<p>No participants found.</p>';
        } else {
            echo '<table class="vaysf-participants-table">';
            echo '<thead><tr>';
            echo '<th>Name</th>';
            echo '<th>Church</th>';
            echo '<th>Primary Sport</th>';
            echo '<th>Status</th>';
            echo '</tr></thead>';
            echo '<tbody>';
            
            foreach ($participants as $participant) {
                echo '<tr>';
                echo '<td>' . esc_html($participant['first_name'] . ' ' . $participant['last_name']) . '</td>';
                echo '<td>' . esc_html($participant['church_name']) . '</td>';
                echo '<td>' . esc_html($participant['primary_sport']) . '</td>';
                
                // Status with appropriate styling
                $status_class = $this->get_status_class($participant['approval_status']);
                echo '<td><span class="approval-status ' . $status_class . '">';
                echo esc_html(ucwords(str_replace('_', ' ', $participant['approval_status'])));
                echo '</span></td>';
                
                echo '</tr>';
            }
            
            echo '</tbody></table>';
        }
        
        // Include CSS
        $this->include_frontend_styles();
        
        // Return the buffered output
        return ob_get_clean();
    }

    /**
     * Shortcode for approved participant badge gallery by church code (Issue #290).
     *
     * @param array $atts Shortcode attributes
     * @return string Shortcode output
     */
    public function badges_shortcode($atts) {
        $atts = shortcode_atts(array(
            'church_code' => '',
            'columns' => 4,
            'show_names' => 'yes',
        ), $atts);

        $church_code = $this->resolve_badges_church_code($atts['church_code']);
        $columns = max(1, min(6, absint($atts['columns'])));
        $show_names = $this->is_truthy($atts['show_names']);

        ob_start();

        if (empty($church_code)) {
            echo '<p class="vaysf-badges-empty">' . esc_html__('Choose a church to view participant badges.', 'vaysf') . '</p>';
            $this->include_frontend_styles();
            return ob_get_clean();
        }

        $church = $this->get_badges_church($church_code);
        if (!$church) {
            echo '<p class="vaysf-badges-empty">' . esc_html__('Church not found.', 'vaysf') . '</p>';
            $this->include_frontend_styles();
            return ob_get_clean();
        }

        $participants = $this->get_badges_participants($church_code);
        $badges = array();
        $missing = 0;
        foreach ($participants as $participant) {
            $badge_url = $this->find_badge_url_for_participant($participant);
            if (empty($badge_url)) {
                $missing++;
                continue;
            }

            $participant['badge_url'] = $badge_url;
            $badges[] = $participant;
        }

        echo '<div class="vaysf-badges" style="--vaysf-badge-columns:' . esc_attr((string) $columns) . '">';
        echo '<div class="vaysf-badges-heading">';
        echo '<h2>' . esc_html($church['church_name']) . ' (' . esc_html($church_code) . ')</h2>';
        echo '<p>' . esc_html(sprintf(
            _n('%d approved badge available', '%d approved badges available', count($badges), 'vaysf'),
            count($badges)
        )) . '</p>';
        echo '</div>';

        if (empty($badges)) {
            echo '<p class="vaysf-badges-empty">' . esc_html__('No approved badge images are available for this church yet.', 'vaysf') . '</p>';
        } else {
            echo '<div class="vaysf-badges-grid">';
            foreach ($badges as $participant) {
                $name = trim(($participant['first_name'] ?? '') . ' ' . ($participant['last_name'] ?? ''));
                echo '<figure class="vaysf-badge-card">';
                echo '<a href="' . esc_url($participant['badge_url']) . '" target="_blank" rel="noopener noreferrer">';
                echo '<img src="' . esc_url($participant['badge_url']) . '" alt="' . esc_attr(sprintf(__('Badge for %s', 'vaysf'), $name ?: __('participant', 'vaysf'))) . '" loading="lazy">';
                echo '</a>';
                if ($show_names) {
                    echo '<figcaption>';
                    echo '<span class="vaysf-badge-name">' . esc_html($name ?: __('Unnamed participant', 'vaysf')) . '</span>';
                    if (!empty($participant['primary_sport'])) {
                        echo '<span class="vaysf-badge-meta">' . esc_html($participant['primary_sport']) . '</span>';
                    }
                    echo '</figcaption>';
                }
                echo '</figure>';
            }
            echo '</div>';
        }

        if ($missing > 0) {
            echo '<p class="vaysf-badges-note">' . esc_html(sprintf(
                _n(
                    '%d approved participant does not have an uploaded badge image yet.',
                    '%d approved participants do not have uploaded badge images yet.',
                    $missing,
                    'vaysf'
                ),
                $missing
            )) . '</p>';
        }
        echo '</div>';

        $this->include_frontend_styles();
        return ob_get_clean();
    }

    /**
     * Shortcode for the manager/admin Results Desk (Issue #208).
     *
     * @param array $atts Shortcode attributes
     * @return string Shortcode output
     */
    public function results_desk_shortcode($atts) {
        if (!function_exists('vaysf_render_results_desk')) {
            return '<p>' . esc_html__('Results Desk is not available.', 'vaysf') . '</p>';
        }

        $atts = shortcode_atts(array(
            'event' => '',
            'late_grace_minutes' => 75,
            'revision_hours' => 12,
            'limit' => 50,
        ), $atts);

        return vaysf_render_results_desk($atts);
    }
    
    /**
     * Shortcode for the spectator-facing live schedule and reported scores (Issue #206).
     *
     * Standings are intentionally not part of this shortcode: the resolved
     * event-day RFC decision is no automatic standings for the 2026 release,
     * and there is no per-sport rules configuration yet to compute them from
     * (that is future work, not this shortcode's job).
     *
     * @param array $atts Shortcode attributes: event, day, venue, church,
     *                    lookback_minutes, refresh (seconds; 0 disables auto-refresh)
     * @return string Shortcode output
     */
    public function live_schedule_shortcode($atts) {
        $atts = shortcode_atts(array(
            'event' => '',
            'day' => '',
            'venue' => '',
            'church' => '',
            'lookback_minutes' => null,
            'refresh' => 25,
        ), $atts);

        $event = isset($_GET['vaysf_event']) ? sanitize_text_field(wp_unslash($_GET['vaysf_event'])) : $atts['event'];
        $day = isset($_GET['vaysf_day']) ? vaysf_sanitize_public_day_filter($_GET['vaysf_day']) : vaysf_sanitize_public_day_filter($atts['day']);
        $venue = $atts['venue'];
        $church = isset($_GET['vaysf_church'])
            ? vaysf_sanitize_public_church_filter($_GET['vaysf_church'])
            : vaysf_sanitize_public_church_filter($atts['church']);
        // Visitor-facing "upcoming games only" checkbox; when checked it takes
        // precedence over an embed's lookback_minutes attribute and caps the
        // window at the end of today, unlike lookback_minutes (see #303).
        $upcoming_only = isset($_GET['vaysf_upcoming']) && vaysf_sanitize_public_upcoming_filter($_GET['vaysf_upcoming']);
        $lookback_minutes = vaysf_sanitize_public_lookback_minutes($atts['lookback_minutes']);
        $refresh_seconds = max(0, (int) $atts['refresh']);

        $filters = array(
            'event' => $event,
            'day' => $day,
            'venue' => $venue,
            'church' => $church,
            'lookback_minutes' => $lookback_minutes,
            'upcoming_only' => $upcoming_only ? '1' : '',
        );
        $rows = vaysf_get_public_schedule_rows($filters);

        ob_start();
        $instance_id = wp_unique_id('vaysf-live-schedule-');
        $should_autoscroll = isset($_GET['vaysf_event']);
        static $scoreboard_anchor_rendered = false;
        $anchor_id = '';
        if ($should_autoscroll && !$scoreboard_anchor_rendered) {
            $anchor_id = 'vaysf-scoreboard';
            $scoreboard_anchor_rendered = true;
        }
        ?>
        <?php if ($anchor_id !== '') : ?>
            <span id="<?php echo esc_attr($anchor_id); ?>" class="vaysf-scoreboard-anchor" aria-hidden="true"></span>
        <?php endif; ?>
        <div class="vaysf-live-schedule" id="<?php echo esc_attr($instance_id); ?>" data-refresh-seconds="<?php echo esc_attr($refresh_seconds); ?>">
            <?php $this->render_public_filter_form($event, $day, $church, $upcoming_only); ?>

            <p class="vaysf-live-schedule-empty"<?php echo empty($rows) ? '' : ' hidden'; ?>><?php echo esc_html__('No published schedule yet.', 'vaysf'); ?></p>
            <table class="vaysf-live-schedule-table"<?php echo empty($rows) ? ' hidden' : ''; ?>>
                    <thead>
                        <tr>
                            <th><?php echo esc_html__('Time', 'vaysf'); ?></th>
                            <th><?php echo esc_html__('Event', 'vaysf'); ?></th>
                            <th><?php echo esc_html__('Matchup', 'vaysf'); ?></th>
                            <th><?php echo esc_html__('Location', 'vaysf'); ?></th>
                            <th><?php echo esc_html__('Status', 'vaysf'); ?></th>
                            <th><?php echo esc_html__('Score', 'vaysf'); ?></th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($rows as $row) : $this->render_live_schedule_row($row); endforeach; ?>
                    </tbody>
            </table>
            <p class="vaysf-live-schedule-updated">
                <?php echo esc_html__('Last updated:', 'vaysf'); ?>
                <span class="vaysf-last-updated"><?php echo esc_html(vaysf_format_sports_fest_time(vaysf_get_sports_fest_now(), 'g:i:s a')); ?></span>
            </p>
        </div>
        <?php
        $this->include_frontend_styles();
        if ($should_autoscroll) {
            $this->render_live_schedule_autoscroll_script($instance_id);
        }
        if ($refresh_seconds > 0) {
            $this->render_live_schedule_script($instance_id, $filters, $refresh_seconds);
        }

        return ob_get_clean();
    }

    /**
     * Shortcode for spectator-facing confirmed semifinal/final advancement (Issue #206).
     *
     * "Confirmed" reflects an admin having populated the Semifinal/Final
     * schedule row's team slots after deciding pool-play qualifiers — see
     * vaysf_get_public_advancement_rows() for why no separate confirmation
     * flag is needed.
     *
     * @param array $atts Shortcode attributes: event, refresh (seconds; 0 disables auto-refresh)
     * @return string Shortcode output
     */
    public function advancement_shortcode($atts) {
        $atts = shortcode_atts(array(
            'event' => '',
            'refresh' => 60,
            'title' => __('Playoff Advancement', 'vaysf'),
            'subtitle' => __('Confirmed semifinal and final matchups update here as coordinators advance teams.', 'vaysf'),
        ), $atts);

        $event = isset($_GET['vaysf_event']) ? sanitize_text_field(wp_unslash($_GET['vaysf_event'])) : $atts['event'];
        $refresh_seconds = max(0, (int) $atts['refresh']);
        $title = sanitize_text_field($atts['title']);
        $subtitle = sanitize_text_field($atts['subtitle']);
        $rows = vaysf_get_public_advancement_rows(array('event' => $event));

        ob_start();
        $instance_id = wp_unique_id('vaysf-advancement-');
        ?>
        <div class="vaysf-advancement" id="<?php echo esc_attr($instance_id); ?>" data-refresh-seconds="<?php echo esc_attr($refresh_seconds); ?>">
            <div class="vaysf-advancement-heading">
                <?php if ($title !== '') : ?>
                    <h2><?php echo esc_html($title); ?></h2>
                <?php endif; ?>
                <?php if ($subtitle !== '') : ?>
                    <p><?php echo esc_html($subtitle); ?></p>
                <?php endif; ?>
            </div>
            <p class="vaysf-advancement-empty" <?php hidden(!empty($rows)); ?>><?php echo esc_html__('No confirmed advancement yet.', 'vaysf'); ?></p>
            <table class="vaysf-advancement-table" <?php hidden(empty($rows)); ?>>
                <thead>
                    <tr>
                        <th><?php echo esc_html__('Event', 'vaysf'); ?></th>
                        <th><?php echo esc_html__('Stage', 'vaysf'); ?></th>
                        <th><?php echo esc_html__('Matchup', 'vaysf'); ?></th>
                        <th><?php echo esc_html__('Time', 'vaysf'); ?></th>
                        <th><?php echo esc_html__('Location', 'vaysf'); ?></th>
                    </tr>
                </thead>
                <tbody>
                    <?php foreach ($rows as $row) : $this->render_advancement_row($row); endforeach; ?>
                </tbody>
            </table>
            <p class="vaysf-advancement-updated">
                <?php echo esc_html__('Last checked:', 'vaysf'); ?>
                <span class="vaysf-advancement-last-updated"><?php echo esc_html(vaysf_format_sports_fest_time(vaysf_get_sports_fest_now(), 'g:i:s a')); ?></span>
            </p>
        </div>
        <?php
        $this->include_frontend_styles();
        if ($refresh_seconds > 0) {
            $this->render_advancement_script($instance_id, array('event' => $event), $refresh_seconds);
        }

        return ob_get_clean();
    }

    /**
     * Render the GET-based sport/day/church/upcoming filter form shared by
     * public shortcodes.
     *
     * A plain GET form works without JavaScript; the auto-refresh script layers
     * on top for spectators who leave the page open. A small inline script
     * additionally remembers the visitor's selections in a first-party,
     * preference-only cookie (no PII, no tracking) so a later visit with no
     * query string restores the same view (#303).
     *
     * @param string $event Selected event filter
     * @param string $day Selected day filter (Y-m-d)
     * @param string $church Selected church code filter
     * @param bool $upcoming_only Whether the "upcoming games only" checkbox is checked
     */
    private function render_public_filter_form($event, $day, $church, $upcoming_only = false) {
        $events = vaysf_get_published_schedule_events();
        $days = vaysf_get_public_schedule_days();
        $churches = function_exists('vaysf_get_public_schedule_churches')
            ? vaysf_get_public_schedule_churches()
            : array();

        if (empty($events) && empty($days) && empty($churches)) {
            return;
        }
        $onchange = 'vaysfSaveScheduleFilterPrefs(this.form); this.form.submit();';
        ?>
        <form method="get" class="vaysf-live-schedule-filters">
            <?php if (!empty($events)) : ?>
                <select name="vaysf_event" onchange="<?php echo esc_attr($onchange); ?>">
                    <option value=""><?php echo esc_html__('All Sports', 'vaysf'); ?></option>
                    <?php foreach ($events as $evt) : ?>
                        <option value="<?php echo esc_attr($evt); ?>" <?php selected($event, $evt); ?>><?php echo esc_html($evt); ?></option>
                    <?php endforeach; ?>
                </select>
            <?php endif; ?>
            <?php if (!empty($days)) : ?>
                <select name="vaysf_day" onchange="<?php echo esc_attr($onchange); ?>">
                    <option value=""><?php echo esc_html__('All Days', 'vaysf'); ?></option>
                    <?php foreach ($days as $d) : ?>
                        <?php $day_at = vaysf_parse_sports_fest_datetime($d . ' 00:00:00'); ?>
                        <option value="<?php echo esc_attr($d); ?>" <?php selected($day, $d); ?>><?php echo esc_html($day_at ? vaysf_format_sports_fest_time($day_at, 'D, M j') : $d); ?></option>
                    <?php endforeach; ?>
                </select>
            <?php endif; ?>
            <?php if (!empty($churches)) : ?>
                <select name="vaysf_church" onchange="<?php echo esc_attr($onchange); ?>">
                    <option value=""><?php echo esc_html__('All Churches', 'vaysf'); ?></option>
                    <?php foreach ($churches as $code) : ?>
                        <option value="<?php echo esc_attr($code); ?>" <?php selected($church, $code); ?>><?php echo esc_html($code); ?></option>
                    <?php endforeach; ?>
                </select>
            <?php endif; ?>
            <label class="vaysf-live-schedule-upcoming-toggle">
                <input type="checkbox" name="vaysf_upcoming" value="1" <?php checked($upcoming_only); ?> onchange="<?php echo esc_attr($onchange); ?>">
                <?php echo esc_html__('Upcoming games only', 'vaysf'); ?>
            </label>
            <noscript><button type="submit"><?php echo esc_html__('Filter', 'vaysf'); ?></button></noscript>
        </form>
        <?php
        $this->render_public_filter_cookie_script();
    }

    /**
     * Echo the shared cookie-persistence script for the public filter form.
     *
     * Stores the visitor's sport/day/church/upcoming-only selections in a
     * first-party `vaysf_schedule_prefs` cookie (JSON, 30-day expiry,
     * SameSite=Lax). On a page load with no `vaysf_*` query args, it restores
     * the last saved selections by redirecting to the same URL with those
     * values appended — the server then renders the filtered view exactly as
     * it would for a visitor who picked those filters directly, so no
     * duplicate client-side rendering logic is needed. The cookie carries only
     * filter selections, never participant data, scores, or identifiers.
     *
     * Safe to emit once per page even with multiple `[vaysf_live_schedule]`
     * instances: the global-function guard skips re-registering, and the
     * restore check is idempotent (it no-ops once the URL carries filter args).
     */
    private function render_public_filter_cookie_script() {
        ?>
        <script>
        (function () {
            if (window.vaysfSaveScheduleFilterPrefs) { return; }

            var COOKIE_NAME = 'vaysf_schedule_prefs';
            var COOKIE_MAX_AGE = 60 * 60 * 24 * 30; // 30 days
            var FIELDS = ['vaysf_event', 'vaysf_day', 'vaysf_church', 'vaysf_upcoming'];

            function readCookie(name) {
                var match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
                return match ? decodeURIComponent(match[1]) : null;
            }

            function writeCookie(name, value) {
                document.cookie = name + '=' + encodeURIComponent(value) + '; max-age=' + COOKIE_MAX_AGE + '; path=/; SameSite=Lax';
            }

            window.vaysfSaveScheduleFilterPrefs = function (form) {
                var prefs = {};
                FIELDS.forEach(function (key) {
                    var field = form.elements[key];
                    if (!field) { return; }
                    if (field.type === 'checkbox') {
                        if (field.checked) { prefs[key] = '1'; }
                    } else if (field.value) {
                        prefs[key] = field.value;
                    }
                });
                writeCookie(COOKIE_NAME, JSON.stringify(prefs));
            };

            var params = new URLSearchParams(window.location.search);
            var hasFilterParams = FIELDS.some(function (key) { return params.has(key); });
            if (hasFilterParams) { return; }

            var raw = readCookie(COOKIE_NAME);
            if (!raw) { return; }

            var prefs;
            try {
                prefs = JSON.parse(raw);
            } catch (e) {
                return;
            }
            if (!prefs || typeof prefs !== 'object') { return; }

            var url = new URL(window.location.href);
            var changed = false;
            FIELDS.forEach(function (key) {
                if (prefs[key]) {
                    url.searchParams.set(key, prefs[key]);
                    changed = true;
                }
            });
            if (changed) {
                window.location.replace(url.toString());
            }
        })();
        </script>
        <?php
    }

    /**
     * Render one live-schedule table row.
     *
     * @param array<string,mixed> $row Public schedule row from vaysf_get_public_schedule_rows()
     */
    private function render_live_schedule_row($row) {
        $matchup = $this->format_matchup_label($row);
        $status = $row['public_status'] !== '' ? $row['public_status'] : $row['game_status'];
        ?>
        <tr data-game-key="<?php echo esc_attr($row['game_key']); ?>">
            <td class="vaysf-live-time"><?php echo esc_html($this->format_scheduled_time($row)); ?></td>
            <td><?php echo esc_html($row['event']); ?><?php if ($row['stage'] !== '') : ?><br><small><?php echo esc_html($row['stage']); ?></small><?php endif; ?></td>
            <td><?php echo esc_html($matchup); ?></td>
            <td><?php echo esc_html($row['scheduled_location']); ?></td>
            <td class="vaysf-live-status vaysf-status-<?php echo esc_attr(sanitize_html_class($status)); ?>"><?php echo esc_html(ucwords(str_replace('_', ' ', $status))); ?></td>
            <td class="vaysf-live-score"><?php echo esc_html($this->format_score_label($row['score'])); ?></td>
        </tr>
        <?php
    }

    /**
     * Render one advancement table row.
     *
     * @param array<string,mixed> $row Public advancement row from vaysf_get_public_advancement_rows()
     */
    private function render_advancement_row($row) {
        ?>
        <tr data-game-key="<?php echo esc_attr($row['game_key']); ?>">
            <td data-label="<?php echo esc_attr__('Event', 'vaysf'); ?>"><?php echo esc_html($row['event']); ?></td>
            <td data-label="<?php echo esc_attr__('Stage', 'vaysf'); ?>"><span class="vaysf-advancement-stage"><?php echo esc_html($row['stage']); ?></span></td>
            <td data-label="<?php echo esc_attr__('Matchup', 'vaysf'); ?>" class="vaysf-advancement-matchup"><?php echo esc_html($this->format_matchup_label($row)); ?></td>
            <td data-label="<?php echo esc_attr__('Time', 'vaysf'); ?>" class="vaysf-advancement-time"><?php echo esc_html($this->format_scheduled_time($row)); ?></td>
            <td data-label="<?php echo esc_attr__('Location', 'vaysf'); ?>"><?php echo esc_html($row['scheduled_location']); ?></td>
        </tr>
        <?php
    }

    /**
     * Build a human-readable "A vs B(vs C)" matchup label, using placeholders
     * for slots not yet filled in (e.g. an unconfirmed semifinal opponent).
     *
     * @param array<string,mixed> $row Row with team_a_label/team_b_label/team_c_label
     * @return string Matchup label
     */
    private function format_matchup_label($row) {
        $labels = array();
        foreach (array('team_a_label', 'team_b_label', 'team_c_label') as $key) {
            if (!empty($row[$key])) {
                $labels[] = $row[$key];
            }
        }

        if (empty($labels)) {
            return __('TBD', 'vaysf');
        }

        return implode(' vs ', $labels);
    }

    /**
     * Format a schedule row time for spectator display in the site's timezone.
     *
     * @param array<string,mixed>|string $row Public schedule row, or a legacy datetime string
     * @return string Formatted time, or a TBD placeholder when absent
     */
    private function format_scheduled_time($row) {
        if (is_array($row)) {
            return vaysf_format_schedule_display_time($row['scheduled_time'] ?? '', $row['scheduled_slot'] ?? '', 'D g:i A');
        }

        return vaysf_format_schedule_display_time($row, '', 'D g:i A');
    }

    /**
     * Format a public score summary as "A - B(- C)", or a dash before any result exists.
     *
     * @param array<string,mixed>|null $score Score summary from vaysf_format_public_score_summary()
     * @return string Display string
     */
    private function format_score_label($score) {
        if (!is_array($score)) {
            return '—';
        }

        if (!empty($score['label'])) {
            return (string) $score['label'];
        }

        if (($score['type'] ?? '') === 'placement') {
            if (!empty($score['placements']) && is_array($score['placements'])) {
                $labels = array();
                foreach ($score['placements'] as $placement) {
                    if (empty($placement['place']) || empty($placement['church_code'])) {
                        continue;
                    }
                    $labels[] = $placement['place'] . ' ' . $placement['church_code'];
                }
                if ($labels) {
                    return implode(' / ', $labels);
                }
            }

            return '—';
        }

        $parts = array();
        foreach (array('team_a_score', 'team_b_score', 'team_c_score') as $key) {
            if (isset($score[$key]) && $score[$key] !== null) {
                $parts[] = (string) $score[$key];
            }
        }

        if (empty($parts)) {
            return '—';
        }

        return implode(' - ', $parts);
    }

    /**
     * Jump query-routed public scoreboard visits straight to the live schedule.
     *
     * @param string $instance_id DOM id of the shortcode's wrapper element
     */
    private function render_live_schedule_autoscroll_script($instance_id) {
        ?>
        <script>
        (function () {
            var root = document.getElementById(<?php echo wp_json_encode($instance_id); ?>);
            if (!root || window.location.hash) { return; }

            function scrollToSchedule() {
                root.scrollIntoView({ block: 'start' });
            }

            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', scrollToSchedule, { once: true });
            } else {
                window.setTimeout(scrollToSchedule, 0);
            }
        })();
        </script>
        <?php
    }

    /**
     * Echo the auto-refresh script for one live-schedule shortcode instance.
     *
     * Reconciles all visible rows after each poll, so rolling windows can
     * add newly eligible games and remove expired ones without a page reload.
     *
     * @param string $instance_id DOM id of the shortcode's wrapper element
     * @param array<string,mixed> $filters Public schedule filter values
     * @param int $refresh_seconds Poll interval in seconds
     */
    private function render_live_schedule_script($instance_id, $filters, $refresh_seconds) {
        $endpoint = rest_url(VAYSF_REST_API::API_NAMESPACE . '/public/schedule');
        ?>
        <script>
        (function () {
            var root = document.getElementById(<?php echo wp_json_encode($instance_id); ?>);
            if (!root) { return; }
            var endpoint = <?php echo wp_json_encode($endpoint); ?>;
            var filters = <?php echo wp_json_encode($filters); ?>;
            var refreshMs = <?php echo (int) $refresh_seconds; ?> * 1000;
            var sportsFestTimeZone = <?php echo wp_json_encode(VAYSF_SPORTS_FEST_TIMEZONE); ?>;

            function buildUrl() {
                var url = new URL(endpoint);
                Object.keys(filters).forEach(function (key) {
                    if (filters[key] !== '' && filters[key] !== null && typeof filters[key] !== 'undefined') {
                        url.searchParams.set(key, filters[key]);
                    }
                });
                return url.toString();
            }

            function formatScore(score) {
                if (!score) { return String.fromCharCode(8212); }
                if (score.label) { return score.label; }
                if (score.type === 'placement') {
                    if (Array.isArray(score.placements) && score.placements.length) {
                        return score.placements.map(function (placement) {
                            return String(placement.place || '') + ' ' + String(placement.church_code || '');
                        }).join(' / ');
                    }
                    return String.fromCharCode(8212);
                }
                var parts = [score.team_a_score, score.team_b_score];
                if (typeof score.team_c_score !== 'undefined' && score.team_c_score !== null) {
                    parts.push(score.team_c_score);
                }
                parts = parts.filter(function (part) {
                    return typeof part !== 'undefined' && part !== null;
                });
                return parts.length ? parts.join(' - ') : String.fromCharCode(8212);
            }

            function titleCase(text) {
                return String(text || '').replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
            }

            function statusClass(status) {
                return String(status || 'scheduled').replace(/[^a-z0-9_-]/gi, '-');
            }

            function sportsFestClockLabel() {
                try {
                    return new Date().toLocaleTimeString([], {
                        hour: 'numeric',
                        minute: '2-digit',
                        second: '2-digit',
                        timeZone: sportsFestTimeZone
                    });
                } catch (e) {
                    return new Date().toLocaleTimeString();
                }
            }

            function matchupLabel(row) {
                var labels = [row.team_a_label, row.team_b_label, row.team_c_label].filter(function (label) {
                    return !!label;
                });
                return labels.length ? labels.join(' vs ') : 'TBD';
            }

            function cell(className, text) {
                var td = document.createElement('td');
                if (className) { td.className = className; }
                td.textContent = text;
                return td;
            }

            function buildRow(row) {
                var tr = document.createElement('tr');
                tr.setAttribute('data-game-key', String(row.game_key || ''));
                tr.appendChild(cell('vaysf-live-time', row.display_time || 'TBD'));

                var eventCell = cell('', row.event || '');
                if (row.stage) {
                    eventCell.appendChild(document.createElement('br'));
                    var stage = document.createElement('small');
                    stage.textContent = row.stage;
                    eventCell.appendChild(stage);
                }
                tr.appendChild(eventCell);
                tr.appendChild(cell('', matchupLabel(row)));
                tr.appendChild(cell('', row.scheduled_location || ''));
                var status = row.public_status || row.game_status || 'scheduled';
                tr.appendChild(cell('vaysf-live-status vaysf-status-' + statusClass(status), titleCase(status)));
                tr.appendChild(cell('vaysf-live-score', formatScore(row.score)));
                return tr;
            }

            function reconcileRows(rows) {
                var table = root.querySelector('.vaysf-live-schedule-table');
                var body = table ? table.querySelector('tbody') : null;
                var empty = root.querySelector('.vaysf-live-schedule-empty');
                if (!table || !body || !empty) { return; }

                while (body.firstChild) { body.removeChild(body.firstChild); }
                rows.forEach(function (row) { body.appendChild(buildRow(row)); });
                table.hidden = rows.length === 0;
                empty.hidden = rows.length > 0;
            }

            function refresh() {
                fetch(buildUrl(), { credentials: 'omit' })
                    .then(function (r) { return r.json(); })
                    .then(function (rows) {
                        if (!Array.isArray(rows)) { return; }
                        reconcileRows(rows);
                        var updated = root.querySelector('.vaysf-last-updated');
                        if (updated) {
                            updated.textContent = sportsFestClockLabel();
                        }
                    })
                    .catch(function () {});
            }

            setInterval(refresh, refreshMs);
        })();
        </script>
        <?php
    }

    /**
     * Echo the auto-refresh script for one advancement shortcode instance.
     *
     * Reconciles the row set in-place so newly confirmed semifinal/final rows
     * appear without requiring a full page reload.
     *
     * @param string $instance_id DOM id of the shortcode's wrapper element
     * @param array<string,string> $filters event filter value
     * @param int $refresh_seconds Poll interval in seconds
     */
    private function render_advancement_script($instance_id, $filters, $refresh_seconds) {
        $endpoint = rest_url(VAYSF_REST_API::API_NAMESPACE . '/public/advancement');
        ?>
        <script>
        (function () {
            var root = document.getElementById(<?php echo wp_json_encode($instance_id); ?>);
            if (!root) { return; }
            var endpoint = <?php echo wp_json_encode($endpoint); ?>;
            var filters = <?php echo wp_json_encode($filters); ?>;
            var refreshMs = <?php echo (int) $refresh_seconds; ?> * 1000;

            function buildUrl() {
                var url = new URL(endpoint);
                Object.keys(filters).forEach(function (key) {
                    if (filters[key]) { url.searchParams.set(key, filters[key]); }
                });
                return url.toString();
            }

            function matchupLabel(row) {
                var labels = [row.team_a_label, row.team_b_label, row.team_c_label].filter(function (label) {
                    return !!label;
                });
                return labels.length ? labels.join(' vs ') : 'TBD';
            }

            function cell(label, className, text) {
                var td = document.createElement('td');
                td.setAttribute('data-label', label);
                if (className) { td.className = className; }
                td.textContent = text;
                return td;
            }

            function buildRow(row) {
                var tr = document.createElement('tr');
                tr.setAttribute('data-game-key', String(row.game_key || ''));
                tr.appendChild(cell('Event', '', row.event || ''));

                var stageCell = cell('Stage', '', '');
                var stage = document.createElement('span');
                stage.className = 'vaysf-advancement-stage';
                stage.textContent = row.stage || '';
                stageCell.appendChild(stage);
                tr.appendChild(stageCell);

                tr.appendChild(cell('Matchup', 'vaysf-advancement-matchup', matchupLabel(row)));
                tr.appendChild(cell('Time', 'vaysf-advancement-time', row.display_time || 'TBD'));
                tr.appendChild(cell('Location', '', row.scheduled_location || ''));
                return tr;
            }

            function reconcileRows(rows) {
                var table = root.querySelector('.vaysf-advancement-table');
                var body = table ? table.querySelector('tbody') : null;
                var empty = root.querySelector('.vaysf-advancement-empty');
                if (!table || !body || !empty) { return; }

                while (body.firstChild) { body.removeChild(body.firstChild); }
                rows.forEach(function (row) { body.appendChild(buildRow(row)); });
                table.hidden = rows.length === 0;
                empty.hidden = rows.length > 0;
            }

            function refresh() {
                fetch(buildUrl(), { credentials: 'omit', cache: 'no-store' })
                    .then(function (r) { return r.json(); })
                    .then(function (rows) {
                        if (!Array.isArray(rows)) { return; }
                        reconcileRows(rows);
                        var updated = root.querySelector('.vaysf-advancement-last-updated');
                        if (updated) {
                            updated.textContent = new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' });
                        }
                    })
                    .catch(function () {});
            }

            setInterval(refresh, refreshMs);
        })();
        </script>
        <?php
    }

    /**
     * Helper method to get status class
     *
     * @param string $status Approval status
     * @return string CSS class
     */
    private function get_status_class($status) {
        switch ($status) {
            case 'approved':
                return 'status-approved';
            case 'denied':
                return 'status-denied';
            case 'validated':
                return 'status-validated';
            case 'pending_approval':
                return 'status-pending-approval';
            default:
                return 'status-pending';
        }
    }
    
    /**
     * Helper method to render a stat box
     * 
     * @param string $label Stat label
     * @param int $value Stat value
     * @param string $icon Icon identifier
     */
    private function render_stat_box($label, $value, $icon = 'info') {
        echo '<div class="vaysf-stat-box">';
        echo '<div class="vaysf-stat-icon vaysf-icon-' . esc_attr($icon) . '"></div>';
        echo '<div class="vaysf-stat-content">';
        echo '<h3>' . esc_html($label) . '</h3>';
        echo '<div class="vaysf-stat-number">' . esc_html($value) . '</div>';
        echo '</div>';
        echo '</div>';
    }

    /**
     * Convert common shortcode truthy values to a boolean.
     *
     * @param string $value Shortcode value
     * @return bool
     */
    private function is_truthy($value) {
        return in_array(strtolower((string) $value), array('1', 'true', 'yes', 'on'), true);
    }

    /**
     * Resolve the badge gallery page URL used by the churches shortcode.
     *
     * @param string $url Shortcode badges_page_url attribute
     * @return string Base URL for church badge gallery links
     */
    private function resolve_badges_page_url($url) {
        $url = trim((string) $url);
        if ($url === '') {
            return home_url('/badges/');
        }

        return esc_url_raw($url);
    }

    /**
     * Build a church-specific badge gallery URL.
     *
     * @param string $base_url Base badge gallery page URL
     * @param string $church_code Church code
     * @return string URL with church_code query parameter
     */
    private function build_church_badges_url($base_url, $church_code) {
        $church_code = strtoupper(trim((string) $church_code));
        if (!preg_match('/^[A-Z0-9]{3}$/', $church_code)) {
            return $base_url;
        }

        return add_query_arg('church_code', $church_code, $base_url);
    }

    /**
     * Resolve a badge gallery church code from the shortcode or query string.
     *
     * @param string $attr_code Shortcode church_code attribute
     * @return string Uppercase 3-character church code, or empty string
     */
    private function resolve_badges_church_code($attr_code) {
        $code = trim((string) $attr_code);
        if ($code === '' && isset($_GET['church_code'])) {
            $code = sanitize_text_field(wp_unslash($_GET['church_code']));
        }

        $code = strtoupper(trim($code));
        return preg_match('/^[A-Z0-9]{3}$/', $code) ? $code : '';
    }

    /**
     * Fetch one church row for the badge gallery.
     *
     * @param string $church_code Church code
     * @return array|null Church row
     */
    private function get_badges_church($church_code) {
        global $wpdb;

        return $wpdb->get_row(
            $wpdb->prepare(
                "SELECT church_code, church_name FROM {$wpdb->prefix}sf_churches WHERE church_code = %s",
                $church_code
            ),
            ARRAY_A
        );
    }

    /**
     * Fetch approved participants for one church.
     *
     * @param string $church_code Church code
     * @return array Participant rows
     */
    private function get_badges_participants($church_code) {
        global $wpdb;

        return $wpdb->get_results(
            $wpdb->prepare(
                "SELECT participant_id, chmeetings_id, church_code, first_name, last_name, primary_sport
                FROM {$wpdb->prefix}sf_participants
                WHERE church_code = %s AND approval_status = %s
                ORDER BY last_name ASC, first_name ASC, participant_id ASC",
                $church_code,
                'approved'
            ),
            ARRAY_A
        );
    }

    /**
     * Resolve the hosted badge URL for one approved participant.
     *
     * @param array $participant Participant row
     * @return string Hosted badge URL, or empty string
     */
    private function find_badge_url_for_participant($participant) {
        if (!function_exists('vaysf_badge_upload_target')) {
            return '';
        }

        $chmeetings_id = (string) ($participant['chmeetings_id'] ?? '');
        $church_code = (string) ($participant['church_code'] ?? '');
        if (!preg_match('/^[A-Za-z0-9_.-]+$/', $chmeetings_id) || !preg_match('/^[A-Za-z0-9]{3}$/', $church_code)) {
            return '';
        }

        $target = vaysf_badge_upload_target();
        if (is_wp_error($target)) {
            return '';
        }

        $prefix = strtoupper($church_code) . '_' . $chmeetings_id . '_';
        $matches = glob(trailingslashit($target['dir']) . $prefix . '*.png') ?: array();
        if (empty($matches)) {
            return '';
        }

        usort($matches, function ($a, $b) {
            return filemtime($b) <=> filemtime($a);
        });

        return trailingslashit($target['url']) . rawurlencode(basename($matches[0]));
    }

    /**
     * Church-level stats available to the churches shortcode.
     *
     * @return array Stat definitions keyed by shortcode stat name
     */
    private function get_church_stat_definitions() {
        return array(
            'participants' => array(
                'label' => 'Participants',
            ),
            'approved_participants' => array(
                'label' => 'Approved',
            ),
            'approval_ratio' => array(
                'label' => 'Approval',
            ),
            'consent_ratio' => array(
                'label' => 'Consent',
            ),
        );
    }

    /**
     * Parse the churches shortcode stats attribute.
     *
     * @param string $stats_attr Comma-separated stat keys or "all"
     * @return array Requested stat keys
     */
    private function get_requested_church_stats($stats_attr) {
        $definitions = $this->get_church_stat_definitions();
        $stats_attr = strtolower(trim((string) $stats_attr));

        if ($stats_attr === 'all') {
            return array_keys($definitions);
        }

        $requested = array();
        foreach (array_map('trim', explode(',', $stats_attr)) as $stat_key) {
            if (isset($definitions[$stat_key])) {
                $requested[] = $stat_key;
            }
        }

        return array_values(array_unique($requested));
    }

    /**
     * Render per-church stats under the church name.
     *
     * @param array $church Church row with aggregate stat columns
     * @param array $stat_keys Requested stat keys
     */
    private function render_church_stats($church, $stat_keys) {
        if (empty($stat_keys)) {
            return;
        }

        $definitions = $this->get_church_stat_definitions();

        echo '<div class="vaysf-church-stats">';
        foreach ($stat_keys as $stat_key) {
            if (!isset($definitions[$stat_key])) {
                continue;
            }

            echo '<span class="vaysf-church-stat vaysf-church-stat-' . esc_attr(sanitize_html_class($stat_key)) . '">';
            echo '<span class="vaysf-church-stat-label">' . esc_html($definitions[$stat_key]['label']) . '</span>';
            echo '<span class="vaysf-church-stat-value">' . esc_html($this->format_church_stat_value($church, $stat_key)) . '</span>';
            echo '</span>';
        }
        echo '</div>';
    }

    /**
     * Format a church stat value for display.
     *
     * @param array $church Church row with aggregate stat columns
     * @param string $stat_key Stat key
     * @return string Display value
     */
    private function format_church_stat_value($church, $stat_key) {
        $total = isset($church['total_participants']) ? (int) $church['total_participants'] : 0;
        $approved = isset($church['approved_participants']) ? (int) $church['approved_participants'] : 0;
        $consented = isset($church['consented_participants']) ? (int) $church['consented_participants'] : 0;

        switch ($stat_key) {
            case 'participants':
                return number_format_i18n($total);
            case 'approved_participants':
                return number_format_i18n($approved);
            case 'approval_ratio':
                $percentage = $total > 0 ? round(($approved / $total) * 100, 1) : 0;
                return sprintf(
                    '%s/%s (%s%%)',
                    number_format_i18n($approved),
                    number_format_i18n($total),
                    number_format_i18n($percentage)
                );
            case 'consent_ratio':
                $percentage = $total > 0 ? round(($consented / $total) * 100, 1) : 0;
                return sprintf(
                    '%s/%s (%s%%)',
                    number_format_i18n($consented),
                    number_format_i18n($total),
                    number_format_i18n($percentage)
                );
            default:
                return '';
        }
    }
    
    /**
     * Include frontend styles
     */
    private function include_frontend_styles() {
        static $styles_included = false;
        
        if (!$styles_included) {
            echo '<style>
                .vaysf-stats-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                    gap: 20px;
                    margin: 20px 0;
                }
                
                .vaysf-stats-list .vaysf-stat-box {
                    margin-bottom: 15px;
                }
                
                .vaysf-stat-box {
                    background: #fff;
                    border: 1px solid #ddd;
                    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
                    padding: 15px;
                    border-radius: 4px;
                    display: flex;
                    align-items: center;
                }
                
                .vaysf-stat-icon {
                    font-size: 24px;
                    width: 40px;
                    height: 40px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin-right: 15px;
                    border-radius: 50%;
                    color: #fff;
                }
                
                .vaysf-icon-church { background-color: #4CAF50; }
                .vaysf-icon-person { background-color: #2196F3; }
                .vaysf-icon-yes { background-color: #8BC34A; }
                .vaysf-icon-no { background-color: #F44336; }
                .vaysf-icon-clock { background-color: #FF9800; }
                .vaysf-icon-warning { background-color: #FF5722; }
                .vaysf-icon-info { background-color: #9C27B0; }
                
                .vaysf-stat-content {
                    flex: 1;
                }
                
                .vaysf-stat-content h3 {
                    margin: 0 0 5px 0;
                    font-size: 16px;
                }
                
                .vaysf-stat-number {
                    font-size: 24px;
                    font-weight: bold;
                }
                
                .vaysf-churches-table,
                .vaysf-participants-table {
                    width: 100%;
                    border-collapse: collapse;
                    margin: 20px 0;
                }
                
                .vaysf-churches-table th,
                .vaysf-churches-table td,
                .vaysf-participants-table th,
                .vaysf-participants-table td {
                    padding: 10px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                }
                
                .vaysf-churches-table th,
                .vaysf-participants-table th {
                    background-color: #f5f5f5;
                    font-weight: bold;
                }

                .vaysf-church-name {
                    margin-bottom: 6px;
                }

                .vaysf-church-stats {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 6px;
                    margin-top: 4px;
                }

                .vaysf-church-stat {
                    display: inline-flex;
                    align-items: baseline;
                    gap: 4px;
                    padding: 3px 7px;
                    border: 1px solid #d7e3f0;
                    border-radius: 3px;
                    background-color: #f8fbff;
                    color: #34495e;
                    font-size: 12px;
                    line-height: 1.4;
                    white-space: nowrap;
                }

                .vaysf-church-stat-label {
                    color: #667085;
                }

                .vaysf-church-stat-value {
                    font-weight: 700;
                }

                .vaysf-participants-button {
                    display: inline-block;
                    padding: 6px 10px;
                    border: 1px solid #1d4ed8;
                    border-radius: 3px;
                    background: #2563eb;
                    color: #fff;
                    font-size: 13px;
                    font-weight: 700;
                    line-height: 1.2;
                    text-decoration: none;
                }

                .vaysf-participants-button:hover,
                .vaysf-participants-button:focus {
                    background: #1d4ed8;
                    color: #fff;
                    text-decoration: none;
                }
                
                .approval-status {
                    display: inline-block;
                    padding: 3px 8px;
                    border-radius: 3px;
                    font-size: 12px;
                    font-weight: bold;
                }
                
                .status-approved {
                    background-color: #d4edda;
                    color: #155724;
                }
                
                .status-denied {
                    background-color: #f8d7da;
                    color: #721c24;
                }
                
                .status-validated {
                    background-color: #cce5ff;
                    color: #004085;
                }
                
                .status-pending-approval {
                    background-color: #fff3cd;
                    color: #856404;
                }
                
                .status-pending {
                    background-color: #e2e3e5;
                    color: #383d41;
                }

                .vaysf-live-schedule-filters {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 8px;
                    margin-bottom: 15px;
                }

                .vaysf-live-schedule-filters select,
                .vaysf-live-schedule-filters button {
                    padding: 6px 10px;
                }

                .vaysf-live-schedule-upcoming-toggle {
                    display: inline-flex;
                    align-items: center;
                    gap: 6px;
                    padding: 6px 4px;
                    font-size: 14px;
                }

                .vaysf-scoreboard-anchor,
                .vaysf-live-schedule,
                .vaysf-advancement {
                    scroll-margin-top: 85px;
                }

                .vaysf-advancement {
                    margin: 28px 0;
                }

                .vaysf-advancement-heading {
                    display: flex;
                    align-items: flex-end;
                    justify-content: space-between;
                    gap: 16px;
                    margin-bottom: 12px;
                    border-bottom: 2px solid #1b4f72;
                    padding-bottom: 10px;
                }

                .vaysf-advancement-heading h2 {
                    margin: 0;
                    color: #1b4f72;
                    font-size: 24px;
                    line-height: 1.2;
                }

                .vaysf-advancement-heading p {
                    max-width: 520px;
                    margin: 0;
                    color: #667085;
                    font-size: 14px;
                    line-height: 1.4;
                    text-align: right;
                }

                .vaysf-live-schedule-table,
                .vaysf-advancement-table {
                    width: 100%;
                    border-collapse: collapse;
                    margin: 10px 0 20px;
                }

                .vaysf-live-schedule-table th,
                .vaysf-live-schedule-table td,
                .vaysf-advancement-table th,
                .vaysf-advancement-table td {
                    padding: 10px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                }

                .vaysf-live-schedule-table th,
                .vaysf-advancement-table th {
                    background-color: #f5f5f5;
                    font-weight: bold;
                }

                .vaysf-advancement-table {
                    border: 1px solid #d7e3f0;
                    background: #fff;
                }

                .vaysf-advancement-table th {
                    background-color: #edf5fb;
                    color: #1b4f72;
                    font-size: 13px;
                    text-transform: uppercase;
                }

                .vaysf-advancement-table td {
                    vertical-align: top;
                }

                .vaysf-advancement-table tbody tr:nth-child(even) {
                    background-color: #f8fbff;
                }

                .vaysf-advancement-stage {
                    display: inline-block;
                    min-width: 76px;
                    border: 1px solid #b8d8ec;
                    background: #edf5fb;
                    color: #1b4f72;
                    padding: 3px 8px;
                    text-align: center;
                    font-size: 12px;
                    font-weight: 700;
                    line-height: 1.25;
                }

                .vaysf-advancement-matchup {
                    font-weight: 700;
                    color: #243b53;
                }

                .vaysf-advancement-time {
                    white-space: nowrap;
                    font-weight: 700;
                }

                .vaysf-live-schedule-updated {
                    font-size: 12px;
                    color: #667085;
                }

                .vaysf-advancement-updated {
                    margin-top: -8px;
                    font-size: 12px;
                    color: #667085;
                }

                .vaysf-advancement-empty {
                    margin: 10px 0 20px;
                    border: 1px solid #d7e3f0;
                    background: #f8fbff;
                    padding: 14px;
                    color: #34495e;
                }

                .vaysf-live-status {
                    display: inline-block;
                    padding: 3px 8px;
                    border-radius: 3px;
                    font-size: 12px;
                    font-weight: bold;
                }

                .vaysf-status-scheduled,
                .vaysf-status-in_progress {
                    background-color: #e2e3e5;
                    color: #383d41;
                }

                .vaysf-status-reported {
                    background-color: #fff3cd;
                    color: #856404;
                }

                .vaysf-status-official {
                    background-color: #d4edda;
                    color: #155724;
                }

                .vaysf-status-under_review {
                    background-color: #f8d7da;
                    color: #721c24;
                }

                .vaysf-live-score {
                    font-weight: bold;
                }

                .vaysf-badges {
                    margin: 20px 0;
                }

                .vaysf-badges-heading {
                    display: flex;
                    align-items: baseline;
                    justify-content: space-between;
                    gap: 12px;
                    margin-bottom: 16px;
                    border-bottom: 1px solid #ddd;
                    padding-bottom: 10px;
                }

                .vaysf-badges-heading h2 {
                    margin: 0;
                    font-size: 22px;
                }

                .vaysf-badges-heading p,
                .vaysf-badges-note {
                    margin: 0;
                    color: #667085;
                    font-size: 13px;
                }

                .vaysf-badges-grid {
                    display: grid;
                    grid-template-columns: repeat(var(--vaysf-badge-columns, 4), minmax(0, 1fr));
                    gap: 18px;
                }

                .vaysf-badge-card {
                    margin: 0;
                    break-inside: avoid;
                }

                .vaysf-badge-card a {
                    display: block;
                    border: 1px solid #d7e3f0;
                    background: #f8fbff;
                    padding: 8px;
                }

                .vaysf-badge-card img {
                    display: block;
                    width: 100%;
                    height: auto;
                    aspect-ratio: 9 / 16;
                    object-fit: contain;
                    background: #fff;
                }

                .vaysf-badge-card figcaption {
                    margin-top: 8px;
                    display: flex;
                    flex-direction: column;
                    gap: 2px;
                    font-size: 13px;
                    line-height: 1.35;
                }

                .vaysf-badge-name {
                    font-weight: 700;
                    color: #34495e;
                }

                .vaysf-badge-meta {
                    color: #667085;
                }

                .vaysf-badges-empty {
                    padding: 14px;
                    border: 1px solid #d7e3f0;
                    background: #f8fbff;
                    color: #34495e;
                }

                .vaysf-badges-note {
                    margin-top: 12px;
                }

                @media (max-width: 768px) {
                    .vaysf-stats-grid {
                        grid-template-columns: 1fr;
                    }

                    .vaysf-churches-table,
                    .vaysf-participants-table,
                    .vaysf-live-schedule-table,
                    .vaysf-advancement-table {
                        display: block;
                        overflow-x: auto;
                    }

                    .vaysf-badges-heading {
                        display: block;
                    }

                    .vaysf-advancement-heading {
                        display: block;
                    }

                    .vaysf-advancement-heading p {
                        margin-top: 6px;
                        text-align: left;
                    }

                    .vaysf-advancement-table {
                        border: 0;
                    }

                    .vaysf-advancement-table thead {
                        display: none;
                    }

                    .vaysf-advancement-table tbody,
                    .vaysf-advancement-table tr,
                    .vaysf-advancement-table td {
                        display: block;
                        width: 100%;
                    }

                    .vaysf-advancement-table tr {
                        margin-bottom: 12px;
                        border: 1px solid #d7e3f0;
                        background: #fff;
                    }

                    .vaysf-advancement-table td {
                        display: grid;
                        grid-template-columns: 92px minmax(0, 1fr);
                        gap: 10px;
                        border-bottom: 1px solid #edf2f7;
                    }

                    .vaysf-advancement-table td::before {
                        content: attr(data-label);
                        color: #667085;
                        font-size: 12px;
                        font-weight: 700;
                        text-transform: uppercase;
                    }

                    .vaysf-advancement-table td:last-child {
                        border-bottom: 0;
                    }

                    .vaysf-badges-heading p {
                        margin-top: 4px;
                    }

                    .vaysf-badges-grid {
                        grid-template-columns: repeat(2, minmax(0, 1fr));
                    }
                }

                @media print {
                    .vaysf-badges-grid {
                        grid-template-columns: repeat(3, minmax(0, 1fr));
                    }

                    .vaysf-badge-card a {
                        border-color: #999;
                    }
                }
            </style>';
            
            // FontAwesome icons could be included here or use WordPress dashicons
            // For now we'll use a simple placeholder for icons
            
            $styles_included = true;
        }
    }
}

// Initialize shortcodes
new VAYSF_Shortcodes();

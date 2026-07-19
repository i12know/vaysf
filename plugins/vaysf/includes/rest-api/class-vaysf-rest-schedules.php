<?php
/**
 * File: includes/rest-api/class-vaysf-rest-schedules.php
 * Description: Schedule REST endpoints - reads by filter/game_key and the
 *              publish-schedule bulk upsert (Issue #203)
 * Author: Bumble Ho
 */

// Exit if accessed directly
if (!defined('ABSPATH')) {
    exit;
}

class VAYSF_REST_Schedules extends VAYSF_REST_Controller {

    /**
     * Register REST API routes
     */
    public function register_routes() {
		// Schedules endpoints (Issue #203)
		register_rest_route(self::API_NAMESPACE, '/schedules', array(
			array(
				'methods' => WP_REST_Server::READABLE,
				'callback' => array($this, 'get_schedules'),
				'permission_callback' => array($this, 'check_api_permission'),
			),
		));

		register_rest_route(self::API_NAMESPACE, '/schedules/upsert', array(
			array(
				'methods' => WP_REST_Server::CREATABLE,
				'callback' => array($this, 'upsert_schedules'),
				'permission_callback' => array($this, 'check_api_permission'),
			),
		));

		register_rest_route(self::API_NAMESPACE, '/schedules/(?P<game_key>[A-Za-z0-9_-]+)', array(
			array(
				'methods' => WP_REST_Server::READABLE,
				'callback' => array($this, 'get_schedule_by_key'),
				'permission_callback' => array($this, 'check_api_permission'),
			),
		));
    }

    /**
     * Get the currently published schedule (Issue #203)
     *
     * @param WP_REST_Request $request Request object
     * @return WP_REST_Response Response object
     */
    public function get_schedules($request) {
        global $wpdb;

        $table_schedules = vaysf_get_table_name('schedules');
        $params = $request->get_params();

        $where = array();
        $where_format = array();

        if (!empty($params['game_status'])) {
            $where[] = 'game_status = %s';
            $where_format[] = sanitize_text_field($params['game_status']);
        }
        if (!empty($params['event'])) {
            $where[] = 'event = %s';
            $where_format[] = sanitize_text_field($params['event']);
        }

        $where_clause = !empty($where) ? 'WHERE ' . implode(' AND ', $where) : '';
        $query_sql = "SELECT * FROM $table_schedules $where_clause ORDER BY schedule_id";
        $query = !empty($where_format) ? $wpdb->prepare($query_sql, $where_format) : $query_sql;

        $schedules = $wpdb->get_results($query, ARRAY_A);

        return rest_ensure_response($schedules);
    }

    /**
     * Get a single schedule row by its stable game_key (Issue #203)
     *
     * @param WP_REST_Request $request Request object
     * @return WP_REST_Response|WP_Error Response object or error
     */
    public function get_schedule_by_key($request) {
        global $wpdb;

        $table_schedules = vaysf_get_table_name('schedules');
        $game_key = sanitize_text_field($request['game_key']);

        $schedule = $wpdb->get_row(
            $wpdb->prepare("SELECT * FROM $table_schedules WHERE game_key = %s", $game_key),
            ARRAY_A
        );

        if (!$schedule) {
            return new WP_Error(
                'rest_schedule_not_found',
                esc_html__('Schedule not found.', 'vaysf'),
                array('status' => 404)
            );
        }

        return rest_ensure_response($schedule);
    }
    /**
     * Bulk create/update sf_schedules rows by stable game_key (Issue #203).
     *
     * Refuses to touch rows whose current game_status is "protected" (reported,
     * official, under_review) regardless of what the payload requests — this is
     * a second line of defense against a stale middleware diff, in addition to
     * the diff itself never including such rows in the payload. Cancellation
     * (game_status = "cancelled") additionally requires force_cancel = true at
     * the request level.
     *
     * @param WP_REST_Request $request Request object
     * @return WP_REST_Response|WP_Error Response object or error
     */
    public function upsert_schedules($request) {
        global $wpdb;

        $table_schedules = vaysf_get_table_name('schedules');
        $params = $request->get_params();

        if (empty($params['games']) || !is_array($params['games'])) {
            return new WP_Error(
                'rest_missing_field',
                esc_html__('Missing required field: games', 'vaysf'),
                array('status' => 400)
            );
        }

        $protected_statuses = array('reported', 'official', 'under_review');
        $schedule_version = isset($params['schedule_version']) ? absint($params['schedule_version']) : 0;
        $force_cancel = !empty($params['force_cancel']);

        $created_count = 0;
        $updated_count = 0;
        $skipped_count = 0;
        $results = array();

        foreach ($params['games'] as $game) {
            if (empty($game['game_key'])) {
                $skipped_count++;
                $results[] = array(
                    'game_key' => null,
                    'action' => 'skipped_missing_game_key',
                    'message' => esc_html__('Missing required field: game_key', 'vaysf'),
                );
                continue;
            }

            $game_key = sanitize_text_field($game['game_key']);
            $existing = $wpdb->get_row(
                $wpdb->prepare("SELECT * FROM $table_schedules WHERE game_key = %s", $game_key),
                ARRAY_A
            );

            if ($existing && in_array($existing['game_status'], $protected_statuses, true)) {
                $incoming_hash = isset($game['source_hash']) ? sanitize_text_field($game['source_hash']) : '';
                $existing_hash = isset($existing['source_hash']) ? (string) $existing['source_hash'] : '';
                if ($incoming_hash !== '' && $incoming_hash === $existing_hash) {
                    $result = $wpdb->update(
                        $table_schedules,
                        array(
                            'schedule_version' => $schedule_version,
                            'published_at' => current_time('mysql'),
                            'updated_at' => current_time('mysql'),
                        ),
                        array('game_key' => $game_key),
                        array('%d', '%s', '%s'),
                        array('%s')
                    );
                    if (false === $result) {
                        $skipped_count++;
                        $results[] = array(
                            'game_key' => $game_key,
                            'action' => 'error',
                            'message' => esc_html__('Failed to carry forward protected schedule row.', 'vaysf'),
                        );
                        continue;
                    }
                    $updated_count++;
                    $results[] = array(
                        'game_key' => $game_key,
                        'action' => 'carried_forward_protected',
                        'schedule_id' => (int) $existing['schedule_id'],
                    );
                    continue;
                }

                $skipped_count++;
                $results[] = array(
                    'game_key' => $game_key,
                    'action' => 'skipped_completed',
                    'schedule_id' => (int) $existing['schedule_id'],
                );
                continue;
            }

            $incoming_status = isset($game['game_status']) ? sanitize_text_field($game['game_status']) : null;
            if ($incoming_status === 'cancelled' && !$force_cancel) {
                $skipped_count++;
                $results[] = array(
                    'game_key' => $game_key,
                    'action' => 'skipped_not_forced',
                );
                continue;
            }

            $data = array();
            $format = array();

            $text_fields = array(
                'event', 'stage', 'pool_id', 'sub_event',
                'team_a_key', 'team_a_label', 'team_b_key', 'team_b_label',
                'team_c_key', 'team_c_label', 'team_ids_json',
                'team_a_church_code', 'team_b_church_code', 'team_c_church_code',
                'resource_id', 'scheduled_slot', 'scheduled_location',
                'game_status', 'source_hash',
            );
            foreach ($text_fields as $field) {
                if (isset($game[$field])) {
                    $data[$field] = sanitize_text_field($game[$field]);
                    $format[] = '%s';
                }
            }
            if (isset($game['round_number'])) {
                $data['round_number'] = absint($game['round_number']);
                $format[] = '%d';
            }
            if (isset($game['scheduled_time'])) {
                $data['scheduled_time'] = sanitize_text_field($game['scheduled_time']);
                $format[] = '%s';
            }

            $data['schedule_version'] = $schedule_version;
            $format[] = '%d';
            $data['published_at'] = current_time('mysql');
            $format[] = '%s';
            $data['updated_at'] = current_time('mysql');
            $format[] = '%s';

            if ($existing) {
                $result = $wpdb->update(
                    $table_schedules,
                    $data,
                    array('game_key' => $game_key),
                    $format,
                    array('%s')
                );
                if (false === $result) {
                    $skipped_count++;
                    $results[] = array(
                        'game_key' => $game_key,
                        'action' => 'error',
                        'message' => esc_html__('Failed to update schedule row.', 'vaysf'),
                    );
                    continue;
                }
                $updated_count++;
                $results[] = array(
                    'game_key' => $game_key,
                    'action' => 'updated',
                    'schedule_id' => (int) $existing['schedule_id'],
                );
            } else {
                $data['game_key'] = $game_key;
                $format[] = '%s';
                if (!isset($data['game_status'])) {
                    $data['game_status'] = 'scheduled';
                    $format[] = '%s';
                }
                $data['created_at'] = current_time('mysql');
                $format[] = '%s';

                $result = $wpdb->insert($table_schedules, $data, $format);
                if (false === $result) {
                    $skipped_count++;
                    $results[] = array(
                        'game_key' => $game_key,
                        'action' => 'error',
                        'message' => esc_html__('Failed to create schedule row.', 'vaysf'),
                    );
                    continue;
                }
                $created_count++;
                $results[] = array(
                    'game_key' => $game_key,
                    'action' => 'created',
                    'schedule_id' => (int) $wpdb->insert_id,
                );
            }
        }

        return rest_ensure_response(array(
            'success' => ($skipped_count === 0),
            'schedule_version' => $schedule_version,
            'created_count' => $created_count,
            'updated_count' => $updated_count,
            'skipped_count' => $skipped_count,
            'results' => $results,
        ));
    }
}

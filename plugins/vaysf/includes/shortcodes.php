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
        ), $atts);
        
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
            echo '<th>Status</th>';
            echo '</tr></thead>';
            echo '<tbody>';
            
            foreach ($churches as $church) {
                echo '<tr>';
                echo '<td>' . esc_html($church['church_name']) . ' (' . esc_html($church['church_code']) . ')</td>';
                echo '<td>' . esc_html($church['pastor_name']) . '</td>';
                echo '<td>' . esc_html(ucfirst($church['registration_status'])) . '</td>';
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
                
                @media (max-width: 768px) {
                    .vaysf-stats-grid {
                        grid-template-columns: 1fr;
                    }
                    
                    .vaysf-churches-table,
                    .vaysf-participants-table {
                        display: block;
                        overflow-x: auto;
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
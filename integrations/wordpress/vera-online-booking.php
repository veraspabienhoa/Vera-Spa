<?php
/**
 * Plugin Name: Vera Spa Online Booking
 * Description: Durable, signed Contact Form 7 delivery to the Vera Spa inbox.
 * Version: 1.1.0
 */
if (!defined('ABSPATH')) { exit; }

function vera_ob_table() { global $wpdb; return $wpdb->prefix . 'vera_booking_outbox'; }
function vera_ob_install() {
    global $wpdb;
    require_once ABSPATH . 'wp-admin/includes/upgrade.php';
    $table = vera_ob_table();
    $charset = $wpdb->get_charset_collate();
    dbDelta("CREATE TABLE $table (
        id bigint unsigned NOT NULL AUTO_INCREMENT,
        event_id varchar(36) NOT NULL,
        payload longtext NOT NULL,
        attempts int unsigned NOT NULL DEFAULT 0,
        next_attempt datetime NOT NULL,
        last_code varchar(32) NOT NULL DEFAULT '',
        created_at datetime NOT NULL,
        PRIMARY KEY  (id),
        UNIQUE KEY event_id (event_id),
        KEY next_attempt (next_attempt)
    ) $charset;");
    if (!wp_next_scheduled('vera_ob_deliver')) { wp_schedule_event(time() + 10, 'vera_ob_minute', 'vera_ob_deliver'); }
}
add_filter('cron_schedules', function ($schedules) {
    $schedules['vera_ob_minute'] = array('interval' => 60, 'display' => 'Vera booking: every minute');
    return $schedules;
});
register_activation_hook(__FILE__, 'vera_ob_install');
register_deactivation_hook(__FILE__, function () { wp_clear_scheduled_hook('vera_ob_deliver'); wp_clear_scheduled_hook('vera_ob_deliver_soon'); });

function vera_ob_value($posted, $key) {
    $value = isset($posted[$key]) ? $posted[$key] : '';
    if (is_array($value) && count($value) === 1) { $value = reset($value); }
    return is_scalar($value) ? trim(sanitize_textarea_field((string) $value)) : '';
}
function vera_ob_capture($form, &$abort, $submission) {
    // Only these reviewed forms; exclude newsletters, other sites and spam/invalid submissions.
    $id = (int) $form->id();
    if (!in_array($id, array(1271, 606), true)) { return; }
    if ($abort) { return; }
    $posted = $submission->get_posted_data();
    $booking = $id === 1271;
    $day = null;
    if ($booking) {
        $raw_day = vera_ob_value($posted, 'date-175');
        $parsed = DateTimeImmutable::createFromFormat('!d-m-Y', $raw_day, wp_timezone());
        if (!$parsed || $parsed->format('d-m-Y') !== $raw_day) {
            $abort = true;
            $submission->set_response('Ngày hẹn không hợp lệ. Vui lòng kiểm tra lại.');
            return;
        }
        $day = $parsed->format('Y-m-d');
    }
    $payload = array(
        'event_id' => wp_generate_uuid4(),
        'kind' => $booking ? 'booking' : 'contact',
        'customer_name' => vera_ob_value($posted, $booking ? 'your-name' : 'text-410'),
        'phone' => vera_ob_value($posted, $booking ? 'number-721' : 'tel-686'),
        'appointment_date' => $day,
        'appointment_time' => $booking ? vera_ob_value($posted, 'checkbox-444') : null,
        'service' => $booking ? vera_ob_value($posted, 'menu-396') : '',
        'guests' => $booking ? (int) vera_ob_value($posted, 'number-999') : null,
        'message' => vera_ob_value($posted, $booking ? 'booking-message' : 'text-750'),
    );
    $digits = preg_replace('/\D/', '', $payload['phone']);
    $valid = mb_strlen($payload['customer_name']) >= 1 && mb_strlen($payload['customer_name']) <= 100
        && preg_match('/^\+?[0-9 () .-]+$/', $payload['phone']) && strlen($digits) >= 9 && strlen($digits) <= 15
        && strlen($payload['phone']) <= 20 && mb_strlen($payload['message']) <= 4000;
    if ($booking) {
        $valid = $valid && preg_match('/^([01][0-9]|2[0-3]):[0-5][0-9]$/', $payload['appointment_time'])
            && $payload['service'] !== '' && mb_strlen($payload['service']) <= 500
            && $payload['guests'] >= 1 && $payload['guests'] <= 50;
    } else { $valid = $valid && $payload['message'] !== ''; }
    if (!$valid) {
        $abort = true;
        $submission->set_response('Thông tin chưa hợp lệ. Vui lòng kiểm tra tên, số điện thoại và nội dung.');
        return;
    }
    global $wpdb;
    $saved = $wpdb->insert(vera_ob_table(), array(
        'event_id' => $payload['event_id'], 'payload' => wp_json_encode($payload),
        'next_attempt' => gmdate('Y-m-d H:i:s'), 'created_at' => gmdate('Y-m-d H:i:s'),
    ), array('%s', '%s', '%s', '%s'));
    if (!$saved) {
        $abort = true;
        $submission->set_response('Chưa lưu được yêu cầu. Vui lòng thử lại hoặc gọi hotline.');
        return;
    }
    // Queue before returning success. Network delivery occurs after CF7 processing.
    wp_schedule_single_event(time(), 'vera_ob_deliver_soon');
    add_action('shutdown', function () { spawn_cron(); }, 20);
}
add_action('wpcf7_before_send_mail', 'vera_ob_capture', 20, 3);

function vera_ob_deliver() {
    if (!defined('VERA_WEBSITE_WEBHOOK_SECRET') || strlen(VERA_WEBSITE_WEBHOOK_SECRET) < 32) { return; }
    global $wpdb;
    $table = vera_ob_table();
    // Overlapping cron/shutdown attempts are safe: the API deduplicates by event_id.
    $rows = $wpdb->get_results("SELECT * FROM $table WHERE next_attempt <= UTC_TIMESTAMP() ORDER BY id LIMIT 5");
    foreach ($rows as $row) {
        $timestamp = (string) time();
        $signature = hash_hmac('sha256', $timestamp . '.' . $row->payload, VERA_WEBSITE_WEBHOOK_SECRET);
        $response = wp_remote_post('https://api.veraspa.vn/v2/integrations/website/requests', array(
            'timeout' => 5, 'redirection' => 0, 'sslverify' => true,
            'headers' => array('Content-Type' => 'application/json', 'X-Vera-Timestamp' => $timestamp, 'X-Vera-Signature' => $signature),
            'body' => $row->payload,
        ));
        $code = is_wp_error($response) ? 0 : wp_remote_retrieve_response_code($response);
        $result = is_wp_error($response) ? null : json_decode(wp_remote_retrieve_body($response), true);
        if ($code === 200 && is_array($result) && !empty($result['ok']) && !empty($result['id'])) {
            $wpdb->delete($table, array('id' => $row->id), array('%d'));
        } else {
            // Keep failed records indefinitely for recovery; never log names, phones or bodies.
            $attempt = min(100000, (int) $row->attempts + 1);
            $delay = min(3600, 30 * (2 ** min(7, $attempt)));
            $wpdb->update($table, array('attempts' => $attempt, 'next_attempt' => gmdate('Y-m-d H:i:s', time() + $delay), 'last_code' => (string) $code), array('id' => $row->id), array('%d', '%s', '%s'), array('%d'));
        }
    }
}
add_action('vera_ob_deliver', 'vera_ob_deliver');
add_action('vera_ob_deliver_soon', 'vera_ob_deliver');
add_action('admin_notices', function () {
    if (!current_user_can('manage_options')) { return; }
    if (!defined('VERA_WEBSITE_WEBHOOK_SECRET') || strlen(VERA_WEBSITE_WEBHOOK_SECRET) < 32) {
        echo '<div class="notice notice-warning"><p>Vera Booking online: chưa cấu hình khóa kết nối. Yêu cầu chưa được chuyển sang Live Tour.</p></div>';
        return;
    }
    global $wpdb;
    $table = vera_ob_table();
    $pending = (int) $wpdb->get_var("SELECT COUNT(*) FROM $table");
    if ($pending) { echo '<div class="notice notice-warning"><p>Vera Booking online: ' . esc_html((string) $pending) . ' yêu cầu đang chờ gửi. Kiểm tra API, khóa kết nối và WP-Cron nếu số lượng không giảm.</p></div>'; }
});

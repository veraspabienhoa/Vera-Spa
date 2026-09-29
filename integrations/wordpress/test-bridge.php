<?php
// Pure fixture harness: no WordPress DB, HTTP, cron, email or customer records.
define('ABSPATH', __DIR__ . '/');
define('VERA_WEBSITE_WEBHOOK_SECRET', str_repeat('x', 40));
function add_action(...$args) {}
function add_filter(...$args) {}
function register_activation_hook(...$args) {}
function register_deactivation_hook(...$args) {}
function sanitize_textarea_field($v) { return strip_tags($v); }
function wp_timezone() { return new DateTimeZone('Asia/Ho_Chi_Minh'); }
function wp_generate_uuid4() { static $n=0; return sprintf('00000000-0000-4000-8000-%012d', ++$n); }
function wp_json_encode($v) { return json_encode($v); }
function wp_schedule_single_event(...$args) {}
function is_wp_error($v) { return $v === false; }
function wp_remote_post($url, $args) {
    global $code, $last_request;
    $last_request = $args;
    if ($url !== 'https://api.veraspa.vn/v2/integrations/website/requests') { throw new Exception('wrong destination'); }
    return array('code'=>$code);
}
function wp_remote_retrieve_response_code($v) { return $v['code']; }
function wp_remote_retrieve_body($v) { return '{"ok":true,"id":1}'; }
class FakeDB {
    public $prefix='wp_', $rows=array(), $fail=false;
    function insert($table,$data,$format) { if($this->fail) return false; $data['id']=count($this->rows)+1; $data['attempts']=0; $this->rows[$data['id']] = (object)$data; return 1; }
    function get_results($sql) { return array_values($this->rows); }
    function delete($table,$where,$format) { unset($this->rows[$where['id']]); }
    function update($table,$data,$where,...$rest) { foreach($data as $k=>$v) $this->rows[$where['id']]->$k=$v; }
}
class Form { private $id; function __construct($id) {$this->id=$id;} function id(){return $this->id;} }
class Submission { public $data, $response=''; function __construct($data){$this->data=$data;} function get_posted_data(){return $this->data;} function set_response($s){$this->response=$s;} }
function check($ok,$message) { if(!$ok) throw new Exception($message); }
require __DIR__.'/vera-online-booking.php';
$wpdb = new FakeDB();
$raw = array('your-name'=>'Test','number-721'=>'0900000000','date-175'=>'30-09-2026','checkbox-444'=>array('14:30'),'menu-396'=>array('VIP 90 phút'),'number-999'=>'2');
$abort=false;
vera_ob_capture(new Form(1271),$abort,new Submission($raw));
check(!$abort && count($wpdb->rows)===1,'booking must be queued');
$payload=json_decode($wpdb->rows[1]->payload,true);
check($payload['service']==='VIP 90 phút' && $payload['appointment_date']==='2026-09-30' && $payload['guests']===2,'field mapping');
$code=503; vera_ob_deliver();
check(count($wpdb->rows)===1 && $wpdb->rows[1]->attempts===1,'failure retained');
check(hash_equals(hash_hmac('sha256',$last_request['headers']['X-Vera-Timestamp'].'.'.$last_request['body'],VERA_WEBSITE_WEBHOOK_SECRET),$last_request['headers']['X-Vera-Signature']),'signature');
$code=200; vera_ob_deliver(); check(count($wpdb->rows)===0,'ack removes only delivered row');
vera_ob_capture(new Form(606),$abort,new Submission(array('text-410'=>'Test','tel-686'=>'0900000000','text-750'=>'Xin tư vấn')));
$contact=json_decode($wpdb->rows[1]->payload,true);
check($contact['kind']==='contact' && $contact['appointment_date']===null && $contact['message']==='Xin tư vấn','contact mapping');
vera_ob_capture(new Form(465),$abort,new Submission($raw)); check(count($wpdb->rows)===1,'newsletter excluded');
$invalid=$raw; $invalid['date-175']='31-02-2026'; vera_ob_capture(new Form(1271),$abort,new Submission($invalid)); check($abort && count($wpdb->rows)===1,'invalid date excluded');
$wpdb->fail=true; $abort=false; vera_ob_capture(new Form(1271),$abort,new Submission($raw)); check($abort,'database failure must not return success');
echo "WordPress bridge fixture checks passed\n";

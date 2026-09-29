# Booking online → Vera Spa

Implementation prepared for deployment; installing the code alone does not activate the integration.

## Behavior

- Reviewed CF7 booking form **1271**, contact form **606**. Newsletter/other forms excluded.
- WordPress captures validated/non-spam submissions before mail delivery; `skip_mail: on` remains supported. It commits a local outbox record first; a failed insert aborts success. Mail failure does not discard the saved request.
- A short signed server-to-server POST forwards the request to Vera. No key or customer data is placed in browser JavaScript, a URL or logs.
- API stores each event UUID once. Same UUID/different content is rejected; retry after timeout cannot create another record. Two independent customer submissions intentionally remain separate requests.
- Separate PostgreSQL rows, indexed inbox, SQL pagination (25/page), optimistic per-row updates. No Live Tour aggregate write or global business lock.
- Admin/Quản lý/Lễ tân can view and process. Other roles and accounts requiring password changes are denied by the API.
- On visible Live Tour, poll unread requests every **5 seconds**, no overlapping requests or hidden-tab polling. Acknowledgement is per account and persists across devices. Popup is not an OS notification and does not run while the app is closed.
- Menu **Booking online** retains booking and contact history, search by name/phone, status/type filters, processing notes. Confirmation records reception's decision; it does not allocate employees, create an invoice or charge the customer.
- Contact form has only name, phone and message. Missing appointment fields display **Chưa cung cấp**; no inferred appointment.

## Activation (after merge and normal VPS deploy)

1. Generate a random secret of at least 32 characters in a secure terminal, e.g. `openssl rand -hex 32`. Do not paste it in chat, git, URLs or workflow logs.
2. Add `VERA_WEBSITE_WEBHOOK_SECRET=<same secret>` to a private systemd `EnvironmentFile` used by the actual API service (owner/service readable, mode 0600). Use a dedicated drop-in so normal deploys preserve it. Do not put it in `web-v2-api.env`: that loader accepts only DB/Auth keys. Restart via the approved normal deployment process. Verify deployed SHA, `/v2/auth/health` and `/v2/health`.
3. In WordPress `wp-config.php`, before the stop-editing line, define `VERA_WEBSITE_WEBHOOK_SECRET` with the same secret. Only server processes should read it. Existing keys should be rotated on both servers together; pending deliveries sign again on each attempt.
4. Install `integrations/wordpress/vera-online-booking.php` as `wp-content/plugins/vera-online-booking/vera-online-booking.php`, then activate **Vera Spa Online Booking**. Activation creates the private outbox and minute cron schedule. Do not paste this file into Code Snippets: it relies on plugin activation.
5. Confirm the admin warning for missing key is absent. Configure a reliable server-side WordPress cron every minute if visitor-triggered WP-Cron is disabled or unreliable. Request shutdown triggers a non-blocking cron spawn for early delivery; it does not wait for the remote API. Retry delay grows to an hour during prolonged failures; records are retained until acknowledged by the API.
6. With approval for a clearly marked test submission, submit each public form once. On an Admin/Lễ tân Live Tour, verify all provided fields, popup, durable history, acknowledgement/reload, and role isolation. A contact request should retain its message and show missing appointment fields explicitly. Verify the outbox count returns to zero; a green deploy alone is insufficient.

The HMAC signs `unix_timestamp + '.' + exact_raw_json_body` using SHA-256; headers `X-Vera-Timestamp` and `X-Vera-Signature`. Five-minute clock tolerance; clocks on both servers must be synchronized. The endpoint fails closed if the secret is missing. Payload limit is 16 KiB. Table setup is transactional on first authenticated inbox/webhook request; application DB owner needs the same DDL privileges as existing stores. Anonymous Supabase roles have no table privileges and RLS is enabled.

## Recovery and rollback

- WordPress warning shows pending count only. Investigate HTTP status and clock/key/configuration without dumping payloads.
- Invalid records (422) and key failures (401/503) remain queued and produce no false success from the API. Fix the cause, then cron retries; do not delete the outbox to silence the warning.
- Deactivate the WordPress plugin to stop capture/delivery; outbox remains intact for reactivation. Existing CF7/Flamingo behavior is unchanged.
- Backend/UI rollback must not drop `vera_online_booking` or `vera_online_booking_seen`; retain customer history and deduplication records. Pause the plugin before a backend rollback to a release lacking this endpoint.
- Customer data is stored on the existing WordPress/Vera servers; include these tables in normal protected backups and retention policy.

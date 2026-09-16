#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vera_web_v2_api import _engine_instance
import vera_live_tour_queue_alerts as alerts


def main() -> None:
    engine = _engine_instance()
    with engine.connect() as conn:
        subscriptions = alerts._admin_subscriptions(conn)
        private_key = alerts._vault_secret(conn, "vera_v2_vapid_private_key")
        subject = alerts._vault_secret(conn, "vera_v2_vapid_subject")

    if len(subscriptions) != 1:
        raise SystemExit(f"CONTROLLED_PUSH_REFUSED: expected exactly 1 active admin/quanly subscription, found {len(subscriptions)}")
    if not private_key:
        raise SystemExit("CONTROLLED_PUSH_REFUSED: VAPID private key is not configured")
    if not subject or not subject.startswith("mailto:"):
        raise SystemExit("CONTROLLED_PUSH_REFUSED: VAPID subject must be configured as mailto:<admin-email>")

    subscription = subscriptions[0]
    payload = {
        "kind": "admin-system-change",
        "title": "VERA SPA · Kiểm tra Web Push",
        "body": "Kiểm tra kết nối Web Push sau khi cập nhật VAPID. Không cần thao tác.",
        "url": alerts.APP_URL,
        "tag": "vera-controlled-web-push-test",
    }

    ok, status, error = alerts._send(subscription, payload, private_key, subject)
    alerts._update_subscription(
        lambda: engine,
        str(subscription["subscription_id"]),
        ok,
        status,
        error,
    )

    result = {
        "ok": bool(ok),
        "http_status": status,
        "target_count": 1,
        "secret_values_printed": False,
    }
    if error:
        result["error"] = str(error)[:500]
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))

    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

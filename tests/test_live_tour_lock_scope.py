from pathlib import Path


SOURCE = Path(__file__).parents[1] / "vera_web_v2_live_tour.py"


def source():
    return SOURCE.read_text(encoding="utf-8")


def test_background_projection_skips_when_operator_holds_lock():
    body = source()
    scheduler = body[body.index("    def scheduled_projection():"):body.index("    def start_scheduler():")]
    assert "if try_state_lock(conn, STATE_LOCK):" in scheduler
    assert "acquire_state_lock(conn, STATE_LOCK)" not in scheduler


def test_permissions_are_resolved_before_mutation_lock():
    body = source()
    action = body[body.index('    @app.post("/v2/live-tour/action")'):body.index('    @app.get("/v2/live-tour/export.xlsx")')]
    assert action.index("grants = permissions(conn, ident)") < action.index("acquire_state_lock(conn, STATE_LOCK)")


def test_safe_metadata_mutations_skip_attendance_projection():
    body = source()
    action = body[body.index('    @app.post("/v2/live-tour/action")'):body.index('    @app.get("/v2/live-tour/export.xlsx")')]
    for name in (
        "admin_reorder", "settings_reorder", "payment_settings_update",
        "service_area_upsert", "room_upsert", "service_upsert", "combo_upsert",
    ):
        assert f'"{name}"' in action
    assert "read_state_without_projection(conn, now, for_update=True)" in action


def test_booking_mutations_keep_full_projection_but_financial_mutations_skip_it():
    body = source()
    action = body[body.index('    @app.post("/v2/live-tour/action")'):body.index('    @app.get("/v2/live-tour/export.xlsx")')]
    projection_set = action[action.index("projection_free_actions = {"):action.index("state, revision = (")]
    for name in ("booking", "multi_booking"):
        assert f'"{name}"' not in projection_set
    for name in ("checkout", "quick_checkout", "combo_purchase", "pending_update", "paid_invoice_update"):
        assert f'"{name}"' in projection_set

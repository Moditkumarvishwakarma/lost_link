import database


def test_report_sms_consent_and_notification_status_persist(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "lostlink-test.db")
    database.init_db()
    lost_id = database.add_report(
        {
            "status": "lost",
            "item_name": "Wallet",
            "category": "Wallets and personal belongings",
            "description": "Black wallet",
            "location": "Library",
            "report_date": "2026-10-10",
            "contact": "+919876543210",
            "reporter_name": "Riya",
            "share_contact_consent": True,
            "sms_consent": True,
        }
    )
    found_id = database.add_report(
        {
            "status": "found",
            "item_name": "Wallet",
            "category": "Wallets and personal belongings",
            "description": "Found near library",
            "location": "Library",
            "report_date": "2026-10-10",
        }
    )

    assert database.get_report_by_id(lost_id)["sms_consent"] == 1
    assert database.get_report_by_id(lost_id)["reporter_name"] == "Riya"
    assert database.get_report_by_id(lost_id)["share_contact_consent"] == 1
    assert not database.has_sent_sms_notification(lost_id, found_id)
    database.save_sms_notification(lost_id, found_id, "sent", "SM123")
    assert database.has_sent_sms_notification(lost_id, found_id)


def test_update_report_persists_changed_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "lostlink-edit-test.db")
    database.init_db()
    report_id = database.add_report(
        {
            "status": "found",
            "item_name": "Blue bottle",
            "category": "Water bottles",
            "description": "Plastic bottle",
            "location": "Library",
            "report_date": "2026-10-10",
            "reporter_name": "Sam",
            "contact": "old@example.com",
        }
    )

    updated = database.update_report(
        report_id,
        {
            "item_name": "Steel bottle",
            "category": "Water bottles",
            "description": "Silver steel bottle",
            "location": "Science block",
            "report_date": "2026-10-09",
            "reporter_name": "Sam Lee",
            "contact": "new@example.com",
            "share_contact_consent": True,
            "image_path": "",
        },
    )

    assert updated
    saved = database.get_report_by_id(report_id)
    assert saved["item_name"] == "Steel bottle"
    assert saved["location"] == "Science block"
    assert saved["reporter_name"] == "Sam Lee"
    assert saved["contact"] == "new@example.com"
    assert saved["share_contact_consent"] == 1


def test_update_report_returns_false_for_missing_id(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "lostlink-missing-test.db")
    database.init_db()

    assert not database.update_report(
        999,
        {
            "item_name": "Missing",
            "category": "Other",
            "description": "Description",
            "location": "Campus",
            "report_date": "2026-10-10",
        },
    )


def test_delete_report_removes_report_assessments_and_notifications(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "lostlink-delete-test.db")
    database.init_db()
    lost_id = database.add_report(
        {
            "status": "lost",
            "item_name": "Wallet",
            "category": "Wallets and personal belongings",
            "description": "Black wallet",
            "location": "Library",
            "report_date": "2026-10-10",
            "image_path": "uploads/wallet.jpg",
        }
    )
    found_id = database.add_report(
        {
            "status": "found",
            "item_name": "Wallet",
            "category": "Wallets and personal belongings",
            "description": "Found wallet",
            "location": "Library",
            "report_date": "2026-10-10",
        }
    )
    database.save_assessment(
        lost_id,
        found_id,
        {
            "match_score": 80,
            "matching_features": ["wallet"],
            "conflicting_features": [],
            "explanation": "Possible match",
            "recommendation": "Verify privately",
            "source": "fallback",
        },
    )
    database.save_sms_notification(lost_id, found_id, "sent", "SM123")

    assert database.delete_report(lost_id) == "uploads/wallet.jpg"
    assert database.get_report_by_id(lost_id) is None
    assert not database.has_sent_sms_notification(lost_id, found_id)
    with database.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM match_assessments").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM sms_notifications").fetchone()[0] == 0


def test_delete_missing_report_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "lostlink-delete-empty.db")
    database.init_db()

    assert database.delete_report(999) is None

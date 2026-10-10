import matching
from matching import basic_keyword_similarity, filter_candidate_reports


def test_basic_keyword_similarity_rewards_shared_details():
    lost = {
        "item_name": "Black wallet",
        "description": "Lost near the library yesterday. It has a silver zipper and a student ID insert.",
        "category": "Wallets and personal belongings",
        "location": "College library",
        "report_date": "2026-10-01",
    }
    found = {
        "item_name": "Dark wallet",
        "description": "Found outside the library. Black wallet with silver zipper and an ID card holder.",
        "category": "Wallets and personal belongings",
        "location": "Library entrance",
        "report_date": "2026-10-02",
    }

    score = basic_keyword_similarity(lost, found)
    assert 30 <= score <= 100


def test_filter_candidate_reports_skips_unrelated_items():
    lost = {
        "item_name": "Blue water bottle",
        "description": "Hydro flask near engineering block",
        "category": "Water bottles",
        "location": "Engineering block",
        "report_date": "2026-10-01",
    }
    found = {
        "item_name": "Red notebook",
        "description": "Found in the library",
        "category": "Books and stationery",
        "location": "Library",
        "report_date": "2026-10-03",
    }

    candidates = filter_candidate_reports(lost, [found])
    assert candidates == []


def test_gemma_prompt_does_not_include_private_report_contact(monkeypatch):
    prompts = []

    def fake_ask(prompt, system, thinking):
        prompts.append(prompt)
        return (
            '{"match_score": 72, "matching_features": ["wallet"], '
            '"conflicting_features": [], "explanation": "Possible match", '
            '"recommendation": "Verify privately"}'
        )

    monkeypatch.setattr(matching.gemma_client, "ask", fake_ask)
    report = {
        "item_name": "Wallet",
        "category": "Wallets and personal belongings",
        "description": "Black wallet",
        "location": "Library",
        "report_date": "2026-10-10",
        "contact": "private@example.com",
        "sms_consent": True,
    }

    matching.call_gemma_match_analysis(report, report)

    assert "private@example.com" not in prompts[0]
    assert "sms_consent" not in prompts[0]


def test_assess_match_explains_when_gemma_key_is_missing(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    report = {
        "item_name": "Black wallet",
        "category": "Wallets and personal belongings",
        "description": "Black wallet near library",
        "location": "Library",
        "report_date": "2026-10-10",
    }

    result = matching.assess_match(report, report)

    assert result["source"] == "fallback"
    assert "API key is not configured" in result["fallback_reason"]


def test_assess_match_exposes_gemma_failure_and_uses_labeled_fallback(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "configured-test-value")
    monkeypatch.setattr(
        matching,
        "call_gemma_match_analysis",
        lambda *_: (_ for _ in ()).throw(RuntimeError("temporary API failure")),
    )
    monkeypatch.setattr(
        matching.gemma_client,
        "describe_error",
        lambda error: "Gemma API error details.",
    )
    report = {
        "item_name": "Black wallet",
        "category": "Wallets and personal belongings",
        "description": "Black wallet near library",
        "location": "Library",
        "report_date": "2026-10-10",
    }

    result = matching.assess_match(report, report)

    assert result["source"] == "fallback"
    assert "Gemma 4 analysis failed" in result["fallback_reason"]
    assert "Gemma API error details." in result["fallback_reason"]

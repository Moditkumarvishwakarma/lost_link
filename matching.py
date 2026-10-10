import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional

import gemma_client
from utils import get_tokens

SYSTEM_RULE = (
    "You are an assistant that helps students find potentially matching lost and found reports. "
    "Compare the provided descriptions, category, appearance, location, and dates. "
    "Identify similarities and contradictions. Never invent missing details. Do not assume two items are identical "
    "merely because they share a category or location. Return valid JSON only with keys: "
    "match_score, matching_features, conflicting_features, explanation, recommendation."
)


def _shared_tokens(left: Iterable[str], right: Iterable[str]) -> set[str]:
    return set(left) & set(right)


def _is_close_in_time(lost: Dict[str, Any], found: Dict[str, Any]) -> bool:
    try:
        from datetime import datetime

        lost_date = lost.get("report_date")
        found_date = found.get("report_date")
        if not lost_date or not found_date:
            return True
        lost_dt = datetime.fromisoformat(str(lost_date))
        found_dt = datetime.fromisoformat(str(found_date))
        return abs((lost_dt - found_dt).days) <= 14
    except ValueError:
        return True


def basic_keyword_similarity(lost_report: Dict[str, Any], found_report: Dict[str, Any]) -> int:
    lost_text = " ".join([
        lost_report.get("item_name", ""),
        lost_report.get("description", ""),
        lost_report.get("distinguishing_features", ""),
        lost_report.get("location", ""),
        lost_report.get("category", ""),
    ])
    found_text = " ".join([
        found_report.get("item_name", ""),
        found_report.get("description", ""),
        found_report.get("distinguishing_features", ""),
        found_report.get("location", ""),
        found_report.get("category", ""),
    ])

    lost_tokens = set(get_tokens(lost_text))
    found_tokens = set(get_tokens(found_text))
    overlap = _shared_tokens(lost_tokens, found_tokens)
    score = len(overlap) * 8

    if str(lost_report.get("category", "")).lower() == str(found_report.get("category", "")).lower():
        score += 35
    else:
        score = max(0, score - 20)

    if _shared_tokens(get_tokens(lost_report.get("location", "")), get_tokens(found_report.get("location", ""))):
        score += 20
    if _is_close_in_time(lost_report, found_report):
        score += 10
    if len(overlap) == 0 and str(lost_report.get("category", "")).lower() != str(found_report.get("category", "")).lower():
        return 0
    return min(100, max(0, score))


def filter_candidate_reports(lost_report: Dict[str, Any], found_reports: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for found_report in found_reports:
        score = basic_keyword_similarity(lost_report, found_report)
        if score <= 15:
            continue
        filtered.append({**found_report, "match_score": score})
    return sorted(filtered, key=lambda item: item.get("match_score", 0), reverse=True)[:10]


def parse_match_response(response_text: str) -> Optional[Dict[str, Any]]:
    text = (response_text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def call_gemma_match_analysis(lost_report: Dict[str, Any], found_report: Dict[str, Any]) -> Dict[str, Any]:
    match_fields = (
        "item_name",
        "category",
        "description",
        "location",
        "report_date",
        "distinguishing_features",
    )
    payload = {
        "lost_item": {key: lost_report.get(key, "") for key in match_fields},
        "found_item": {key: found_report.get(key, "") for key in match_fields},
        "comparison_rules": [
            "Same or similar item names and descriptions",
            "Nearby campus location",
            "Similar date window",
            "Check contradictions such as color, brand, or physical details",
        ],
    }
    prompt = (
        f"Compare the following lost and found reports. Do not invent missing details. "
        f"Return valid JSON only.\n\n{json.dumps(payload, ensure_ascii=False)}"
    )
    response = gemma_client.ask(prompt, system=SYSTEM_RULE, thinking=False)
    parsed = parse_match_response(response)
    if not parsed:
        raise ValueError("Gemma did not return JSON for the match assessment.")
    match_score = int(parsed.get("match_score", 0))
    return {
        "match_score": max(0, min(100, match_score)),
        "matching_features": parsed.get("matching_features") or [],
        "conflicting_features": parsed.get("conflicting_features") or [],
        "explanation": parsed.get("explanation") or "The reports share some overlap but the details are not enough to confirm a match.",
        "recommendation": parsed.get("recommendation") or "Ask the claimant to verify a private detail before handing over the item.",
        "source": "ai",
    }


def assess_match(lost_report: Dict[str, Any], found_report: Dict[str, Any]) -> Dict[str, Any]:
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        fallback = basic_match_fallback(lost_report, found_report)
        return {
            **fallback,
            "source": "fallback",
            "fallback_reason": "Gemma 4 API key is not configured; this is a basic keyword estimate.",
        }
    try:
        return call_gemma_match_analysis(lost_report, found_report)
    except Exception as error:
        fallback = basic_match_fallback(lost_report, found_report)
        return {
            **fallback,
            "source": "fallback",
            "fallback_reason": (
                "Gemma 4 analysis failed, so this is a basic keyword estimate. "
                + gemma_client.describe_error(error)
            ),
        }


def basic_match_fallback(lost_report: Dict[str, Any], found_report: Dict[str, Any]) -> Dict[str, Any]:
    score = basic_keyword_similarity(lost_report, found_report)
    shared = _shared_tokens(
        get_tokens(lost_report.get("item_name", "") + " " + lost_report.get("description", "")),
        get_tokens(found_report.get("item_name", "") + " " + found_report.get("description", "")),
    )
    conflicting = []
    if str(lost_report.get("category", "")).lower() != str(found_report.get("category", "")).lower():
        conflicting.append("Category does not match exactly.")
    if not _shared_tokens(get_tokens(lost_report.get("location", "")), get_tokens(found_report.get("location", ""))):
        conflicting.append("Location details differ.")
    if score >= 75:
        explanation = "The item descriptions and location overlap strongly enough to warrant a careful manual review."
        recommendation = "Ask the owner to confirm a private detail before returning the item."
    elif score >= 40:
        explanation = "The reports share plausible similarities, but there are still contradictions that need verification."
        recommendation = "Review the item with the finder and compare unique details before proceeding."
    else:
        explanation = "There is limited evidence of a match. This looks like a weak similarity rather than a confirmed match."
        recommendation = "Do not assume these reports refer to the same object. Request more detail from the claimant."

    return {
        "match_score": score,
        "matching_features": sorted(shared)[:5],
        "conflicting_features": conflicting or ["No strong contradictions were identified in the limited data."],
        "explanation": explanation,
        "recommendation": recommendation,
    }

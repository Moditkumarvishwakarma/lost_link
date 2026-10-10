from __future__ import annotations

import os
from datetime import date
from html import escape
from typing import Any, Dict

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

import database
import image_storage
import matching
import sms_client
from requests.exceptions import RequestException
from utils import make_chip_text, mask_contact

st.set_page_config(page_title="LostLink AI", page_icon="🧭", layout="wide")
SMS_MATCH_THRESHOLD = 70

CATEGORY_OPTIONS = [
    "Electronics",
    "Wallets and personal belongings",
    "ID cards",
    "Books and stationery",
    "Keys",
    "Clothing",
    "Water bottles",
    "Other",
]


def safe_report_data(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": report.get("id"),
        "status": report.get("status", "lost"),
        "item_name": report.get("item_name", "Unknown item"),
        "category": report.get("category", "Other"),
        "description": report.get("description", "No description provided."),
        "location": report.get("location", "Unknown location"),
        "report_date": report.get("report_date", str(date.today())),
        "distinguishing_features": report.get("distinguishing_features") or "No extra details provided.",
        "contact": report.get("contact") or "Not shared",
        "image_path": report.get("image_path") or "",
    }


def configure_gemini_key() -> bool:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        try:
            api_key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
        except StreamlitSecretNotFoundError:
            api_key = ""
        if api_key:
            os.environ["GEMINI_API_KEY"] = api_key
    return bool(api_key)


def render_stats_cards(stats: Dict[str, Any]) -> None:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total lost items", stats.get("total_lost", 0))
    with col2:
        st.metric("Total found items", stats.get("total_found", 0))
    with col3:
        lost = database.list_reports(status="lost")
        found = database.list_reports(status="found")
        potential = sum(len(matching.filter_candidate_reports(item, found)) for item in lost)
        st.metric("Potential matches", potential)
    with col4:
        st.metric("Recent reports", len(stats.get("recent", [])))

    if stats.get("category_stats"):
        st.subheader("Category-wise stats")
        chart_data = {row["category"]: row["count"] for row in stats["category_stats"]}
        st.bar_chart(chart_data)


def render_report_card(report: Dict[str, Any]) -> None:
    item = safe_report_data(report)
    escaped = {
        key: escape(str(item[key]))
        for key in (
            "item_name",
            "category",
            "location",
            "report_date",
            "description",
            "distinguishing_features",
        )
    }
    st.markdown(
        """
        <div style='padding:18px; border:1px solid #2b2d42; border-radius:16px; background: linear-gradient(135deg, rgba(20,184,166,0.12), rgba(147,197,253,0.08)); margin-bottom: 10px;'>
            <h4>{title}</h4>
            <p><b>Category:</b> {category} &nbsp; | &nbsp; <b>Location:</b> {location} &nbsp; | &nbsp; <b>Date:</b> {date}</p>
            <p>{description}</p>
            <p><b>Key details:</b> {features}</p>
            <p><b>Contact:</b> {contact}</p>
        </div>
        """.format(
            title=escaped["item_name"],
            category=escaped["category"],
            location=escaped["location"],
            date=escaped["report_date"],
            description=escaped["description"],
            features=escaped["distinguishing_features"],
            contact=escape(mask_contact(item["contact"])),
        ),
        unsafe_allow_html=True,
    )
    if item["image_path"]:
        image_path = image_storage.get_uploaded_image_path(item["image_path"])
        if image_path:
            st.image(str(image_path), caption=f"Photo: {item['item_name']}", width=320)
        else:
            st.caption("The image for this report is no longer available.")


def render_dashboard() -> None:
    st.title("LostLink AI")
    st.caption("Lost something? Let AI find it.")
    stats = database.get_stats()
    render_stats_cards(stats)
    st.subheader("Recently reported items")
    recent = stats.get("recent", [])
    if not recent:
        st.info("No reports yet. Create the first lost or found entry.")
        return
    for report in recent[:6]:
        render_report_card(report)


def render_lost_form() -> None:
    st.title("Report a Lost Item")
    with st.form("lost_form"):
        item_name = st.text_input("Item name *")
        category = st.selectbox("Category *", CATEGORY_OPTIONS)
        description = st.text_area("Description *", height=110)
        location = st.text_input("Last-seen location *")
        report_date = st.date_input("Date lost *", value=date.today())
        distinguishing_features = st.text_area("Distinguishing features (optional)")
        contact = st.text_input(
            "Indian mobile number for match alerts (optional)",
            placeholder="9876543210 or +91 9876543210",
            help="Enter a 10-digit Indian mobile number starting with 6–9, with or without +91.",
        )
        sms_consent = st.checkbox(
            "I agree to receive an SMS if a found item may match this report."
        )
        uploaded_image = st.file_uploader(
            "Optional item photo (PNG/JPEG, up to 5 MB)",
            type=["png", "jpg", "jpeg"],
            key="lost_item_image",
            help="Do not include ID numbers, addresses, or other private details in the photo.",
        )
        submitted = st.form_submit_button("Save lost report")
        if submitted:
            missing = [field for field, value in {"Item name": item_name, "Description": description, "Last-seen location": location}.items() if not str(value).strip()]
            if missing:
                st.error(f"Please complete the required fields: {', '.join(missing)}")
                return
            if sms_consent and not sms_client.normalize_phone_number(contact):
                st.error(
                    "To receive SMS alerts, enter a valid Indian mobile number "
                    "(10 digits starting with 6–9, optionally prefixed with +91)."
                )
                return
            image_path = ""
            if uploaded_image is not None:
                try:
                    image_path = image_storage.save_uploaded_image(uploaded_image.getvalue())
                except ValueError as error:
                    st.error(str(error))
                    return
            database.add_report({
                "status": "lost",
                "item_name": item_name.strip(),
                "category": category,
                "description": description.strip(),
                "location": location.strip(),
                "report_date": str(report_date),
                "distinguishing_features": distinguishing_features.strip(),
                "contact": contact.strip(),
                "sms_consent": sms_consent,
                "image_path": image_path,
            })
            if sms_consent and contact.strip():
                st.success("Lost item report saved. We’ll text you if a likely match is found.")
            else:
                st.success("Lost item report saved successfully.")


def notify_lost_reporters(found_report_id: int) -> None:
    configure_gemini_key()
    found_report = database.get_report_by_id(found_report_id)
    if not found_report:
        st.error("The found-item report was saved, but could not be loaded for matching.")
        return

    lost_reports = database.list_reports(status="lost")
    candidates = matching.filter_candidate_reports(found_report, lost_reports)
    if not candidates:
        st.info("Found report saved. No likely lost-item reports were found to compare yet.")
        return

    sent = 0
    skipped_phone = 0
    skipped_consent = 0
    already_notified = 0
    likely_count = 0
    send_errors = []
    with st.spinner("Checking existing lost reports for possible matches…"):
        for candidate in candidates:
            lost_report = database.get_report_by_id(candidate["id"])
            if not lost_report:
                continue
            assessment = matching.assess_match(lost_report, found_report)
            database.save_assessment(lost_report["id"], found_report_id, assessment)
            if assessment["match_score"] < SMS_MATCH_THRESHOLD:
                continue

            likely_count += 1
            if not lost_report.get("sms_consent"):
                skipped_consent += 1
                continue
            to_number = sms_client.normalize_phone_number(lost_report.get("contact", ""))
            if not to_number:
                skipped_phone += 1
                continue
            if database.has_sent_sms_notification(lost_report["id"], found_report_id):
                already_notified += 1
                continue

            message = sms_client.build_match_message(
                found_report["category"],
                found_report["location"],
                found_report["report_date"],
                reporter_name=found_report.get("reporter_name", ""),
                reporter_contact=found_report.get("contact", ""),
                share_contact=bool(found_report.get("share_contact_consent")),
            )
            try:
                message_sid = sms_client.send_sms(to_number, message)
            except sms_client.SmsConfigurationError as error:
                send_errors.append(str(error))
                break
            except (sms_client.TwilioRestException, RequestException):
                database.save_sms_notification(
                    lost_report["id"], found_report_id, "failed"
                )
                send_errors.append(
                    "SMS could not be sent. Check your connection, Twilio account, sender number, and recipient format."
                )
                continue
            database.save_sms_notification(
                lost_report["id"], found_report_id, "sent", message_sid
            )
            sent += 1

    if sent:
        st.success(f"Sent {sent} potential-match SMS alert(s).")
    if likely_count == 0:
        st.info("Found report saved. No potential matches scored 70 or higher.")
    if skipped_consent:
        st.info(
            f"{skipped_consent} likely match(es) were not texted because the reporter did not opt in."
        )
    if skipped_phone:
        st.info(
            f"{skipped_phone} opted-in reporter(s) need a valid Indian mobile number "
            "to receive SMS alerts."
        )
    if already_notified:
        st.info(f"Skipped {already_notified} alert(s) already sent for this report pair.")
    for error in send_errors:
        st.error(error)


def render_edit_form(report: Dict[str, Any]) -> None:
    item = safe_report_data(report)
    report_id = int(item["id"])
    report_date = date.fromisoformat(item["report_date"])
    with st.expander("Edit this report"):
        with st.form(f"edit_report_{report_id}"):
            item_name = st.text_input("Item name *", value=item["item_name"])
            category_index = (
                CATEGORY_OPTIONS.index(item["category"])
                if item["category"] in CATEGORY_OPTIONS
                else CATEGORY_OPTIONS.index("Other")
            )
            category = st.selectbox(
                "Category *", CATEGORY_OPTIONS, index=category_index
            )
            description = st.text_area(
                "Description *", value=item["description"], height=110
            )
            location_label = (
                "Last-seen location *"
                if item["status"] == "lost"
                else "Location found *"
            )
            location = st.text_input(location_label, value=item["location"])
            edited_report_date = st.date_input(
                "Report date *", value=report_date
            )
            distinguishing_features = st.text_area(
                "Distinguishing features",
                value=report.get("distinguishing_features") or "",
            )

            reporter_name = ""
            share_contact_consent = False
            sms_consent = False
            if item["status"] == "found":
                reporter_name = st.text_input(
                    "Finder name", value=report.get("reporter_name") or ""
                )
                contact = st.text_input(
                    "Finder phone or email",
                    value=report.get("contact") or "",
                )
                share_contact_consent = st.checkbox(
                    "I agree to share my name and contact details with a likely claimant.",
                    value=bool(report.get("share_contact_consent")),
                    key=f"share_contact_{report_id}",
                )
            else:
                contact = st.text_input(
                    "Indian mobile number for match alerts",
                    value=report.get("contact") or "",
                    placeholder="9876543210 or +91 9876543210",
                )
                sms_consent = st.checkbox(
                    "I agree to receive an SMS if a found item may match this report.",
                    value=bool(report.get("sms_consent")),
                    key=f"sms_consent_{report_id}",
                )

            replacement_image = st.file_uploader(
                "Replace photo (optional; PNG/JPEG, up to 5 MB)",
                type=["png", "jpg", "jpeg"],
                key=f"edit_image_{report_id}",
            )
            remove_image = False
            if item["image_path"]:
                remove_image = st.checkbox(
                    "Remove current photo",
                    key=f"remove_image_{report_id}",
                )

            submitted = st.form_submit_button("Save changes")
            if submitted:
                missing = [
                    label
                    for label, value in {
                        "Item name": item_name,
                        "Description": description,
                        "Location": location,
                    }.items()
                    if not value.strip()
                ]
                if missing:
                    st.error(f"Please complete the required fields: {', '.join(missing)}")
                    return
                if item["status"] == "lost" and sms_consent and not sms_client.normalize_phone_number(contact):
                    st.error(
                        "To receive SMS alerts, enter a valid Indian mobile number "
                        "(10 digits starting with 6–9, optionally prefixed with +91)."
                    )
                    return

                old_image_path = item["image_path"]
                new_image_path = old_image_path
                if replacement_image is not None:
                    try:
                        new_image_path = image_storage.save_uploaded_image(
                            replacement_image.getvalue()
                        )
                    except ValueError as error:
                        st.error(str(error))
                        return
                elif remove_image:
                    new_image_path = ""

                updated_report = {
                    "item_name": item_name.strip(),
                    "category": category,
                    "description": description.strip(),
                    "location": location.strip(),
                    "report_date": str(edited_report_date),
                    "distinguishing_features": distinguishing_features.strip(),
                    "contact": contact.strip(),
                    "reporter_name": reporter_name.strip(),
                    "share_contact_consent": share_contact_consent,
                    "sms_consent": sms_consent,
                    "image_path": new_image_path,
                }
                if not database.update_report(report_id, updated_report):
                    if replacement_image is not None:
                        image_storage.delete_uploaded_image(new_image_path)
                    st.error("This report could not be found, so the changes were not saved.")
                    return

                if old_image_path and old_image_path != new_image_path:
                    image_storage.delete_uploaded_image(old_image_path)
                st.session_state["report_updated"] = True
                st.rerun()

        st.warning("Deleting a report cannot be undone.")
        confirm_delete = st.checkbox(
            "I understand and want to delete this report.",
            key=f"confirm_delete_{report_id}",
        )
        if st.button(
            "Delete report",
            key=f"delete_report_{report_id}",
            type="secondary",
            disabled=not confirm_delete,
        ):
            deleted_image_path = database.delete_report(report_id)
            if deleted_image_path is None:
                st.error("This report could not be found, so it was not deleted.")
                return
            image_storage.delete_uploaded_image(deleted_image_path)
            st.session_state["report_deleted"] = True
            st.rerun()


def render_found_form() -> None:
    st.title("Report a Found Item")
    with st.form("found_form"):
        item_name = st.text_input("Item name *")
        category = st.selectbox("Category *", CATEGORY_OPTIONS)
        description = st.text_area("Description *", height=110)
        location = st.text_input("Location found *")
        report_date = st.date_input("Date found *", value=date.today())
        distinguishing_features = st.text_area("Distinguishing features (optional)")
        reporter_name = st.text_input("Your name (optional)")
        contact = st.text_input(
            "Your phone number or email (optional)",
            help="This is kept private and masked in public report cards.",
        )
        share_contact_consent = st.checkbox(
            "I agree to share my name and contact details with a lost-item reporter "
            "if their report is a likely match."
        )
        uploaded_image = st.file_uploader(
            "Optional item photo (PNG/JPEG, up to 5 MB)",
            type=["png", "jpg", "jpeg"],
            key="found_item_image",
            help="Do not include ID numbers, addresses, or other private details in the photo.",
        )
        submitted = st.form_submit_button("Save found report")
        if submitted:
            missing = [field for field, value in {"Item name": item_name, "Description": description, "Location found": location}.items() if not str(value).strip()]
            if missing:
                st.error(f"Please complete the required fields: {', '.join(missing)}")
                return
            image_path = ""
            if uploaded_image is not None:
                try:
                    image_path = image_storage.save_uploaded_image(uploaded_image.getvalue())
                except ValueError as error:
                    st.error(str(error))
                    return
            found_report_id = database.add_report({
                "status": "found",
                "item_name": item_name.strip(),
                "category": category,
                "description": description.strip(),
                "location": location.strip(),
                "report_date": str(report_date),
                "distinguishing_features": distinguishing_features.strip(),
                "reporter_name": reporter_name.strip(),
                "contact": contact.strip(),
                "share_contact_consent": share_contact_consent,
                "image_path": image_path,
            })
            st.success("Found item report saved.")
            notify_lost_reporters(found_report_id)


def render_match_finder() -> None:
    st.title("AI Match Finder")
    gemini_available = configure_gemini_key()
    lost_reports = database.list_reports(status="lost")
    found_reports = database.list_reports(status="found")
    if not lost_reports or not found_reports:
        st.info("Add at least one lost item and one found item to start matching.")
        return

    if not gemini_available:
        st.warning(
            "Gemma 4 API key is not configured. This finder can still run using "
            "basic keyword matching. Add GEMINI_API_KEY to .env or Streamlit secrets to enable Gemma."
        )

    left, right = st.columns(2)
    with left:
        lost_choice = st.selectbox("Select lost item", [f"{r['id']} | {r['item_name']}" for r in lost_reports])
    with right:
        found_choice = st.selectbox("Select found item", [f"{r['id']} | {r['item_name']}" for r in found_reports])

    if st.button("Analyze potential match"):
        lost_id = int(lost_choice.split(" | ")[0])
        found_id = int(found_choice.split(" | ")[0])
        lost_report = database.get_report_by_id(lost_id)
        found_report = database.get_report_by_id(found_id)
        if not lost_report or not found_report:
            st.error("One or both selected reports could not be loaded.")
            return
        result = matching.assess_match(lost_report, found_report)
        database.save_assessment(lost_id, found_id, result)

        st.markdown(f"### Match score: {result['match_score']}/100")
        st.caption("AI-generated assessment" if result.get("source") == "ai" else "Basic keyword-based assessment")
        if result.get("fallback_reason"):
            st.warning(result["fallback_reason"])
        st.progress(min(max(result["match_score"], 0), 100) / 100)
        st.subheader("Similarities")
        st.write(make_chip_text(result.get("matching_features", [])))
        st.subheader("Differences")
        st.write(make_chip_text(result.get("conflicting_features", [])))
        st.subheader("Explanation")
        st.write(result.get("explanation", "No explanation provided."))
        st.subheader("Suggested next step")
        st.write(result.get("recommendation", "Continue with a manual review."))

        with st.expander("Review match checklist"):
            st.markdown(
                """
                - Confirm the item type and category match.
                - Compare the distinctive appearance and color details.
                - Check whether the location and date overlap.
                - Require a private verification detail before returning valuables or IDs.
                - Keep all contact information private and avoid exposing full identifiers in public view.
                """
            )


def render_browse() -> None:
    st.title("Browse Items")
    if st.session_state.pop("report_updated", False):
        st.success("Report updated successfully.")
    if st.session_state.pop("report_deleted", False):
        st.success("Report and its associated data were deleted.")
    status_filter = st.selectbox("Status", ["all", "lost", "found"])
    category_filter = st.selectbox("Category", ["all"] + CATEGORY_OPTIONS)
    keyword_filter = st.text_input("Search keywords")
    location_filter = st.text_input("Campus location")

    reports = database.list_reports(
        status=None if status_filter == "all" else status_filter,
        category=None if category_filter == "all" else category_filter,
        location=location_filter.strip() or None,
        keyword=keyword_filter.strip() or None,
    )
    if not reports:
        st.info("No reports match the current filters.")
        return
    for report in reports:
        render_report_card(report)
        render_edit_form(report)


def render_about() -> None:
    st.title("About the project")
    st.markdown(
        """
        LostLink AI helps campus communities recover lost belongings faster while keeping private details protected.

        The platform combines a modern dashboard, searchable item records, and AI-assisted similarity checks. It never claims that a match is confirmed without manual verification.

        Safety rules:
        - Never reveal full ID numbers or personal contact details in public.
        - Ask claimants to confirm a private detail before handing over valuables.
        - Use AI as a support tool, not an automatic authority on ownership.
        """
    )


def main() -> None:
    pages = {
        "Home Dashboard": render_dashboard,
        "Report Lost Item": render_lost_form,
        "Report Found Item": render_found_form,
        "AI Match Finder": render_match_finder,
        "Browse Items": render_browse,
        "About the Project": render_about,
    }
    selected = st.sidebar.radio("Navigation", list(pages.keys()))
    pages[selected]()


if __name__ == "__main__":
    main()

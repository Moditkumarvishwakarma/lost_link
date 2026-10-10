# LostLink AI

LostLink AI is a campus lost-and-found platform built for the "Build for Your Campus" . It helps students report lost or found items, browse recent records, and use Gemma 4 to surface likely matches without automatically declaring a confirmed ownership claim.

## Features

- Dashboard with totals and recent activity
- Lost and found item forms with validation
- Edit saved report details from the Browse Items page
- Delete saved reports with confirmation
- Optional, persistent PNG/JPEG photos for lost and found reports (up to 5 MB)
- Search and filters by status, category, location, and keyword
- AI-assisted match scoring with a clear fallback mode
- Opt-in SMS alerts when a found report has a likely match
- Finder name/contact details are shared with the claimant only with the finder's explicit consent
- Privacy-first review checklist for valuables and identity documents

## Tech stack

- Python
- Streamlit
- SQLite
- Gemma 4 via Google GenAI
- Pytest

## Run the app

1. Create a virtual environment.
2. Install requirements:

```bash
pip install -r requirements.txt
```

3. Add your Gemini API key in `.env`:

```bash
copy .env.example .env
```

Then edit `.env` and replace the placeholder after `GEMINI_API_KEY=` with a valid key from Google AI Studio.

To send SMS alerts, configure `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM_NUMBER` in `.env`. SMS alerts support Indian mobile numbers only: enter a 10-digit number beginning with 6–9, optionally prefixed with `+91`. Lost-item reporters must opt in. A notification is sent only for a match score of 70 or higher; its wording says the match is unconfirmed. A finder's name and contact details are included only if they supplied them and explicitly consented to share them with a likely claimant. Without Twilio credentials, the report is still saved and the app explains why no SMS was sent.

4. Start the app:

```bash
streamlit run app.py
```

Uploaded photos are saved locally in the ignored `uploads/` directory and shown on report cards. Avoid uploading photos that reveal ID numbers, addresses, or other private details.

## Model

The app uses the Gemma 4 model name:

- `gemma-4-26b-a4b-it`

If the model is unavailable, the app warns the user and falls back to a clearly labeled rule-based matching mode.


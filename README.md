# Systematic IT Solutions AI Sales Agent

A production-oriented FastAPI sales assistant with website-grounded RAG, lead qualification,
an embeddable responsive widget, browser actions, integration webhooks, and an admin dashboard.
The demo defaults to `gpt-4.1-mini` for responsive website conversations.

## What is included

- GPT-powered, multilingual conversation grounded in the crawled company website
- Persistent conversation history, lead extraction, scoring (cold/warm/hot), and sales stages
- Service recommendations, objection-handling and conversion-oriented behavior
- User-confirmed actions to open relevant pages, prefill inquiry forms, call, or book in Google Calendar
- Signed, durable webhook delivery to a custom CRM, Google Sheets automation, and notifications
- Calendar webhook support for confirmed meeting events
- Visitor/conversation/conversion analytics, pipeline data, service popularity, FAQs and leads
- Built-in demo CRM for lead status, ownership, follow-up reminders, notes, and human replies
- Website crawler plus repeatable document, chunk, and embedding-index build scripts

## Run locally

1. Create `backend/.env` from `backend/.env.example` and set `OPENAI_API_KEY` and
   `OPENAI_CHAT_MODEL`. Keep secrets server-side.
2. From `backend`, install dependencies with `python -m pip install -r requirements.txt`.
3. Ensure `data/processed/knowledge_embeddings.json` exists (a generated index is included).
4. Run `uvicorn app.main:app --reload` from the `backend` directory.
5. Open `http://127.0.0.1:8000/demo`, `/docs`, or `/admin`.

Embed the widget on the company website:

```html
<script src="https://YOUR-API/widget/widget.js"
        data-api-base="https://YOUR-API"></script>
```

Set `ALLOWED_ORIGINS` to the production website origin. Actions that fill forms require the
widget to run on the same page as the form; browsers intentionally prevent cross-origin DOM
access.

## External integrations

Configure `CUSTOM_CRM_WEBHOOK_URL`, `GOOGLE_SHEETS_WEBHOOK_URL`, and
`NOTIFICATION_WEBHOOK_URL`. Identified-lead payloads include the full conversation, score,
temperature, status, suggested team, and follow-up time. With `INTEGRATION_SECRET` set, outgoing
requests contain an HMAC-SHA256 signature in `X-Sales-Agent-Signature`. Failed and unconfigured
deliveries remain visible in `integration_deliveries` for operational follow-up.
Google OAuth access and refresh tokens are encrypted at rest with Fernet using
`TOKEN_ENCRYPTION_KEY`; keep this key in the deployment secret manager and back it up securely.

For Google Calendar and Sheets, create an OAuth 2.0 Web Application in Google Cloud, enable the
Calendar API and Google Sheets API,
and register `http://127.0.0.1:8000/api/google-calendar/callback` as an authorized redirect URI.
Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, and optionally
`GOOGLE_CALENDAR_ID`. Start the application, open `/admin`, and select **Connect Google Calendar**.
The evaluator signs into Google and grants calendar-event access; no Google password is stored.
Meeting actions then open `/booking`, create a real event, invite the visitor, and request a Google
Meet conference link. The same OAuth connection upserts identified leads into Google Sheets by
session ID. Set `GOOGLE_SHEETS_SPREADSHEET_ID` to use an existing sheet with a `Leads` tab, or
leave it empty and the application creates an **AI Sales Agent Leads** spreadsheet automatically.
The demo defaults direct-call actions to the public website number `+1 626-381-8293`; override
`COMPANY_PHONE` when needed.

For real email notifications, Gmail SMTP is the default (`smtp.gmail.com:587` with STARTTLS).
Configure `SMTP_USERNAME`, a Google App Password in `SMTP_PASSWORD`, and comma-separated
`SALES_NOTIFICATION_EMAILS`; `SMTP_FROM_EMAIL` defaults to the username. Never use or commit the
normal Google account password. Notifications cover new leads,
meeting requests and bookings, proposal requests, high-value leads, and live-agent handovers.
Delivery results are persisted and SMTP failures never interrupt visitor conversations.

Protect dashboard APIs with `ADMIN_API_KEY` in production. The dashboard sends it via
`X-Admin-Key` and stores it only in the browser's local storage.

## Knowledge updates

From `backend`, run in order:

```text
python scripts/crawl_website.py
python scripts/process_knowledge.py
python scripts/build_embeddings.py
```

This makes website content refresh explicit and repeatable. Schedule these commands in the
deployment platform for continuous updates.

The application also starts an automatic background crawl on every startup. Content hashes are
compared with the current snapshot, so OpenAI embeddings are rebuilt only when website content
changed or the index is missing. The refreshed index is swapped in atomically and loaded by the
running sales agent; refresh status and errors appear in dashboard analytics.

## Validation

Run the offline automated suite (no OpenAI calls):

```text
python -m unittest discover -s tests -v
```

The SQLite default is suitable for a single-instance demo. Set `DATABASE_URL` to a managed SQL
database for multi-instance production scale. Tables are created automatically; use a schema
migration tool before evolving an already-deployed production database.

# Frontend API contract

The UI in `frontend/` talks to the backend only through the interface in
`frontend/src/api/types.ts`. Two implementations exist:

| Implementation | When | Source |
| --- | --- | --- |
| Local stand-in | `VITE_API_URL` is not set | `frontend/src/api/local.ts`: reads `public/data/assessment.json` (written by `backend/scripts/export_frontend_data.py`) and answers chat with fixed rules |
| HTTP backend | `VITE_API_URL` is set, e.g. in `frontend/.env.local`: `VITE_API_URL=http://localhost:8000/api` | `frontend/src/api/remote.ts` |

A backend that serves the endpoints below replaces the stand-in without UI changes.

## Run the backend API locally

From the project root, start the API after the space and terrestrial assessments have
completed:

```powershell
.\.venv\Scripts\python.exe backend\scripts\serve_frontend_api.py
```

By default, startup refreshes `frontend/public/data/assessment.json` from `output/`
and serves the API at `http://127.0.0.1:8000/api`. The server uses the model settings
in the root `.env`; the API key remains on the backend. In `frontend/.env.local`, set:

```text
VITE_API_URL=http://localhost:8000/api
```

Then start the Vite development server as usual. The frontend selects its existing
remote API client from `VITE_API_URL`; no frontend source changes are required.

## Endpoints

| Method and path | Request | Response |
| --- | --- | --- |
| `GET /assessment` | | The same JSON as `assessment.json`: `{ generated, issues[], notices[], trends[] }`. Field meanings: `frontend/src/data.ts`. |
| `GET /notifications` | | `[{ id, text, ref?, createdAt? }]` |
| `POST /letters` | `{ scope: "notice" \| "administration", key }` | `{ text }` |
| `POST /chat` | `{ conversationId, messages: [{ role, content }], context?: { ref?, issueId? } }` | NDJSON stream of chat events (below), `Content-Type: application/x-ndjson` |

`key` for a notice is `<issueId>:<noticeId>`, e.g. `ific3074:124545403`; for an
administration it is the ITU code, e.g. `CHN`. `context.ref` tells the assistant what the
user was looking at when they pressed "Ask about this notice", "Ask about this station",
and so on.

## Chat events

One JSON object per line, applied in order to the assistant message:

```json
{"type":"reasoning","text":"Matched [CSN-SSO](notice:ific3074:124545403) in IFIC 3074."}
{"type":"text","text":"[CSN-SSO](notice:ific3074:124545403) from "}
{"type":"text","text":"[China](administration:CHN) is **exceeds limit**, 42.9 dB over limit."}
{"type":"reference","ref":"notice:ific3074:124545403","label":"CSN-SSO notice 124545403"}
{"type":"action","ref":"letter:notice:ific3074:124545403","label":"Draft letter for this notice"}
{"type":"action","ref":"letter:administration:CHN","label":"Open the draft letter","auto":true}
{"type":"done"}
```

| Event | UI element |
| --- | --- |
| `reasoning` | One step in the collapsible Reasoning block, open while the answer streams |
| `text` | Appended to the answer |
| `reference` | Listed under Sources |
| `action` | A button under the answer. With `auto: true` the UI opens it when the answer is done. |
| `done` | Ends the answer and shows Copy and Regenerate |
| `error` | Shows the message and a Retry button |

The user can stop the stream at any time. The UI then aborts the HTTP request.

## Text format and links

`text`, `reasoning` and notification texts use a small Markdown subset: blank line
between paragraphs, `- ` list items, `**bold**`, and `[label](ref)` links.

| Reference | Opens |
| --- | --- |
| `notice:<issueId>:<noticeId>` | Notice detail |
| `administration:<code>` | All notices from one administration |
| `station:<stationNumber>` | All notices affecting a Finnish station |
| `issue:<issueId>` | Overview for one issue |
| `letter:notice:<issueId>:<noticeId>` | Draft letter for one notice |
| `letter:administration:<code>` | Draft letter for one administration |
| `chat:<conversationId>` | A saved conversation |
| `https://...` | External document in a new tab |

The UI also links known names it finds in plain text (satellite names, notice numbers,
administration names, Finnish station numbers and issue labels), so an answer stays
navigable even when the model forgets to add links. Explicit links are still preferred
because they are unambiguous: two notices can share a satellite name.

## Rules for generated text

Quote the numbers, statuses and citations from the records instead of recomputing them.
Every value is a pessimistic screening result: an exceedance is a reason for expert review,
not proof of harmful interference. The UI's style rules also apply to generated text:
no em dashes and no `|`, ` - ` or `·` used as separators.

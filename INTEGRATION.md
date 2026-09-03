# Pipeline → UI handoff

Everything below is live now. Person B is not blocked on Person A for anything.

## Setup (one minute)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
printf 'RC_LLM_API_KEY=%s\n' "$YOUR_KEY" > .env    # your own key, not Person A's
```

Keys are one per person, never shared and never committed. `.env` is already
gitignored — check with `git check-ignore -v .env` if unsure.

Verify the whole chain in one command before writing any UI code:

```bash
.venv/bin/python -m slidesight decks/some_lecture.pptx -o out/test.pptx
```

## Start here: build against the fixture

Even with a working key, build the layout against the fixture first — it is
instant, deterministic, and contains a review item and an undecodable image,
which a clean deck may not produce on demand.

`fixtures/sample_report.json` is a real report, trimmed to 8 images that cover
every case the UI has to render — including a low-confidence review item and an
undecodable image. No API key, no model calls, no waiting.

```python
import json
report = json.load(open("fixtures/sample_report.json"))

queue = [i for i in report["images"] if i["action"] == "review_queue"]
applied = [i for i in report["images"] if i["action"] == "auto_applied"]
silent = [i for i in report["images"] if i["action"] == "decorative_empty_alt"]
```

## The record shape

One per image. This is the contract — it will not change without telling you.

```json
{
  "slide": 7,
  "image_id": "shape_4",
  "alt_text": "Bar chart of FY24 revenue by region. Southwest leads at $4.2M...",
  "confidence": 5,
  "decorative": false,
  "reason": null,
  "action": "auto_applied"
}
```

| `action` | Meaning | What the UI should do |
|---|---|---|
| `auto_applied` | Confidence 4–5, written into the deck | Show it, allow an edit |
| `review_queue` | Confidence 1–3, **not** written | **This is the centrepiece.** Show the image, the draft, and `reason` |
| `decorative_empty_alt` | Logo/icon, alt set to `""` so readers skip it | Show as "silenced", low prominence |

`reason` is populated whenever confidence is 3 or below, and explains *why* in
one line — that sentence is what makes the review queue persuasive rather than
just a list.

## Report-level fields

```
source  slides  images_found  auto_applied  review_queue  decorative
tables_detected  shapes_written  runtime_seconds  deck_summary  images[]  wcag{}
```

## Running it for real

```python
from slidesight import remediate

report = await remediate(
    "lecture.pptx",
    "out/lecture.remediated.pptx",
    concurrency=6,
    on_progress=lambda rec: ...,   # called once per image, as each lands
)
```

`on_progress` receives the same record shape as above, one at a time as results
arrive. Wire it straight to a progress bar and a live-updating list — a bar that
fills is a much better 90 seconds than a spinner.

Streamlit note: `remediate` is async. Call it with
`asyncio.run(remediate(...))`, and push records from `on_progress` onto a queue
or `st.session_state` rather than calling `st.write` from inside the callback.

## The WCAG report, with no API key

```python
from slidesight.pipeline import audit_only
audit = audit_only("lecture.pptx")     # ~0.4s, no model calls
```

Returns `wcag.total_issues`, `wcag.by_check`, and `wcag.issues[]` where each
issue is `{check, slide, detail, severity}`. Checks are `missing_title`,
`small_text`, `table_no_header`, `vague_link`, `reading_order`.

This path needs no key and no network, so it is also the graceful-degradation
demo if the gateway is down.

## Things worth knowing

- **Only `.pptx`.** Legacy `.ppt` is a different binary format. If a user
  uploads one, tell them to convert it — `soffice --headless --convert-to pptx`.
  The CLI already prints that message.
- **Image bytes are not in the report.** To show a thumbnail next to a review
  item, pull it from the deck with
  `slidesight.extract.extract_images(Presentation(path))` and match on
  `(slide, image_id)`.
- **Review items are not written to the file.** That is the whole point of the
  gate. If the UI lets a human approve one, it needs to write it back —
  `slidesight.extract.set_alt_text(shape, text)` does that; call
  `prs.save(path)` after.

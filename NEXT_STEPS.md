# Next steps — Person B

Three jobs: get the app hosted, test it properly, and pick the two decks we
demo. Read the hosting section first, because the obvious answer does not work.

---

## 1. Hosting

### Streamlit Community Cloud cannot host this

Worth saying plainly before you spend an hour on it. Streamlit Cloud runs one
command — `streamlit run your_app.py`. Our app is a **FastAPI server** that also
serves a static page (`web/`), started with `uvicorn`. There is no way to
express that on Streamlit Cloud.

The Streamlit front end that existed before was replaced by the approved
SlideSight design. Putting it back would mean throwing that design away, so the
question is really *"where do we host a FastAPI app"*.

**Good news:** the ASU AIR gateway is reachable from the public internet — it
answers `401` to an unauthenticated request rather than timing out, so a cloud
host can reach it. No VPN needed. (Getting a *key* still needs the portal.)

### Options, best first

| Option | Effort | Notes |
|---|---|---|
| **Run it locally for the demo** | zero | `uvicorn server.main:app --port 8000`. Nothing to break on stage, no cold start, no upload limits. **Recommended for Sept 3.** |
| **Render / Railway** | ~30 min | Free tier, native Python. Start command `uvicorn server.main:app --host 0.0.0.0 --port $PORT`. Add `RC_LLM_API_KEY` as a secret. Free tiers sleep — wake it before demoing. |
| **Hugging Face Spaces (Docker)** | ~45 min | Handles long-running requests well. Needs a small Dockerfile. |
| **Streamlit Cloud** | — | Not possible without rebuilding the UI in Streamlit and losing the approved design. |

### If you host it anywhere public, do these three things

1. **Put the key in the host's secret store**, never in the repo. `.env` is
   gitignored; keep it that way.
2. **Cap the upload size.** A 200 MB deck on a free tier will time out. The UI
   says 200 MB; the server does not enforce it yet.
3. **Expect cold starts.** Free tiers sleep after ~15 minutes. Hit the URL a few
   minutes before the demo.

**My honest recommendation: demo from localhost.** Hosting adds risk on the day
and buys nothing the judges will see. If you want a live URL for the submission,
put it up on Render *after* the demo is safely recorded.

---

## 2. Testing the app end to end

Start it:

```bash
.venv/bin/python -m uvicorn server.main:app --port 8000
```

Open <http://127.0.0.1:8000> and walk all four steps. Tick these off:

**Upload**
- [ ] Drag-and-drop works, and so does the file picker
- [ ] A **PDF** is rejected with a readable message, not a stack trace
- [ ] A **legacy .ppt** is rejected and tells you to convert it
- [ ] A PDF renamed `.pptx` is rejected (the server sniffs the bytes)

**Processing**
- [ ] The bar advances and the percentage matches
- [ ] Descriptions stream in as they land — you should not stare at a spinner
- [ ] Copy the URL, add `?job=<the id>`, refresh — the run resumes

**Review queue** — this is the one that matters
- [ ] Every item shows a **real thumbnail** of the image being judged
- [ ] "Why flagged" reads as a sentence a human can act on
- [ ] Editing the draft updates the character count
- [ ] **Approve** → the row greys out and says "Written into the file"
- [ ] **Skip** leaves it unwritten
- [ ] Download the deck and confirm your approved text is really in it:

```bash
.venv/bin/python scripts/screen_reader_preview.py ORIGINAL.pptx DOWNLOADED.pptx --slide N --silent
```

**Results**
- [ ] The four counts match the numbers on the processing screen
- [ ] Before/after quotes are populated
- [ ] The accessibility list shows real slide numbers
- [ ] Both download buttons work

**Accessibility of our own app** — we would look silly failing this
- [ ] Tab through every screen; focus is always visible
- [ ] The skip link works
- [ ] Turn on VoiceOver (⌘F5) and confirm the step nav and the review queue are
      navigable

### Known rough edges (say these before a judge finds them)

- Review items caught by the decorative guard show **"5 of 5"** next to "Needs a
  human". That is accurate — the model is confident in the *description*; what
  is being challenged is its decision to silence the image — but it reads oddly.
- The 200 MB limit is stated in the UI and not enforced by the server.
- Approving rewrites the whole `.pptx` each time. Fine for a demo, slow for a
  300-image deck.

---

## 3. The two decks to demo

Pick these two. Both are **real ASU course material**, which matters — we are
pitching to ASU.

### Primary: `U1_Introduction to Machine Learning (1).pptx`

**This is the demo.** 23 images, about 50 seconds — short enough to run live.

- **The "before" is visceral.** Slide 13's existing alt text is
  `C:\Users\symbiosis\Desktop\IB2COM\box_fls.png`. A blind student in that
  course hears a Windows directory read out letter by letter. We did not invent
  that; it is in the file the professor shipped.
- **The review queue actually fills** — 11 of 23 images, nearly half. They are
  photographs of cats, dogs and a puppy on a *feature-extraction* slide, where
  the images are the raw data being taught. Our guard caught our own tool trying
  to silence them.
- Only 6 accessibility issues, so the results screen stays readable.

Run it live, then open the review queue and read one "why flagged" aloud.

### Secondary: `chapter2 for online instruction Part 1 (student).pptx`

PHY 111 physics. 23 images, about 45 seconds — the fastest deck we have.

- **Not computer science**, which answers "does this only work on CS slides?"
- **23 of 23 described**, nothing silenced — physics decks are all content, so
  it shows the classifier is not just firing at a fixed rate.
- **A second flavour of bad "before":** 7 images already have alt text, and it
  is figure codes — `0202a`, `0203`, `0205b`. Useless to a screen reader, and a
  naive tool that skips images "that already have alt text" would skip all seven.
- It reads handwritten derivations and position-time graphs accurately, which is
  the description-quality argument.

### Deliberately not the demo

- **`stanford_cs106b_fundamentals.pptx`** — 65 of 71 images silenced, which is a
  great *statistic* (a briefcase icon repeated 37 times). But only 5 images get
  described, so a live run looks like it did almost nothing. **Quote the number
  on a slide; do not run it.**
- **`mit_ai101_eecs.pptx`** — where we found the false positives, but it takes
  97 seconds and it is MIT's, not ASU's.
- **`September 8th-CSE 511.pptx`** — 91 images, too long to run live.

### Backup plan

If the gateway is slow or down on the day, run
`.venv/bin/python -m slidesight <deck> --wcag-only`. It needs no API key and no
network, and still produces a real accessibility report. Have a
pre-remediated deck and its report saved locally too, so you can show results
without a live run.

---

## The API, if you need it

The web UI in `web/` uses only these:

```
POST /api/upload                              -> {job_id}
GET  /api/jobs/{id}                           -> progress, then the full report
GET  /api/jobs/{id}/thumb/{slide}/{image_id}  -> the image being reviewed
POST /api/jobs/{id}/approve                   -> {slide, image_id, alt_text}
GET  /api/jobs/{id}/download                  -> the remediated .pptx
GET  /api/jobs/{id}/report                    -> report JSON
```

Every image in the report is one record:

```json
{"slide": 7, "image_id": "shape_4", "alt_text": "...", "confidence": 5,
 "decorative": false, "reason": null, "action": "auto_applied"}
```

`action` is `auto_applied`, `review_queue`, `decorative_empty_alt`, or
`human_approved` once you approve one. Bad uploads return `{"error": "..."}`
with a message already written for a human — show it as-is.

# SlideSight — build status and review

Written 3 Sep 2026, 3:10 PM MST. Code freeze 6 PM, submission 11:59 PM.

This is the honest state of the project: what exists, how it works, what has
been proven, what has not, and what is still owed. Read the "Not proven" and
"Still owed" sections before writing anything for the pitch.

---

## 1. What it does

A professor uploads a `.pptx`. SlideSight finds every image, writes real alt
text using a vision model on ASU Research Computing hardware, and writes it back
into the file. It applies only what the model is confident about; everything
else is held for a human. It also detects five other accessibility problems and
reports them without touching them.

Three behaviours, in order of how much they matter:

1. **Confidence gate.** The model scores its own certainty 1–5 in the same call
   that produces the description. 4–5 is written into the file. 1–3 is held in a
   review queue with the model's stated reason. It does not guess silently.
2. **On-premise inference.** Lecture decks are unpublished faculty IP, and some
   carry graded student work. Those cannot go to a commercial API as a matter of
   policy. All inference stays on ASU hardware.
3. **Decorative silencing.** Logos and icons get empty alt text so screen
   readers skip them. A briefcase icon repeated across 40 slides should be
   silent, not announced 40 times.

Prior art already generates pptx alt text. The gate, the human queue, and
on-premise inference are the parts that are ours.

---

## 2. Status at a glance

| Area | State |
|---|---|
| Extraction (incl. images nested in groups) | ✅ Done, verified |
| Vision descriptions via ASU AIR | ✅ Done, verified on 405 images |
| Confidence gate + review queue | ✅ Done, fires on real decks |
| Decorative detection + silencing | ✅ Done, verified |
| Write-back into the file | ✅ Done, verified in 3 readers |
| Accessibility (WCAG) checks — 5 of 6 | ✅ Done, verified |
| Contrast check | ❌ Cut, deliberately (see §7) |
| Second "critique" pass | ❌ Cut, deliberately (see §7) |
| Batch evaluation harness | ✅ Done |
| Streamlit UI | ⬜ Person B, not started here |
| Screen reader run end to end | ⬜ **Not done — needs a human** |
| Tested in real PowerPoint | ⬜ **Not done — not installed** |
| Pitch deck / video / written answers | ⬜ **Not started** |
| Progress report filed | ⬜ **Unknown — check today** |
| Team size 3–5 vs our 2 | ⬜ **Unresolved — biggest risk** |

11 commits, ~1,480 lines of Python. Repo:
[github.com/shrey-Bish/ASU-AIR](https://github.com/shrey-Bish/ASU-AIR)

---

## 3. How it works

```
.pptx ─> extract ─> describe ─> triage ─> write back ─> .pptx + report.json
         (recurse    (vision     (conf.    (descr=…,      + WCAG report
          groups)     model)      gate)     strip title)
```

| File | Lines | Responsibility |
|---|---|---|
| `slidesight/extract.py` | 159 | Walk every shape recursing into groups; pull each image plus its own slide's title, body, notes. |
| `slidesight/describe.py` | 347 | One vision call per image → description, decorative flag, confidence, reason, and what it can literally read. Parses and salvages the reply, cross-checks it. |
| `slidesight/apply.py` | 89 | The confidence gate and write-back to the OOXML `descr` attribute. |
| `slidesight/pipeline.py` | 162 | Async orchestration, bounded concurrency, streaming callback, safe file opening. |
| `slidesight/wcag.py` | 236 | Five detection-only accessibility checks. No model calls. |
| `slidesight/cli.py` | 162 | Command line, progress output, input validation. |
| `scripts/evaluate.py` | 122 | Batch-runs a folder of decks, writes the summary the results table comes from. |
| `scripts/make_review_demo.py` | 124 | Builds a deliberately degraded deck so the gate has something to catch on stage. |

### Decisions that matter

- **Context is per-slide, not per-deck.** Sending all 50 slides of text with
  every image dilutes the signal. A single ~200-word deck summary is generated
  once and prepended instead.
- **Confidence is 1–5, not 0–100.** Models do not calibrate to a hundred points;
  you get meaningless clusters at 85/90/95.
- **Decorative is decided before describing.** Deciding it afterwards made the
  model treat "I can identify this logo clearly" as "this is worth describing."
- **Nothing destructive is ever auto-fixed.** Alt text is additive. Colour and
  font size are not, so those are reported only.

### Models (see MODELS.md)

| Role | Model | Calls |
|---|---|---|
| Image description | `qwen3-vl-32b-instruct` | one per image |
| Deck summary | `gemma4-31b-it` | one per deck |

Endpoint `https://openai.rc.asu.edu/v1`, key from `.env`, one per person, never
committed.

---

## 4. WCAG checks — what is and is not implemented

Five of the six checks in the plan are done. All are **detection only** —
nothing in this list modifies the deck.

| Check | Implemented | What it finds |
|---|---|---|
| `missing_title` | ✅ | Slides with no title placeholder or an empty one. A text box that merely *looks* like a title does not count — screen readers navigate by the placeholder. |
| `small_text` | ✅ | Body text under 18pt, resolved against the layout placeholder when the run inherits its size. Titles exempt. |
| `table_no_header` | ✅ | Tables with no header row. |
| `vague_link` | ✅ | "click here", "read more" — screen reader users navigate by link list. |
| `reading_order` | ✅ | Shapes announced in XML order rather than visual order. A deck can look right and read out backwards. |
| **contrast** | ❌ **Not implemented** | Cut deliberately. PowerPoint colours are usually theme references with tint maths, and text over a photo has no computable ratio. It was first on the plan's cut list. |

Run them alone, no API key and no network needed:

```bash
.venv/bin/python -m slidesight lecture.pptx --wcag-only
```

This is also the graceful-degradation path: if the AIR gateway is down, this is
still a working accessibility tool.

**Both checks that looked wrong were verified rather than trusted:**
`missing_title` fired on ~50% of slides — real, confirmed by finding text boxes
posing as titles. `vague_link` returned zero on one deck set — a correct
negative; it had found 16 hyperlinks and judged all of them descriptive.

---

## 5. Evidence

### Evaluation run — 9 real university decks

Five ASU course decks, two MIT OpenCourseWare, two Stanford CS106B.
**517 slides, 405 images, 514 seconds.**

| | Count |
|---|---|
| Images found | 405 |
| Alt text applied automatically | 213 |
| Marked decorative (silenced) | 187 |
| Sent to human review | 5 |
| Tables detected (reported, not fixed) | 4 |
| WCAG issues detected | 590 |

Confidence spread: 274 at 5, 126 at 4, 2 at 3, 3 at 2.
WCAG breakdown: 240 small text, 210 reading order, 135 missing titles,
3 tables without headers, 2 vague links.

| Deck | Slides | Images | Applied | Decor. | Review | WCAG | Time |
|---|---|---|---|---|---|---|---|
| ASU CSE 450 (algorithms) | 66 | 10 | 4 | 5 | 1 | 114 | 18s |
| ASU CSE 551 (algorithms) | 60 | 6 | 1 | 5 | 0 | 131 | 12s |
| ASU CSE 511 (data processing) | 49 | 91 | 57 | 30 | 4 | 54 | 111s |
| ASU Intro to Machine Learning | 19 | 23 | 8 | 15 | 0 | 6 | 40s |
| ASU Unsupervised Learning | 37 | 22 | 15 | 7 | 0 | 14 | 37s |
| MIT AI 101 | 54 | 77 | 66 | 11 | 0 | 48 | 107s |
| MIT CMS.595 Media Studies | 23 | 52 | 28 | 24 | 0 | 47 | 65s |
| Stanford CS106B fundamentals | 102 | 71 | 5 | 66 | 0 | 84 | 53s |
| Stanford CS106B welcome | 107 | 53 | 29 | 24 | 0 | 92 | 71s |

### Write-back verified in three independent readers

- **python-pptx** — reopened after save: 23/23 alt texts present, zip integrity
  intact, source file unmodified, 0 leftover filename `title` attributes.
- **Keynote** — opens a remediated deck with no repair prompt.
- **LibreOffice Impress** — read and re-saved the file; **23/23 descriptions
  preserved byte-identical.** A separate OOXML implementation reading our
  `descr` field is real evidence it is written where a conforming reader looks.

### The confidence gate fires on real input

All five review items are genuine low confidence, four from one ASU deck:

> "The image is extremely blurry and cropped, showing only a portion of what
> appears to be the digit…"

> "The description infers context (data records in external storage) from the
> lecture topic and slide text rather than reading it in the image."

The second is the cross-check catching the model leaning on slide text.

### Calibration was tested, not assumed

Degrading a known image by measured amounts moves confidence the right way:

| Image condition | Confidence | Routed to |
|---|---|---|
| Clean | 4–5 | applied |
| Gaussian blur r=6 | 3 | review |
| Gaussian blur r=14 | 2 | review |

`scripts/make_review_demo.py` blurs exactly one image in a real deck, leaving
every other byte identical. Result: clean `8 applied / 15 decorative / 0 review`
→ blurred `7 applied / 15 decorative / 1 review`. One variable changed, one
outcome changed.

---

## 6. Bugs found by running real decks — all fixed

Each of these was making the tool quietly wrong, and each was caught by running
real material rather than by reading the code.

| Bug | Effect | Fix |
|---|---|---|
| `notes_text_frame` can be `None` when a notes slide exists | Extraction crashed on one MIT deck | Guard for `None` |
| TIFF and BMP rejected as "unsupported" | 26 images in one deck went to review as failures — **a queue full of things a human could not act on** | Pillow re-encodes them; only undecodable vector art now goes to review |
| Replies truncated by the token limit were discarded | 3 good descriptions reported as low-confidence failures | Salvage the fields from partial JSON; token cap raised |
| Model copied values from slide text | Confident, invented values on an illegible image | Model reports what it can literally read; mechanical cross-check caps confidence at 3 |
| Decorative decided after describing | Only 1 of 15 images silenced; 5 logos described at confidence 5 | Decide decorative first → 8 of 15 silenced, runtime halved |
| PDFs and mislabelled files | Raw `python-pptx` traceback | Plain-English `ValueError`; four cases tested |

---

## 7. Not proven, and deliberately not built

**Not proven — do not claim these:**

- **No screen reader has been run end to end.** The XML is right and three
  readers preserve it, but nobody has heard VoiceOver or NVDA read a remediated
  deck. Steps are in [DEMO.md](DEMO.md); it needs a human keypress (⌘F5).
- **PowerPoint itself is untested.** It is not installed on the dev machine and
  installing needs an admin password: `brew install --cask microsoft-powerpoint`.
  Keynote and LibreOffice both work.
- **The model can still be fooled.** Given an illegible image plus *matching*
  slide text, a well-worded caption can carry a wrong description past the gate.
  Mitigated, not eliminated. This is the most important known weakness.

**Deliberately not built** (both first on the plan's own cut list):

- **Contrast checking.** Theme colours with tint maths; text over photos has no
  computable ratio.
- **Second critique pass.** Optional in the plan, and all the unknowns live in
  it.

**Out of scope by design:**

- **PDF.** The tool rejects it with a message pointing at ASU CIC's existing
  PDF tool. This is scope discipline, not an oversight.

**Coverage gap:** 9 decks across ~4 subject areas, heavily computer science. The
plan asks for 20–30 decks from five or more departments.

---

## 8. Still owed

### Submission deliverables — none of these are code

| Item | Est. | Note |
|---|---|---|
| **Progress report filed** | 10 min | Plan says missing it risks disqualification |
| **Team size 3–5 vs our 2** | — | Plan says message organisers immediately. **Biggest single risk to the submission.** |
| Pitch deck (Google Slides/Canva — a GitHub PDF is explicitly disallowed) | ~1.5 hr | |
| 90-second video on YouTube | ~1 hr | Script ready in DEMO.md |
| Written submission answers | ~1 hr | |
| Public repo + README | ✅ done | |
| MODELS.md with exact AIR model IDs | ✅ done | |

### Code

| Item | Owner |
|---|---|
| Streamlit UI — upload, progress, review queue, download | Person B |
| Screen reader test on before/after | Person B (plan §12) |
| More decks, more departments | Person B |

---

## 9. Reproducing everything

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
printf 'RC_LLM_API_KEY=%s\n' "$YOUR_KEY" > .env

# one deck
.venv/bin/python -m slidesight lecture.pptx -o out/lecture.remediated.pptx

# accessibility checks only, no key needed
.venv/bin/python -m slidesight lecture.pptx --wcag-only

# the full evaluation table in §5
.venv/bin/python scripts/evaluate.py decks -o out/eval

# the review-queue demo deck
.venv/bin/python scripts/make_review_demo.py "decks/<a deck>.pptx" -o decks_demo -r 12
```

Docs: [README.md](README.md) overview and results · [MODELS.md](MODELS.md) model
IDs and why AIR · [INTEGRATION.md](INTEGRATION.md) the pipeline→UI contract ·
[DEMO.md](DEMO.md) the pitch script and what not to claim.

---

## 10. What I would do with the remaining hours

1. File the progress report and message the organisers about team size. Neither
   is code and both can sink the submission.
2. Install PowerPoint, open a remediated deck, run VoiceOver once, record it.
   That is the pitch's best 15 seconds and the one claim still unverifiable.
3. Person B: the review queue is the centrepiece. Make it the first thing on
   screen, not below the fold.
4. Only then: more decks, more departments.

The tool is in good shape. The deliverables are the risk now, not the code.

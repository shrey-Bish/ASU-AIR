# SlideSight — build status and review

Written 3 Sep 2026, 4:51 PM MST. Code freeze 6 PM, submission 11:59 PM.

This is the honest state of the project: what exists, how it works, what has
been proven, what has not, and what is still owed. Read the "Not proven" and
"Still owed" sections before writing anything for the pitch.

---

## 1. What it does

A professor uploads a `.pptx` — in the browser app or from the command line.
SlideSight finds every image, writes real alt text using a vision model on ASU
Research Computing hardware, and writes it back into the file. It applies only what the model is confident about; everything
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
| Vision descriptions via ASU AIR | ✅ Done, verified on 380 images |
| Confidence gate + review queue | ✅ Done, 17 items on real decks |
| Decorative detection + silencing | ✅ Done, guarded by two signals (§5) |
| Write-back into the file | ✅ Done, verified in 3 readers |
| Accessibility (WCAG) checks — 5 of 6 | ✅ Done, verified |
| Screen-reader audio preview (before/after) | ✅ Done, working |
| Contrast check | ❌ Cut, deliberately (see §7) |
| Second "critique" pass | ❌ Cut, deliberately (see §7) |
| Batch evaluation harness | ✅ Done |
| Web app (upload → review → download) | ✅ Done, verified end to end |
| Review queue: thumbnails + approve-to-file | ✅ Done |
| VoiceOver run end to end | ⬜ **Not done — needs a human keypress** |
| Opens in real PowerPoint | ✅ Installed; both decks open with no repair prompt |
| Alt Text pane confirmed in PowerPoint | ⬜ **Needs a human to look** |
| Pitch deck / video / written answers | ⬜ **Not started** |
| Progress report filed | ⬜ **Still open — do this first** |
| Team size 3–5 vs our 2 | ✅ Confirmed OK |

25 commits, ~2266 lines of Python (pipeline, server and scripts). Repo:
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
| `slidesight/extract.py` | 177 | Walk every shape recursing into groups; pull each image plus its own slide's title, body, notes. |
| `slidesight/describe.py` | 347 | One vision call per image → description, decorative flag, confidence, reason, and what it can literally read. Parses and salvages the reply, cross-checks it. |
| `slidesight/apply.py` | 113 | The confidence gate and write-back to the OOXML `descr` attribute. |
| `slidesight/pipeline.py` | 162 | Async orchestration, bounded concurrency, streaming callback, safe file opening. |
| `slidesight/wcag.py` | 236 | Five detection-only accessibility checks. No model calls. |
| `slidesight/cli.py` | 162 | Command line, progress output, input validation. |
| `scripts/evaluate.py` | 122 | Batch-runs a folder of decks, writes the summary the results table comes from. |
| `scripts/make_review_demo.py` | 124 | Builds a deliberately degraded deck — kept as calibration evidence. |
| `server/main.py` + `jobs.py` | 400 | FastAPI: upload, progress, thumbnails, approve, download. Runs each job on a worker thread so the model calls do not starve the event loop. |
| `web/` (html, css, js) | 700 | The browser UI, built from the approved design and served by the same app. |
| `scripts/screen_reader_preview.py` | 98 | Speaks what a screen reader announces before and after, via the macOS `say` voice. Can save audio for the video. |

### Where things live

```
slidesight/  the pipeline       server/     FastAPI app (upload, review, approve, download)
web/         the browser UI     scripts/    evaluate · make_review_demo · screen_reader_preview
fixtures/    sample report      decks/      the 10 test decks
demo-decks/  the 2 demo decks   out/        generated output
data/        legacy-ppt · demo · pdfs · challenge · design-source
```

`decks/`, `out/` and `data/` are gitignored. `demo-decks/` is **not** — the two
demo decks are committed so the team can pull them, and they are ASU course
material that should come out before the repo is shared widely. The repo
otherwise carries code, docs, and `out/eval/eval_summary.json` as the evidence
behind §5.

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

### Evaluation run — 10 real university decks

Eight ASU course decks (five computer science, **three PHY 111 physics**), one MIT OpenCourseWare, one Stanford CS106B.
**505 slides, 380 images, 556 seconds.**

| | Count |
|---|---|
| Images found | 380 |
| Alt text applied automatically | 228 |
| Marked decorative (silenced) | 122 |
| Sent to human review | 30 |
| WCAG issues detected | 531 |

Confidence spread: 238 at 5, 137 at 4, 4 at 3, 1 at 2. Every column above sums to the
per-deck table below.

WCAG breakdown: 197 small text, 183 reading order, 148 missing titles,
3 tables without headers.

### Silencing is the dangerous decision — and it was unguarded

Reviewed every image the model silenced. Two findings.

**Mostly right, and the headline number is misleading in a good way.** Stanford
CS106B silenced 66 images, but they are only **5 unique pictures**: a briefcase
icon repeated 37 times, an arrow 26 times, plus the Stanford seal, the C++ logo
and a stock photo. Both ASU algorithms decks silenced exactly 2 unique images
each — the ASU Fulton logo and a divider bar. Quote "66 silenced" as "37 copies
of one icon a student would otherwise hear announced", not as 66 judgements.

**But MIT AI 101 had real false positives.** Photographs of cats, dogs and a
crawling baby were called decorative on slides reading *"1. Define a problem"*,
*"6. Test the model"*, and *"three types of learning"*. In a machine-learning
course those animals **are** the teaching content; silencing them deletes the
slide's point, and by design it never reached a human.

**Fix, now shipped:** a decorative verdict is checked against two independent
signals, and failing either sends the image to a human instead of silencing it.

* **Size** — anything over 12% of the slide. Logos and dividers are small; a
  chart is not.
* **Photograph or flat graphic** — the better of the two. Size alone missed a
  **1%-of-slide dog photograph** that was the raw input in a feature-extraction
  diagram: tiny, and entirely the point of the slide. Measured on images
  verified by eye, decorative art tops out at **843 distinct colours** while
  teaching photographs start at **3,324**. The threshold sits in that gap.

Together these reroute 30 images, and they close the gap completely: **MIT AI
101 now silences nothing at all** — every one of its 77 images is either
described or sent to a human, so none of the twelve teaching photographs can be
lost. The size guard alone had caught nine of the twelve; the colour signal
caught the remaining three, including a cat at 6.7% of the slide and another at
1%.

**Reading the per-deck table.** All figures below are from the current run, with
both guards on. For MIT AI 101 — the deck where the problem was found — that is
**68 applied, 0 decorative, 9 review**. Before either guard existed the same
deck read 66 applied / 11 decorative / 0 review, so the eleven silenced images
became nine reviews plus two the model simply described instead. Quote the
current row; the pre-guard figures are history, not a second measurement.

**Which per-deck numbers are stable.** The two guards are deterministic: on ASU
intro machine learning, all eleven review items are decorative calls the guard
intercepted, none are low-confidence, so that deck's 15 → 4 decorative swing is
entirely the guard. The model itself is not deterministic at temperature 0.2,
and small decks show it: CSE 450 moved 4 → 2 applied with three images landing
at confidence 3 instead of 4, and CSE 551 flipped one of its six images between
runs. **Totals and guard-driven figures are safe to quote; single-image
movements on ten-image decks are not.**


| Deck | Slides | Images | Applied | Decor. | Review | WCAG | Time |
|---|---|---|---|---|---|---|---|
| ASU CSE 450 — algorithms | 66 | 10 | 2 | 5 | 3 | 114 | 36.6s |
| ASU CSE 551 — algorithms | 60 | 6 | 0 | 6 | 0 | 131 | 20.8s |
| **ASU PHY 111 — physics ch.5** | 29 | 24 | 23 | 0 | 1 | 29 | 62.2s |
| ASU CSE 511 — data processing | 49 | 91 | 51 | 35 | 5 | 54 | 64.5s |
| ASU — intro machine learning | 19 | 23 | 8 | 4 | 11 | 6 | 50.4s |
| ASU — unsupervised learning | 37 | 22 | 15 | 7 | 0 | 14 | 26.4s |
| **ASU PHY 111 — physics ch.2 pt1** | 47 | 23 | 23 | 0 | 0 | 19 | 45.5s |
| **ASU PHY 111 — physics ch.2 pt2** | 42 | 33 | 33 | 0 | 0 | 32 | 92.4s |
| MIT AI 101 — EECS | 54 | 77 | 68 | 0 | 9 | 48 | 97.2s |
| Stanford CS106B — fundamentals | 102 | 71 | 5 | 65 | 1 | 84 | 58.6s |
| **Total** | **505** | **380** | **228** | **122** | **30** | **531** | **556s** |

**The three physics decks silenced nothing — 0 decorative across 80 images, 79
of 80 described.** That is the right answer: PHY 111 slides are motion diagrams,
graphs and worked equations, with no logo furniture. Set against Stanford
CS106B, where 65 of 71 images are template icons, it is evidence the classifier
tracks what an image *is* rather than firing at a fixed rate.

### The web app, verified end to end

Upload → progress → review → download, exercised against the real API on the ASU
machine-learning deck: 23 images, 8 applied, 4 silenced, **11 to review**. A
thumbnail loads for each review item, editing the draft and approving writes the
text into the deck, and downloading returns a file that contains it.

Two things that had to be fixed to get there, both in the handover code:

- **Job ids did not match.** Upload minted one id for the temp directory while
  the registry minted another internally, so the id handed to the browser
  addressed nothing and every poll returned 404. Nothing would have worked.
- **The review queue had no backend.** The design has an approve button, but
  there was no endpoint to write a description or to show the image being
  judged. Both added.

### Write-back verified in three independent readers

- **python-pptx** — reopened after save: 23/23 alt texts present, zip integrity
  intact, source file unmodified, 0 leftover filename `title` attributes.
- **Keynote** — opens a remediated deck with no repair prompt.
- **LibreOffice Impress** — read and re-saved the file; **23/23 descriptions
  preserved byte-identical.** A separate OOXML implementation reading our
  `descr` field is real evidence it is written where a conforming reader looks.

### Hearing it, without VoiceOver

`scripts/screen_reader_preview.py` speaks what a screen reader announces for
each image, before and after, using the macOS `say` engine. **Verified working.**
On slide 13 of the ASU machine-learning deck:

> **BEFORE:** "C:\Users\symbiosis\Desktop\IB2COM\box_fls.png"
> **AFTER:** "Laparoscopic surgery simulator with a monitor displaying a virtual
> surgical environment showing colorful anatomical structures and tools…"

That before is not invented. PowerPoint auto-filled the alt text with the source
file path, so a student in that course hears a Windows directory read out.

It is a preview, not proof — it reads the file the same way we wrote it, so it
does not independently confirm PowerPoint exposes the field. `--save` writes
audio files for the pitch video.

### The confidence gate fires on real input

30 review items, most from the decorative guards, the rest genuine low confidence:

> "The image is extremely blurry and cropped, showing only a portion of what
> appears to be the digit…"

> "The description infers context (data records in external storage) from the
> lecture topic and slide text rather than reading it in the image."

The second is the cross-check catching the model leaning on slide text.

**On the threshold.** The model answers 5 for 238 images and 4 for 137.
Auto-applying 4-and-above is deliberate: requiring 5 would send another 137
images — **36% of the corpus** — to a human, far more than a reviewer can
absorb. If a
judge asks whether a gate that rarely fires is doing real work, the calibration
table above is the answer — it responds to degradation, so a low rate means
clean inputs, not a dead gate.

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
| **Decorative verdicts were never second-guessed** | **Teaching photos in an AI course silently deleted from the accessible version — the most harmful failure in the system, and invisible by design** | A decorative call now fails two independent checks: image over 12% of the slide, **or** photographic rather than flat graphic (distinct-colour count). Either sends it to a human. |
| Size alone was the wrong signal for that guard | A dog photograph at **1% of the slide** — the raw input on a feature-extraction slide, and the entire point of it — was still being silenced | Colour count separates the populations cleanly: verified decorative art tops out at 843 distinct colours, teaching photographs start at 3,324 |
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
- **PowerPoint opens the files, but the Alt Text pane has not been eyeballed.**
  PowerPoint 16.112 is now installed, and both the original and remediated decks
  open with no repair prompt. What nobody has done is right-click an image →
  View Alt Text and confirm the description is sitting there. Ten seconds, and
  it converts "verified in three OOXML readers" into "verified in PowerPoint".
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

**Coverage gap:** 10 decks across two departments — five computer science, three
physics, two general machine learning — plus MIT and Stanford CS. The plan asks
for 20–30 decks from five or more departments, so the count and the department
spread are both short. Deliberate: at this point ten decks with a false-positive
analysis is worth more than twenty without one.

---

## 8. Still owed

### Submission deliverables — none of these are code

| Item | Est. | Note |
|---|---|---|
| **Progress report filed** | 10 min | Plan says missing it risks disqualification. **Still open.** |
| ~~Team size 3–5 vs our 2~~ | — | ✅ Confirmed OK with organisers |
| Pitch deck (Google Slides/Canva — a GitHub PDF is explicitly disallowed) | ~1.5 hr | |
| 90-second video on YouTube | ~1 hr | Script ready in DEMO.md |
| Written submission answers | ~1 hr | |
| Public repo + README | ✅ done | |
| MODELS.md with exact AIR model IDs | ✅ done | |

### Code

| Item | Owner |
|---|---|
| ~~UI — upload, progress, review queue, download~~ | ✅ Built and wired |
| Host it, test it, run the demo decks | Person B — see [NEXT_STEPS.md](NEXT_STEPS.md) |
| Screen reader test on before/after | Person B (plan §12) |
| ~~More decks, more departments~~ | Dropped — 10 decks with a false-positive analysis beats 20 without |

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
.venv/bin/python scripts/make_review_demo.py "decks/<a deck>.pptx" -o data/demo -r 12
```

Docs: [README.md](README.md) overview and results · [MODELS.md](MODELS.md) model
IDs and why AIR · [DEMO.md](DEMO.md) the pitch script and what not to claim ·
[NEXT_STEPS.md](NEXT_STEPS.md) hosting, the test checklist, and the two demo decks.

---

## 10. What I would do with the remaining hours

1. **File the progress report.** Ten minutes, still open, and the plan says
   missing it risks disqualification.
2. **Two checks in PowerPoint, ten minutes total.** Right-click the image on
   slide 13 of a remediated deck → View Alt Text, and confirm the description is
   there. Then ⌘F5 and hear it. Both decks are already open. That closes the
   last unverified claim and gives you the video's best fifteen seconds.
3. **Person B: host it and run the checklist** in [NEXT_STEPS.md](NEXT_STEPS.md).
   Demo from localhost — hosting adds risk on the day and buys nothing a judge
   sees.
4. **Not** more decks. Ten decks with a false-positive analysis beats twenty
   without one. The coverage gap belongs on the limitations slide, not in the
   remaining hours.

The tool is in good shape. The deliverables are the risk now, not the code.

# SlideSight

Accessibility remediation for PowerPoint lecture decks, running entirely on ASU
Research Computing hardware.

A blind student opening a lecture deck hears `"shape 4"` where everyone else
sees a revenue chart. SlideSight finds every image in a `.pptx`, writes real alt
text with a vision model, and writes it back into the file — but only when the
model is confident. Everything else goes to a human review queue instead of
being silently guessed.

Built for the ASU AIR Spark Challenge.

## What makes this different

Generating alt text for PowerPoint is not new (see [prior art](#prior-art)).
Two things here are:

1. **A confidence gate.** The model scores its own certainty 1–5 in the same
   call that produces the description. 4–5 is written to the file; 1–3 is held
   for a human with the model's stated reason. The tool knows when it does not
   know.
2. **On-premise inference.** Lecture decks are unpublished faculty intellectual
   property, and some carry graded student work. Those cannot go to a commercial
   API as a matter of policy, not preference. All inference stays on ASU
   hardware.

A third behaviour matters more than it sounds: **decorative images get empty alt
text**, so screen readers skip them. A university logo repeated across 45 slides
should be silent, not announced 45 times.

## Install

Requires Python 3.11+.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Put your Research Computing key in `.env` (get one from
[voyager.rc.asu.edu](https://voyager.rc.asu.edu)):

```
RC_LLM_API_KEY=your-key-here
```

`.env` is gitignored. Never commit a key.

## Use

```bash
.venv/bin/python -m slidesight lecture.pptx -o out/lecture.remediated.pptx
```

```
Reading lecture.pptx
  slide   8  applied  c5  Two horizontal position axes labeled x(m) from -60 to 60...
  slide  25  decor.   c5  Discord brand logo, no teaching content
  slide  31  REVIEW   c2  chart axis labels are cut off at the right edge

23 images on 47 slides  ->  20 applied, 2 decorative, 1 to review   (339.0s)
Wrote out/lecture.remediated.pptx
Wrote out/lecture.remediated.json
```

| Flag | Meaning |
|---|---|
| `-o, --output` | where to write the remediated deck |
| `-r, --report` | where to write the JSON report |
| `-c, --concurrency` | parallel calls to the gateway (default 4) |
| `--no-summary` | skip the one-per-deck summary call |
| `--wcag-only` | run the accessibility checks only, no model calls |
| `--quiet` | only print the final counts |

**PowerPoint `.pptx` only.** Legacy `.ppt` is a different binary format that
`python-pptx` cannot read. Convert it first:

```bash
soffice --headless --convert-to pptx "old deck.ppt"
```

## Output contract

Every image produces one record. This is the interface between the pipeline and
the UI:

```json
{
  "slide": 7,
  "image_id": "shape_4",
  "alt_text": "Bar chart of FY24 revenue by region. Southwest leads at $4.2M, roughly double the Northeast at $2.1M.",
  "confidence": 5,
  "decorative": false,
  "reason": null,
  "action": "auto_applied"
}
```

`action` is one of `auto_applied`, `review_queue`, or `decorative_empty_alt`.

## How it works

```
.pptx ─> extract ─> describe ─> triage ─> write back ─> .pptx + report.json
         (recurse    (vision     (conf.    (descr=,
          groups)     model)      gate)     strip title)
```

| Module | Responsibility |
|---|---|
| `extract.py` | Walk every shape, recursing into groups. Pull each image plus its own slide's title, body, and speaker notes. |
| `describe.py` | One vision call per image returning description, decorative flag, confidence, and reason. |
| `apply.py` | The confidence gate, and write-back into the OOXML `descr` attribute. |
| `pipeline.py` | Async orchestration with a bounded semaphore; results stream as they land. |
| `wcag.py` | Five detection-only accessibility checks. No model calls. |

Three details that are easy to get wrong, all verified against real decks:

- **Images hide inside groups.** Iterating `slide.shapes` found 13 pictures in
  one test deck; recursing into `MSO_SHAPE_TYPE.GROUP` found 15. Missing 13% of
  the images on the first deck we tried.
- **Pictures carry a `title` attribute** holding the original filename
  (`Screenshot 2026-09-02 at 9.25.40 AM.png`). Some screen readers read it
  aloud. We strip it.
- **Context is per-slide, not per-deck.** Sending all 45 slides of text with
  every image dilutes the signal and makes descriptions vaguer. A single
  200-word deck summary is generated once and prepended instead.

## Results

Evaluated on **9 real university lecture decks** — five ASU course decks
(CSE 450 algorithms, CSE 551 algorithms, CSE 511 data processing, and two
machine-learning units), two MIT OpenCourseWare decks (AI 101, CMS.595 Media
Studies), and two Stanford CS106B decks. **517 slides, 405 images, 514
seconds.**

| | Count |
|---|---|
| Images found | 405 |
| Alt text applied automatically | 213 |
| Marked decorative (silenced) | 187 |
| Sent to human review | 5 |
| WCAG issues detected (nothing modified) | 590 |

Confidence spread: 274 at 5, 126 at 4, 2 at 3, 3 at 2. Alt text was confirmed to
persist after save and reopen, with zip integrity intact and source files
unmodified. A remediated deck opens in Keynote with no repair prompt.

WCAG issues by check: 240 instances of text under 18pt, 210 slides that read out
of visual order, 135 missing slide titles, 3 tables with no header row, 2 vague
link texts.

### The confidence gate, on real input

All five review items are genuine low confidence, and four came from one ASU
deck (CSE 511):

> "The image is extremely blurry and cropped, showing only a portion of what
> appears to be the digit..."

> "The description infers context (data records in external storage) from the
> lecture topic and slide text rather than reading it in the image."

That second one is the cross-check working: the model is caught leaning on the
slide text instead of the image, and the image goes to a human.

### The decorative result

Stanford CS106B's *fundamentals* deck has 71 images, of which **66 are
decorative** — the Stanford seal plus a briefcase icon repeated across roughly
40 slides. Without this, a blind student hears "briefcase" forty times in one
lecture.

### What did not work

**The gate fires rarely — 5 in 405 images.** Real lecture decks are mostly
clean, so this is honest rather than broken, and we deliberately did not raise
the threshold to manufacture a queue. We verified the gate *can* fire by
degrading a known image in measured steps: Gaussian blur r=6 drops confidence to
3, r=14 to 2, both landing in the review queue. `scripts/make_review_demo.py`
builds a deck with exactly one image degraded, for demonstrating this honestly.

**The model leans on slide text.** Given an illegible image plus the real slide
text, it reported values it could not possibly read. Given the *same* image with
text from an unrelated lecture, it described the wrong subject entirely. It now
reports what it can literally read, and a mechanical check caps confidence at 3
when a description quotes values absent from that list but present in the slide
text. A well-matched caption can still slip a wrong description past the gate.

**Three bugs this evaluation caught**, all fixed:
- A deck whose notes slide had no notes placeholder crashed extraction.
- 26 TIFF images in one deck were routed to review as "unsupported" when Pillow
  decodes them fine — a review queue full of things a human could not act on.
- Replies truncated by the token limit were discarded, reporting three good
  descriptions as failures. They are now salvaged, and the cap was raised.

**Not fully verified:** a remediated deck opens correctly in Keynote, but
**PowerPoint itself has not been tested** — it is not installed on the dev
machine — and no screen reader has been run end to end. See [DEMO.md](DEMO.md).

**Department coverage is thin.** 9 decks, heavily computer science. PLAN.md asks
for 20–30 across five or more departments.

## Accessibility report

Alongside alt text, SlideSight detects five issues it deliberately does **not**
fix. Alt text is additive — filling an empty field breaks nothing. Changing a
professor's colours or type sizes hands back a deck they do not recognise. So
these are reported with slide numbers for a human to decide:

| Check | What it finds |
|---|---|
| `missing_title` | Slides with no title placeholder, or an empty one. Screen readers navigate by title, and a text box that merely *looks* like a title does not count. |
| `small_text` | Body text under 18pt, resolved against the layout placeholder when the run inherits its size. |
| `table_no_header` | Tables with no header row, leaving a screen reader no column context. |
| `vague_link` | "click here", "read more" — screen reader users navigate by link list. |
| `reading_order` | Shapes are announced in XML order, not visual order. A deck can look right and read out backwards. |

Run them alone, with no API key and no network:

```bash
.venv/bin/python -m slidesight lecture.pptx --wcag-only
```

This is also the graceful-degradation path: if the gateway is unreachable, this
alone is still a working accessibility tool.

**Contrast is not implemented.** PowerPoint colours are usually theme references
with tint maths, and text over a photograph has no computable ratio. It was
first on the cut list and it got cut.

## Limitations

- PowerPoint only. PDF remediation needs tag trees and reading order — a much
  larger problem, and ASU's CIC has already built a funded version.
- Tables are detected and reported, never remediated. They have their own
  accessibility requirements.
- Vector images (EMF/WMF) cannot be read by the vision model. They are routed to
  the review queue rather than guessed at.
- Images are downscaled to 1280px before encoding. Very fine print in a
  high-resolution screenshot may be lost.

## Prior art

- [`waltervanheuven/auto-alt-text`](https://github.com/waltervanheuven/auto-alt-text)
  — generates pptx alt text with a VLM and produces a report. The closest
  existing work. No confidence gate, no review queue.
- [`ASUCICREPO/PDF_Accessibility`](https://github.com/ASUCICREPO/PDF_Accessibility)
  — ASU AI Cloud Innovation Center's PDF remediation tool, built with Ohio State
  Libraries. Source of the ~$3–4/page manual remediation cost figure.
- [`Width-ai/powerpoint-generative-ai`](https://github.com/Width-ai/powerpoint-generative-ai)
  — includes a `create_alt_text_for_powerpoint` method.

## Models

See [MODELS.md](MODELS.md) for exact model IDs and why each is used.

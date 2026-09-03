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

Evaluated on **10 real university lecture decks** — eight ASU course decks
(CSE 450, CSE 551, CSE 511, two machine-learning units, and **three PHY 111
physics decks**), MIT's AI 101, and Stanford CS106B.
**505 slides, 380 images, 478 seconds.**

| | Count |
|---|---|
| Images found | 380 |
| Alt text applied automatically | 222 |
| Marked decorative (silenced) | 141 |
| Sent to human review | 17 |
| WCAG issues detected (nothing modified) | 531 |

Confidence spread: 232 at 5, 144 at 4, 4 at 3. Write-back verified in three
independent readers — reopened in `python-pptx` with zip integrity intact and
the source unmodified, opened in **Keynote** with no repair prompt, and
round-tripped through **LibreOffice Impress with all 23 descriptions preserved
byte-identical**. **PowerPoint itself has not been tested** — it is not
installed on the dev machine.

### Silencing an image is the dangerous decision

A bad description gets read by a human and fixed. A wrongly-silenced diagram is
removed from the blind student's experience entirely — and a confidence gate on
descriptions does nothing to protect it.

We found this the hard way. Reviewing the images the model called decorative,
most were exactly right: Stanford CS106B's *fundamentals* deck silenced 66
images, but those are only **5 unique pictures** — a briefcase icon repeated 37
times, an arrow 26 times, plus the Stanford seal, the C++ logo and a stock
photo. Without silencing, a student hears "briefcase" thirty-seven times.

But MIT's AI 101 deck was a different story. Photographs of cats, dogs and a
crawling baby were called decorative — on slides reading *"1. Define a
problem"*, *"6. Test the model"*, and *"three types of learning: supervised,
unsupervised, reinforcement"*. In a machine-learning course **those animals are
the teaching content**. Silencing them deletes the point of the slide.

So a decorative verdict is no longer trusted on its own. Any image covering more
than 12% of the slide goes to human review instead of being silenced, with the
reason stated. Logos and template icons run 1–8% of slide area and are
unaffected; this reroutes 9% of previously-silenced images.

**Why 12%, and what it still misses.** The two populations were measured, not
guessed. Images we confirmed by eye as genuinely decorative — logos, template
icons, dividers — run **2.0-8.6%** of slide area, with one outlier at 14.1% (a
full-width stock photo). The AI 101 teaching photos wrongly silenced run
**10.3-42.7%**. The populations *overlap*, so there is no clean line; 12% is a
tradeoff placed inside that overlap.

The cost is explicit: **it catches 9 of the 12 AI 101 misclassifications, not
all of them.** A cat photo at 6.7% on a slide reading "2. Find data" is still
silenced, because no size threshold that catches it would leave the queue
usable. Size is a proxy for importance and an imperfect one. Repetition was
tested as a second signal -- decorative icons repeat, content usually does not
-- but it pushes 67 more images into review, most of them genuine one-off
logos, so it was rejected as a queue flood.

### The confidence gate

17 images reached the review queue — most caught by the decorative guard above,
the rest by genuinely low confidence:

> "The image is extremely blurry and cropped, showing only a portion of what
> appears to be the digit…"

> "The description infers context from the lecture topic and slide text rather
> than reading it in the image."

The gate was calibrated rather than assumed. Degrading a known image moves
confidence the right way — Gaussian blur r=6 → 3, r=14 → 2, both landing in
review — so a low rate reflects clean source decks, not a dead gate.
`scripts/make_review_demo.py` reproduces this on demand.

On the threshold: the model returns 5 for 232 images and 4 for 144. Auto-applying
4-and-above is a deliberate choice; requiring 5 would route another 144 images
(38% of the corpus) to a human, which is more than a reviewer can absorb.

### Bugs found by running real decks

Every one of these was found by running real material, not by reading code.

| Bug | Effect | Fix |
|---|---|---|
| Decorative verdicts were never second-guessed | Teaching photos in an AI course silently deleted from the accessible version | Decorative calls on images >12% of slide area go to review |
| TIFF and BMP rejected as "unsupported" | 26 images went to review as failures — a queue full of items a human could not act on | Re-encoded via Pillow; only undecodable vector art now goes to review |
| Replies truncated by the token limit were discarded | 3 good descriptions reported as low-confidence failures | Salvage fields from partial JSON; token cap raised |
| Model copied values from slide text | Confident invented values on an illegible image | Model reports what it can literally read; mechanical cross-check caps confidence at 3 |
| Decorative decided *after* describing | 1 of 15 images silenced; 5 logos described at confidence 5 | Decide decorative first — 8 of 15 silenced, runtime halved |
| `notes_text_frame` can be `None` | Extraction crashed on one deck | Guard for `None` |
| PDFs and mislabelled files | Raw `python-pptx` traceback | Plain-English errors; four cases tested |

### Still not proven

- **No screen reader has been run end to end.** The XML is right and three
  readers preserve it, but nobody has heard VoiceOver or NVDA read a remediated
  deck. Steps are in [DEMO.md](DEMO.md).
- **The model can still be fooled.** An illegible image paired with *matching*
  slide text can carry a wrong description past the gate. Mitigated, not
  eliminated.
- **Coverage is thin** — 9 decks, heavily computer science. PLAN.md asks for
  20–30 across five or more departments.

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

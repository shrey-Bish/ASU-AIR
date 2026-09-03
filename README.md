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

Evaluated on **11 real US university lecture decks** — MIT OpenCourseWare
(Comparative Media Studies CMS.595, AI 101, Theory of Computation) and Stanford
CS106B. 426 slides, 467 images, start to finish in **602 seconds**.

| | Count |
|---|---|
| Images found | 467 |
| Alt text applied automatically | 307 |
| Marked decorative (silenced) | 159 |
| Sent to human review | 1 |
| WCAG issues detected (nothing modified) | 517 |

Confidence spread: 235 at 5, 231 at 4, 1 at 3. Alt text was confirmed to persist
after save and reopen, with zip integrity intact and source files unmodified.

WCAG issues by check: 213 missing slide titles, 201 instances of text under
18pt, 90 slides that read out of visual order, 11 vague link texts, 2 tables
with no header row.

### The decorative result

Stanford CS106B's *fundamentals* deck has 71 images, of which **65 are
decorative** — the Stanford seal plus a briefcase icon repeated across roughly
40 slides. Without this, a blind student hears "briefcase" forty times in one
lecture. The 6 images that were described are the ones that carry teaching
content: a TIOBE index line graph and console output windows.

### What did not work

**The review queue fired once in 467 images.** One image — an unlabelled
abstract graphic in a media studies deck — came back at confidence 3 with the
reason *"the purpose of the glowing shapes is inferred... no labels or context
are visible in the image to confirm their meaning."* That is the gate working
exactly as intended, but at 0.2% it is close to invisible.

We tested whether the gate *can* fire rather than assuming. Degrading a known
image by a measured amount moves confidence the right way: Gaussian blur r=6
drops it to 3, r=14 to 2, both landing in the review queue. So the empty queue
reflects clean source decks, not a broken gate. We did not raise the threshold
to manufacture a queue.

**The model leans on slide text.** Given a deliberately illegible image plus
the real slide text, it reported values it could not possibly read. Given the
*same* image with slide text from an unrelated lecture, it described the wrong
subject entirely. The prompt now tells it to score by what is visible in the
image alone, which makes it report the inference in `reason` — but a
well-matched caption can still carry a wrong description past the gate. This is
the most important known weakness.

**Two bugs this evaluation caught**, both fixed:
- A deck whose notes slide had no notes placeholder crashed extraction
  (`notes_text_frame` is `None`, not an empty frame).
- 26 TIFF images in one MIT deck were being routed to review as "unsupported"
  when Pillow decodes them fine. Unsupported formats are now re-encoded; only
  genuinely undecodable vector art goes to review.

**Not yet verified:** nobody has opened a remediated file in desktop PowerPoint
or run NVDA/VoiceOver against it. The XML is well-formed and reopens correctly
in `python-pptx`, but that is not the same as a screen reader reading it aloud.

**Department coverage is thin.** 11 decks across 4 subject areas, and 7 of them
are from one course. PLAN.md calls for 20–30 decks from five or more
departments; this is short of that.

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

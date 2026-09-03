# Project brief — SlideSight

Accessibility remediation for PowerPoint lecture decks.
Built for the ASU AIR Spark Challenge. Submission due Sept 3, 11:59 PM MST.
Team of 2.

## What this does

Faculty upload a `.pptx` lecture deck. We find every image, use a vision model
to write real alt text, and write it back into the file so screen readers can
describe images to blind students. The model scores its own confidence:
high-confidence descriptions are applied automatically, low-confidence ones go
to a human review queue instead of being silently guessed.

Output: a remediated `.pptx` the user downloads, plus a report.

## Hard constraints

- All model calls MUST go to ASU AIR. No OpenAI, no Anthropic, no external APIs
  in the shipped product. This is a competition rule, not a preference.
- Endpoint: `https://openai.rc.asu.edu/v1` (OpenAI-compatible)
- Auth: `Authorization: Bearer $RC_LLM_API_KEY`, loaded from `.env`
- `.env` and `*.pptx` are gitignored. Never commit a key.
- PowerPoint only. No PDF. This is scope discipline, not an oversight —
  PDF remediation needs tag trees and reading order, which is a different
  and much larger problem.

## Models

Set these in `MODELS.md` with exact IDs from the Voyager portal.

| Role | Model | Notes |
|---|---|---|
| Image description | Qwen3-VL (32B instruct) | vision-capable; takes base64 images |
| Fallback / text | Gemma 4 31B-it or Qwen 3 | only if VL is unavailable |

## Verified technical facts

These were tested against a real 45-slide ASU deck. Do not re-litigate them.

- Alt text lives in the OOXML `descr` attribute, reached via
  `shape._element._nvXxPr.cNvPr.attrib['descr']`. Writing it, saving, and
  reopening works. Zip integrity holds, no parts lost, XML stays well-formed.
- `lxml` handles escaping. Ampersands, angle brackets, em dashes, and
  non-ASCII characters round-trip correctly. Do not hand-escape.
- **Images hide inside groups.** Iterating `slide.shapes` found 13 pictures in
  the test deck; recursing into `MSO_SHAPE_TYPE.GROUP` found 15. Always recurse:

  ```python
  def walk(shapes):
      for sh in shapes:
          yield sh
          if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
              yield from walk(sh.shapes)
  ```

- **Strip the `title` attribute.** Pictures carry a `title` holding the original
  filename (e.g. `Screenshot 2026-09-02 at 9.25.40 AM.png`). Some screen readers
  announce it. Pop it when writing alt text.
- Tables exist in real decks and have their own accessibility requirements.
  Out of scope — detect and report them, do not remediate.

## Data contract

Person A writes this. Person B reads it. Agreed before splitting work.

```json
{
  "slide": 7,
  "image_id": "shape_4",
  "alt_text": "Bar chart of FY24 revenue by region. Southwest leads at $4.2M, roughly double the Northeast at $2.1M.",
  "confidence": 5,
  "reason": null,
  "action": "auto_applied"
}
```

- `confidence`: integer 1-5, self-scored by the model in the same call as the
  description. One call, not two.
- `action`: `auto_applied` (confidence >= 4) or `review_queue` (below)
- `reason`: one line explaining uncertainty, only when confidence is low

## Prompt requirements

The model receives the image AND the slide's title, body text, and speaker
notes. Context is what makes the difference between "a bar chart" and "bar
chart of FY24 revenue by region, Southwest leads at $4.2M."

Descriptions must read the data, not name the shape. Ask for the confidence
score and reason in the same response as the description.

## Ownership

- **Person A — pipeline.** Extraction, vision calls, confidence parsing,
  write-back, save. Pure Python, no UI.
- **Person B — interface and evaluation.** Streamlit app (upload, progress,
  results, review queue, download). Then run 20+ decks through it, judge whether
  the descriptions are actually useful, log failures, produce the results numbers.

Both push directly to `main`. No branches, no PRs — with two people and one day
git ceremony is overhead.

## WCAG report — detection only

In scope, built AFTER the core alt-text pipeline works. These need no model
calls, so they are unblocked afternoon work.

**Detect and report. Never auto-fix.** Alt text is additive — we fill an empty
field and nothing breaks. Contrast and font size are destructive: changing a
professor's colours or type sizes returns a deck they do not recognise. Report
with slide numbers, let a human decide. This is the confidence-gate principle
applied to the whole product: fix what is safe to fix, flag the rest.

Cheap checks, roughly in build order:

- Missing or empty slide titles — check the title placeholder
- Text under 18pt — walk runs, read `run.font.size`. `None` means inherited from
  the layout, so resolve against the placeholder default rather than skipping
- Tables without a header row — `table.first_row` is a boolean
- Vague link text — flag "click here", "read more", "this link". Screen reader
  users navigate by link list, so this matters more than it looks
- Reading order — shapes are announced in XML order, not visual order. Compare
  each shape's `top`/`left` against its index and flag mismatches

**Contrast is the expensive one.** PowerPoint colours are often theme references
(`MSO_THEME_COLOR` with tints and shades), not RGB, so you must resolve the
theme, apply tint maths, then determine what is actually behind the text — shape
fill, slide background, image, or gradient. Text over a photo has no computable
ratio. Scope to solid RGB fills only, state that limitation in the report, and
do not let it consume more than a couple of hours.

## What gets cut if time runs short

Cut in this order: contrast checking, remaining WCAG checks, UI polish,
deck volume.

**Never cut the confidence gate or the review queue.** Prior art already
generates alt text for pptx — see `auto-alt-text` below. The human-in-the-loop
path and on-premise inference are the only genuinely novel parts of this
project. They are the pitch.

## Prior art — credit these in the README

- `waltervanheuven/auto-alt-text` — generates pptx alt text with a VLM and
  produces a report. Closest existing work. Has no confidence gate or review
  queue.
- `ASUCICREPO/PDF_Accessibility` — ASU AI Cloud Innovation Center's PDF
  remediation tool, built with Ohio State Libraries. Runs on AWS. Source of the
  ~$3-4/page manual remediation cost figure.
- `Width-ai/powerpoint-generative-ai` — has a `create_alt_text_for_powerpoint`
  method worth reading.

Knowing the landscape scores better than pretending we invented this.

## Deliverables checklist

- [ ] GitHub repo, public, complete README
- [ ] `MODELS.md` listing exact AIR model IDs per role
- [ ] Pitch deck — Google Slides or Canva. NOT a GitHub PDF (explicitly disallowed)
- [ ] 90-second pre-recorded pitch on YouTube
- [ ] Written submission answers
- [ ] Progress reports filed (missing these risks disqualification)

Hard code freeze 6 PM Sept 3. Deliverables take ~4 hours, not 40 minutes.

## Evaluation numbers to produce

Images found, auto-applied, flagged for review, wrong, runtime — across 20+ decks
from different departments.

Report the wrong ones. A perfect score from a 24-hour build reads as untested;
publishing one failure and explaining its cause buys more credibility than
hiding it.

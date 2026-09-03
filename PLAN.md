# PLAN.md — Slide accessibility remediation

ASU AIR Spark Challenge. Team of 2.
Submission deadline: **Sept 3, 11:59 PM MST**. Hard code freeze **6:00 PM**.

---

## 1. The problem

Professors upload PowerPoint lecture decks full of charts, diagrams, and
screenshots. Screen readers cannot describe images. A blind student hears
`"shape 4"` where everyone else sees a revenue chart.

Universities are legally required to fix this. Manual remediation runs roughly
$3–4 per page (figure from ASU's own CIC challenge page — verify before quoting
it on a slide). Nobody has time, so it does not get done.

**Evidence this is real:** the kickoff deck the organizers handed us contains
15 images. Every single one has `descr: None`. Not one has alt text. Verified
directly against the file.

## 2. What we build

Upload a `.pptx`. We find every image, generate real alt text with a vision
model, and write it back into the file. The model scores its own confidence:
high-confidence descriptions apply automatically, low-confidence ones go to a
human review queue instead of being silently guessed. Decorative images get
empty alt so screen readers skip them.

Output: a remediated `.pptx` the user downloads, plus an accessibility report
listing issues we detected but did not touch.

**PowerPoint only. No PDF.** PDF remediation needs tag trees and reading order —
a different and much larger problem — and ASU's CIC already built a funded,
polished version. Putting a 24-hour attempt beside it invites a comparison we
lose.

## 3. Why it has to run on ASU AIR

The question every team gets asked: *why not just use ChatGPT?*

- Lecture decks are unpublished faculty intellectual property. Sending them to
  a commercial vendor is a policy problem.
- Volume: hundreds of images per deck, thousands of decks across a university.
  That is a real bill anywhere else and free here.
- Nothing leaves campus. AIR keeps all inference on ASU hardware and does not
  train on the data.

**Strengthen this:** put one slide containing actual student work into the demo
deck — a graded example, a marked-up assignment. Protected data in the file
moves the argument from "policy and cost" to "legally cannot leave," which is
unanswerable.

## 4. Competition rules and deliverables

**Hard rules**
- AIR-hosted models are mandatory. No OpenAI, Anthropic, or external inference
  in the shipped product.
- Progress reports must be filed (tinyurl.com/spark-report). Missing them risks
  disqualification. File tonight's before writing any code.
- Pitch deck must be Google Slides or Canva. A GitHub-hosted PDF is explicitly
  disallowed. Decks lock at submission.
- **Team size: the deck specifies 3–5.** We are 2. Message organizers
  immediately — either they allow it or they merge us with another pair. Do not
  discover this at submission.

**Deliverables checklist**
- [ ] Public GitHub repo with complete README
- [ ] `MODELS.md` listing exact AIR model IDs per role
- [ ] Pitch deck (Google Slides / Canva)
- [ ] 90-second pre-recorded pitch on YouTube
- [ ] Written submission answers
- [ ] Progress reports filed

**Scoring.** Pre-screening checks completeness, code quality, and slide quality
— not cleverness. Top-ten judging is on Use Case & Real-World Impact, Prototype
Functionality, Innovation & Creativity, Cross-Functional Collaboration, and
Pitch & Presentation.

Cross-Functional Collaboration is a fifth of the score. With two people, make
the two roles visibly distinct and name them in the pitch.

## 5. Tech stack

| Layer | Choice | Note |
|---|---|---|
| Language | Python 3.11+ | |
| PPTX | `python-pptx` | verified working, see §6 |
| AI SDK | `openai` client, `base_url="https://openai.rc.asu.edu/v1"` | OpenAI-compatible gateway |
| Auth | `Authorization: Bearer $RC_LLM_API_KEY` from `.env` | one key each, never shared, never committed |
| UI | **Streamlit** | see below |
| State | in-memory / JSON on disk | no database |
| Concurrency | `asyncio` with a semaphore | see §7 |

**On Streamlit vs React.** FastAPI + Next.js + Tailwind + SQLite with two people
in one day means CORS config, a build pipeline, client-server state sync, and
migrations — hours of scaffolding producing zero judged output. Streamlit does
upload, progress, review queue, and download in a few hundred lines. Less
impressive as an artifact, far more likely to exist at 6 PM. Only override this
if one of us has already shipped Next.js.

**Models.** Pull exact IDs from the Voyager portal — do not guess strings like
`asu/qwen-3-vl`. Wrong IDs mean nothing runs, and judges verify AIR usage.

| Role | Model | Note |
|---|---|---|
| Image description | Qwen3-VL (32B instruct) | the only vision-capable option |
| Critique pass (optional) | Qwen3-VL again | **not Gemma** — see §7 |
| Deck summary | Gemma 4 31B-it or Qwen 3 | text only, one call per deck |

## 6. Verified technical facts

Tested against a real 45-slide ASU RTO deck. Do not re-litigate.

- Alt text lives in the OOXML `descr` attribute, reached via
  `shape._element._nvXxPr.cNvPr.attrib['descr']`. Write, save, reopen all work.
  Zip integrity holds, no parts lost, XML stays well-formed (15/15 persisted).
- `lxml` handles escaping. Ampersands, angle brackets, em dashes, and non-ASCII
  round-trip correctly. Do not hand-escape.
- **Images hide inside groups.** Iterating `slide.shapes` found 13 pictures;
  recursing into `MSO_SHAPE_TYPE.GROUP` found 15. Missing 13% of images on the
  first deck we tried. Always recurse:

  ```python
  def walk(shapes):
      for sh in shapes:
          yield sh
          if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
              yield from walk(sh.shapes)
  ```

- **Strip the `title` attribute.** Every picture carries one holding the original
  filename (`Screenshot 2026-09-02 at 9.25.40 AM.png`, `Discord-logo.png`). Some
  screen readers announce it, so a student hears the filename read aloud. Pop it
  when writing alt text. Good pitch detail: we remove noise as well as add
  description.
- Real decks contain tables (2 in the test deck). Tables have their own
  accessibility requirements. Detect and report, do not remediate.

**Still unverified:** nobody has opened a written file in actual PowerPoint or
run NVDA/VoiceOver against it. The XML is well-formed and schema-shaped so this
should be a formality, but confirm it early.

## 7. Pipeline

### Ingestion
Extract every image (recursing into groups) plus, for each one, **its own
slide's** title, body text, and speaker notes.

**Do not send the whole deck's text with every image.** Sending all 45 slides of
raw text with each image sounds generous but dilutes the signal — when
describing slide 7's chart, slide 32's bullets are noise, and descriptions get
vaguer. It is also a context-window risk; some AIR models are 64k.

If deck-level awareness is wanted, generate a **200-word deck summary once** and
prepend that. One extra call, not fifteen bloated ones. Unmetered tokens mean
cost is not the constraint; attention still is.

**No text cleaning.** Pass the raw fragmented `python-pptx` output straight to
the model. Do not write regex stitching algorithms.

### Pass 1 — description (Qwen3-VL)
Image + local slide context → description, confidence, reason, decorative flag.
One call, all four fields in the same response.

### Pass 2 — critique (optional, afternoon only)
**Must also run on Qwen3-VL, not Gemma.** Gemma is text-only. A critic that
cannot see the image cannot catch hallucination — if Pass 1 invents "$4.2M" that
is not on the chart, a text-only critic has no way to know. It can only judge
style. Either run the critic on the vision model, or state honestly that Pass 2
is a rewriter rather than a fact-checker.

Also: do not let the critic score its own rewrite. It will rate its own work
highly and the review queue empties out — killing the best demo moment. Have it
either score the original draft or flag disagreement.

**Build single-pass first and get it working end to end.** Add Pass 2 only if
the core is solid. All the unknowns live in Pass 2.

### Triage routing
- **Confidence 4–5** → applied automatically
- **Confidence 1–3** → human review queue with the model's stated reason
- **Decorative** → empty alt (`descr=""`), skipped by screen readers, never
  queued for a human

Use **1–5, not 0–100**. Models do not calibrate to a hundred points; you get
meaningless clusters at 85/90/95.

**Decorative handling is a genuine win most teams will miss.** The ASU logo
appears on all 45 slides — a blind student should not hear it 45 times. "We
identified 30 images that should be silent" is a sophisticated result.

### Concurrency
`asyncio.gather()` over all images at once will get rate-limited. Wrap in a
semaphore (3–5 concurrent) and pass `return_exceptions=True` so one failure does
not kill the batch.

**Stream results as they arrive.** A progress bar that fills is a much better 90
seconds than a spinner followed by everything appearing at once.

### Write-back
Apply final text to `descr`, strip `title`, save. **Modify only image metadata.**
Layouts, fonts, themes, and animations stay untouched.

## 8. Data contract

Agreed before splitting work. Person A writes it, Person B reads it.

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

`action`: `auto_applied` | `review_queue` | `decorative_empty_alt`

Person B can build the entire UI against a hand-written fake JSON file without
waiting for the pipeline.

## 9. Prompts

### Pass 1 — description

```
You are an expert accessibility remediator. Analyze this image from a
university lecture slide.

Slide title: {SLIDE_TITLE}
Slide text: {SLIDE_BODY}
Speaker notes: {SLIDE_NOTES}
Deck summary: {DECK_SUMMARY}

Write alt text for a blind student using a screen reader. Never begin with
"an image of" or "a picture of". Focus on the data, the educational
takeaway, and structural relationships. Include specific values, labels,
and comparisons visible in the image.

If the image is purely decorative — a logo, a border, a background
texture, a stock photo carrying no information — mark it decorative
instead of describing it.

Examples of good alt text:
"Line graph comparing Q1 to Q4 retention. Q1 starts at 85%, dipping to
72% in Q3 before recovering to 78% in Q4."
"Diagram of a cell. The nucleus is highlighted in red at the center,
surrounded by the rough endoplasmic reticulum."

Return ONLY this JSON:
{
  "description": "...",
  "decorative": false,
  "confidence": 4,
  "reason": "one line, only when confidence is 3 or below"
}
```

Confidence rubric to include in the prompt so scores mean something:
- **5** — all data legible, context clear, description verifiable from the image
- **4** — clear image, minor ambiguity in labels or units
- **3** — readable but context missing; guessing at purpose
- **2** — blurry, cropped, or unfamiliar subject matter
- **1** — cannot determine what this shows

### Deck summary (once per deck)

```
Summarize what this lecture deck covers in under 200 words: subject,
level, and the main topics in order. This summary gives an image
description model background context.

Deck text:
{ALL_SLIDE_TEXT}
```

## 10. WCAG report — detection only

Built **after** the core pipeline works. Needs no model calls, so it is
unblocked afternoon work.

**Detect and report. Never auto-fix.** Alt text is additive — we fill an empty
field and nothing breaks. Contrast and font size are destructive: changing a
professor's colours or type sizes returns a deck they do not recognise. Report
with slide numbers, let a human decide. Same confidence-gate principle applied
to the whole product.

Build order:
1. **Missing or empty slide titles** — check the title placeholder
2. **Text under 18pt** — walk runs, read `run.font.size`. `None` means inherited
   from the layout; resolve against the placeholder default rather than skipping
3. **Tables without a header row** — `table.first_row` is a boolean, one line
4. **Vague link text** — flag "click here", "read more", "this link". Screen
   reader users navigate by link list, so this matters more than it looks
5. **Reading order** — shapes are announced in XML order, not visual order.
   Compare each shape's `top`/`left` against its index, flag mismatches. Cheap,
   and most people do not know it is a problem

**Contrast is the expensive one.** PowerPoint colours are often theme references
(`MSO_THEME_COLOR` with tints and shades), not RGB. You must resolve the theme,
apply tint maths, then determine what is behind the text — shape fill, slide
background, image, or gradient. Text over a photo has no computable ratio.
Scope to solid RGB fills, state the limitation in the report, cap it at two
hours.

## 11. Evaluation

**This is a scored deliverable, not a nice-to-have.** Person B starts it in the
morning, not at the end. Every team says they will test at the end; none do.

- 20–30 decks minimum, from at least five different departments
- Variety over volume: charts, photos, diagrams, screenshots, scanned handwriting
- Record: images found, auto-applied, flagged, decorative, wrong, runtime
- Manually judge whether descriptions are actually useful — not just present
- Log every bad output with the reason

**Report the wrong ones.** A perfect score from a 24-hour build reads as
untested. Publishing one failure and explaining its cause buys more credibility
than hiding it. Target shape: 60 found / 48 auto-applied / 12 flagged / 1 wrong.

## 12. Roles

**Person A — pipeline.** Extraction with group recursion, vision calls,
confidence parsing, decorative handling, write-back, `title` stripping, save.
Pure Python, no UI.

**Person B — interface and evaluation.** Streamlit app, then the full evaluation
run and the results numbers. Also owns the screen reader testing — running NVDA
or VoiceOver on before/after decks and judging real usefulness.

Both push directly to `main`. No branches, no PRs — with two people and one day,
git ceremony is pure overhead. Agree file ownership so you do not collide.

## 13. Schedule

**Tonight**
- File progress report *first*
- Both: API keys from [voyager.rc.asu.edu](https://voyager.rc.asu.edu) via VPN,
  terminal preflight per the BYOK doc
- Confirm the vision model returns a description for one base64 image —
  everything is blocked on this
- Set up repo: public, MIT, `.gitignore` with `.env` and `*.pptx` **before**
  first commit
- Person B: collect 20–30 lecture decks
- Freeze the JSON contract
- **Stop at midnight.** Tired code tomorrow is worse than no code tonight.

**Morning**
- A: batch pipeline, write-back, save
- B: Streamlit UI against fake JSON, then start the evaluation run

**Midday**
- A: prompt tuning until descriptions read the data, not the shape
- B: review queue, screen reader testing

**Afternoon**
- WCAG detection checks (order in §10)
- Pass 2 critique **only if the core is solid**
- Full evaluation across all decks

**6:00 PM — hard freeze.** No exceptions, no "one more fix."

**Evening (~4 hours, this is real work not 40 minutes)**
- README: setup, architecture, prior art credit, honest limitations
- `MODELS.md` with exact AIR model IDs
- Pitch deck in Google Slides or Canva
- Record and upload the 90-second video
- Written answers, submit with time to spare

## 14. Pitch

**Order matters.** Lead with the blind student hearing `"shape 4"`. Then the
fix. Then the CIC validation. If you open with "ASU already built this," the
first reaction is "so why fund it again?" Problem first, validation second.

**90 seconds:**
1. A blind student in a lecture hall hears "shape 4" where everyone sees a chart
2. Every image in the organizers' own kickoff deck has no alt text
3. Upload → remediated deck out
4. **Screen reader before and after on the same slide** — this is the moment
5. The numbers, including the wrong one
6. The review queue: it knows when it does not know

**Include a refusal in the video.** A jury has watched five teams claim their bot
works. Be the team that shows it knowing when it does not.

**UI note:** put a screen-reader preview on the results screen — a before/after
pair showing `"shape 4"` versus the real description. Most persuasive element in
the product. Make the review queue the visual centrepiece, not below the fold.

**Do not build a benchmark nobody asked for.** "Why AIR" is one sentence in the
pitch and a `MODELS.md` in the repo. Ten minutes of effort. Telling RTO staff
their own platform is fast is not news.

## 15. Prior art — credit in the README

- **`waltervanheuven/auto-alt-text`** — generates pptx alt text with a VLM and
  produces a report. Closest existing work. Has no confidence gate and no review
  queue. Read its code for group traversal and report formatting.
- **`ASUCICREPO/PDF_Accessibility`** — ASU CIC's PDF remediation tool, built with
  Ohio State Libraries, runs on AWS. Source of the $3–4/page figure.
- **`Width-ai/powerpoint-generative-ai`** — has a
  `create_alt_text_for_powerpoint` method worth reading.
- **PowerPoint Accessibility Analyzer** (Hugging Face Spaces) — FastAPI +
  python-pptx + local vision models.

A judge who finds `auto-alt-text` after our pitch, when we did not mention it,
reads the project very differently than one who reads "prior art: X does this;
we add a confidence gate, human review, and on-premise inference."

## 16. Cut order and risks

**Cut in this order:** contrast checking → remaining WCAG checks → Pass 2 →
UI polish → deck volume.

**Never cut the confidence gate or the review queue.** Prior art already
generates alt text for pptx. Human-in-the-loop and on-premise inference are the
only genuinely novel parts of this project. They are the pitch.

**Risks**
| Risk | Mitigation |
|---|---|
| Team size non-compliant | Message organizers tonight |
| Vision model gives vague descriptions | Prompt work is the morning priority; local context over global |
| PowerPoint rejects a written file | Verify in real PowerPoint early — XML checks out, but confirm |
| Rate limiting | Semaphore at 3–5 concurrent |
| Pass 2 eats the afternoon | It is optional. Cut it without hesitation |
| Deliverables squeezed | 6 PM freeze is non-negotiable |

**Fallback:** if the pipeline is fundamentally broken by mid-afternoon, ship the
WCAG detection report alone. It needs no model calls and is still a working
accessibility tool. Degrading gracefully is why this project was chosen over the
alternatives.

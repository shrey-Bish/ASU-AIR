# SlideSight

Writes alt text for the pictures in PowerPoint lecture slides, using models
hosted on ASU Research Computing.

A blind student opening a lecture deck usually hears "Picture 4". In one real ASU
course deck the alt text is `C:\Users\symbiosis\Desktop\IB2COM\box_fls.png`, so
what they actually hear is a Windows folder path spelled out.

SlideSight finds every picture in a `.pptx`, writes a description for each one,
and saves the descriptions back into the file. It only saves the ones it is
confident about. The rest go to a review queue for a person to check.

Built for the ASU AIR Spark Challenge. There is a browser app and a command line
tool; both run the same code underneath.

## What is different about it

Writing alt text for PowerPoint has been done before (see [prior art](#prior-art)).
Two things here have not.

**It knows when it is unsure.** The model rates its own confidence from 1 to 5 in
the same request that produces the description. Anything at 4 or 5 goes into the
file. Anything lower is held back, with the model's reason attached, for a person
to approve or rewrite.

**Nothing leaves campus.** Lecture slides are unpublished faculty work and some
carry graded student material, so sending them to a commercial API is a policy
problem before it is a technical one. Every model call goes to ASU hardware.

There is a third behaviour that turned out to matter more than we expected.
Logos and icons get empty alt text so screen readers skip past them. One Stanford
deck repeats a briefcase icon 37 times; without this a student hears "briefcase"
37 times in one lecture. Deciding to silence a picture is also the most dangerous
thing the tool does, and [we caught ourselves getting it
wrong](#silencing-a-picture-is-the-dangerous-decision).

## Setup

Python 3.11 or newer.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Put your Research Computing key in `.env`. You can get one from
[voyager.rc.asu.edu](https://voyager.rc.asu.edu).

```
RC_LLM_API_KEY=your-key-here
```

`.env` is gitignored. Do not commit a key.

## Running it

### Browser

```bash
.venv/bin/python -m uvicorn server.main:app --port 8000
```

Open <http://127.0.0.1:8000> and upload a `.pptx`. Four steps: upload, watch the
descriptions being written, work through the review queue, download the file.

The review queue is the part that matters. Those descriptions were deliberately
not saved. Approving one is what writes it into the file, and you can edit the
draft first. Each run gets its own URL (`?job=<id>`), so refreshing the page does
not lose your work.

### Command line

```bash
.venv/bin/python -m slidesight lecture.pptx -o out/lecture.remediated.pptx
```

```
Reading lecture.pptx
  slide   8  applied  c5  Two horizontal position axes labeled x(m) from -60 to 60...
  slide  25  decor.   c5  Discord brand logo, no teaching content
  slide  31  REVIEW   c2  the chart's axis labels are cut off at the right edge

23 images on 19 slides  ->  8 applied, 4 decorative, 11 to review   (50.4s)
Wrote out/lecture.remediated.pptx
Wrote out/lecture.remediated.json
```

| Flag | What it does |
|---|---|
| `-o, --output` | where to write the new file |
| `-r, --report` | where to write the JSON report |
| `-c, --concurrency` | how many pictures to describe at once (default 4) |
| `--no-summary` | skip the one-per-file summary call |
| `--wcag-only` | run the accessibility checks only, no model calls |
| `--quiet` | print the totals and nothing else |

Only `.pptx` works. The older `.ppt` format is a completely different kind of
file that `python-pptx` cannot open, so convert it first:

```bash
soffice --headless --convert-to pptx "old deck.ppt"
```

## The report

Every picture produces one record. This is what the browser app reads, and what
you get from `--report`.

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

`action` is one of:

| Value | Meaning |
|---|---|
| `auto_applied` | confident enough to write straight into the file |
| `review_queue` | held back for a person |
| `decorative_empty_alt` | a logo or icon, given empty alt text so readers skip it |
| `human_approved` | someone approved or rewrote it in the browser app |

## Layout

```
slidesight/   the pipeline: extract, describe, apply, wcag
server/       the API: upload, progress, review, approve, download
web/          the browser app
scripts/      evaluate.py, make_review_demo.py, screen_reader_preview.py
fixtures/     a sample report, useful for working on the UI without a key
out/eval/     the summary behind the numbers below
```

Test decks are not in the repo. They are course materials belonging to the people
who wrote them.

## How it works

```
.pptx -> find pictures -> describe -> decide -> write back -> .pptx + report
```

| File | Job |
|---|---|
| `extract.py` | Walk every shape, including inside groups. Pull each picture plus its own slide's title, body text and speaker notes. |
| `describe.py` | One model call per picture. Returns a description, a decorative flag, a confidence score and a reason. |
| `apply.py` | Decides what to do with each result, and writes alt text back into the file. |
| `pipeline.py` | Runs the calls a few at a time and streams results as they arrive. |
| `wcag.py` | Five accessibility checks. No model calls. |

Three things that are easy to get wrong, all of which bit us:

Pictures hide inside groups. Looping over `slide.shapes` found 13 pictures in
the first deck we tried; recursing into groups found 15. We were missing 13% of
them.

Pictures carry a second field holding the original filename, something like
`Screenshot 2026-09-02 at 9.25.40 AM.png`. Some screen readers read it out. We
delete it.

Each picture is sent with its own slide's text, not the whole deck's. Sending
everything makes descriptions vaguer, because slide 32's bullet points are noise
when you are describing slide 7's chart. A single 200-word summary of the file is
generated once and included instead.

## Results

Ten real university lecture decks: eight from ASU (CSE 450, CSE 551, CSE 511, two
machine learning units and three PHY 111 physics decks), plus MIT's AI 101 and
Stanford's CS106B. 505 slides, 380 pictures, 556 seconds.

| | Count |
|---|---|
| Pictures found | 380 |
| Descriptions written automatically | 228 |
| Silenced as decorative | 122 |
| Sent to a person | 30 |
| Accessibility issues found and reported | 531 |

Confidence came back as 5 for 238 pictures, 4 for 137, 3 for four and 2 for one.

We checked the descriptions really do survive being saved. Files reopen in
`python-pptx` with the zip intact and the original untouched, Keynote opens them
with no repair prompt, and LibreOffice reads and rewrites them with all 23
descriptions in one test file preserved byte for byte. PowerPoint itself has not
been tested, because it was not installed on the machine we built this on.

### Silencing a picture is the dangerous decision

A bad description gets read by a person and fixed. A wrongly silenced picture
disappears from the file entirely, and by design nobody ever sees it again. The
confidence gate protects descriptions. Nothing protected this.

So we went and looked at every picture the tool had silenced.

Most of it was right. Stanford's CS106B deck silenced 66 pictures, but those are
only five unique images: a briefcase icon used 37 times, an arrow 26 times, the
Stanford seal, the C++ logo and a stock photo of string.

MIT's AI 101 deck was not right. Photographs of cats, dogs and a crawling baby
had been marked decorative, on slides that read "1. Define a problem", "6. Test
the model" and "three types of learning: supervised, unsupervised,
reinforcement". In a machine learning course those animals are the lesson.
Silencing them removes the point of the slide.

A decorative verdict now has to pass two separate checks, and failing either one
sends the picture to a person.

The first is size. Anything covering more than 12% of the slide gets held back.
We measured both groups rather than guessing: pictures we confirmed by eye as
decorative run 2 to 8.6% of the slide, and the AI 101 photographs that should
never have been silenced run 10.3 to 42.7%.

The second check is better, and we only found it because size was not enough.
Size caught nine of the twelve AI 101 cases. Then a worse example turned up in an
ASU deck: a dog photograph taking up 1% of a slide headed "Data Representation –
Feature Extraction, Raw data: Images → Features". That photograph was the raw
data being taught. No size threshold that caught it would leave the review queue
usable.

What does separate them is how the picture is built. Logos and icons are a
handful of flat colours. Photographs are thousands. On the pictures we had
checked by eye, decorative art topped out at 843 distinct colours and teaching
photographs started at 3,324, so the line goes in that gap.

Together the two checks move 11% of previously silenced pictures into the review
queue, which is a safety net rather than a flood. MIT's AI 101 now silences
nothing at all. We also tried using repetition as a signal, on the theory that
icons repeat and content does not, but it pushed 67 more pictures into review and
most of them were ordinary one-off logos, so we dropped it.

### Does the confidence gate actually fire?

Thirty pictures reached the review queue. Most came from the two decorative
checks; the rest were genuinely low confidence, with reasons like:

> The image is extremely blurry and cropped, showing only a portion of what
> appears to be the digit…

> The description infers context from the lecture topic and slide text rather
> than reading it in the image.

We tested the gate rather than assuming it worked. Blurring a picture we knew the
tool handled well moves the score the right way: a Gaussian blur of radius 6
drops it to 3, radius 14 drops it to 2, and both land in the review queue.
`scripts/make_review_demo.py` reproduces that on any file.

On where the line sits: the model answers 5 for 238 pictures and 4 for 137.
Writing 4s straight into the file is a deliberate choice. Requiring a 5 would
send another 137 pictures, 36% of everything, to a person, which is more than
anyone would work through.

### Bugs we found by running real files

None of these came from reading the code.

| Bug | What it did | Fix |
|---|---|---|
| Nothing ever double-checked a decorative verdict | Teaching photographs in an AI course were being deleted from the accessible version, invisibly | Two checks now, size and photograph-vs-graphic. Failing either sends it to a person. |
| Size alone was the wrong signal | A dog photograph at 1% of a slide, the raw data on a feature-extraction slide, was still silenced | Count distinct colours: decorative art tops out at 843, photographs start at 3,324 |
| TIFF and BMP were rejected as unsupported | 26 pictures went to the review queue as failures, which a person could do nothing about | Re-encode them first; only genuinely unreadable vector art goes to review now |
| Long replies were cut off by the token limit and thrown away | Three good descriptions were reported as failures | Salvage the fields from a partial reply; raise the limit |
| The model copied numbers out of the slide text | Confident, invented values on a picture it could not read | It now reports what it can actually read, and a check caps confidence when the two disagree |
| Decorative was decided after describing | Only 1 of 15 pictures silenced, and five logos described at full confidence | Decide decorative first. 8 of 15 silenced, and it ran twice as fast. |
| A slide with an empty notes page crashed extraction | One deck would not process at all | Guard for the empty case |
| PDFs and mislabelled files | A raw Python traceback | Plain error messages, four cases covered |

### What we have not proved

No screen reader has been run against a finished file. The XML is correct and
three different readers preserve it, but nobody has actually listened to
VoiceOver or NVDA read one. To hear it for yourself:

```bash
.venv/bin/python scripts/screen_reader_preview.py original.pptx remediated.pptx --slide 13
```

That speaks both versions through the macOS voice. It is not proof, since it
reads the file the same way we wrote it, so confirm with VoiceOver (⌘F5).

The model can still be fooled. An unreadable picture next to slide text that
happens to match can carry a wrong description past the gate. Better than it was,
but not solved.

Coverage is thinner than we wanted: ten decks across two departments. We were
aiming for 20 to 30 across five. We chose to spend the time on the
false-positive analysis instead, and think ten decks with that work behind them
is worth more than twenty without it.

## Accessibility checks

Alongside the alt text, SlideSight looks for five other problems and
deliberately does not fix any of them. Adding alt text to an empty field breaks
nothing. Changing someone's colours or type sizes hands back a file they do not
recognise. So these are reported with slide numbers, and the decision stays with
the author.

| Check | What it finds |
|---|---|
| Missing titles | Slides with no title box, or an empty one. People move between slides by title, and a text box that merely looks like a title does not count. |
| Small text | Body text under 18pt. |
| Tables with no header row | Without one, a screen reader cannot say which column a number belongs to. |
| Vague links | "click here", "read more". People often browse a list of just the links. |
| Reading order | Boxes are read in the order they were added, not the order they appear. A slide can look right and still be read out backwards. |

Run them on their own, with no key and no network:

```bash
.venv/bin/python -m slidesight lecture.pptx --wcag-only
```

That is also the fallback if the gateway is down. It is still a useful
accessibility tool with no model behind it.

Colour contrast is not implemented. PowerPoint colours are usually theme
references with tint calculations applied, and text sitting on a photograph has
no computable ratio at all. It was first on the list of things to cut, and it got
cut.

## Limitations

PowerPoint only. PDF needs tag trees and reading order, which is a much bigger
problem, and ASU's Cloud Innovation Center has already built a funded tool for it.

Tables are found and reported but never changed. They have their own
accessibility requirements.

Vector images (EMF and WMF) cannot be read by the model, so they go to the review
queue rather than being guessed at.

Pictures are shrunk to 1280px before being sent. Very fine print in a
high-resolution screenshot can be lost.

## Prior art

- [`waltervanheuven/auto-alt-text`](https://github.com/waltervanheuven/auto-alt-text)
  writes pptx alt text with a vision model and produces a report. The closest
  existing work. No confidence gate and no review queue.
- [`ASUCICREPO/PDF_Accessibility`](https://github.com/ASUCICREPO/PDF_Accessibility)
  is ASU's Cloud Innovation Center PDF tool, built with Ohio State Libraries.
  Where the $3–4 per page manual remediation figure comes from.
- [`Width-ai/powerpoint-generative-ai`](https://github.com/Width-ai/powerpoint-generative-ai)
  has a `create_alt_text_for_powerpoint` method worth reading.

## Models

[MODELS.md](MODELS.md) lists the exact model IDs, and explains why everything
runs on ASU hardware.

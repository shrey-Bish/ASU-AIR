# Demo script — the 90-second pitch

Everything here is reproducible from the repo.

**Order matters.** Lead with the blind student hearing "shape 4". Then go
straight to Moment 2 — the failure we caught in our own tool — *before* any
count of how many images were described.

Every team will demo something working. Almost none will demo something they
caught themselves doing wrong. It also answers the hardest question available
— *how do you know your tool isn't quietly wrong?* — with: we assumed it was,
and went looking.

## Moment 1 — what a blind student actually hears

Use a remediated ASU deck. `out/demo_ASU_ML.pptx` (from
`decks/U1_Introduction to Machine Learning (1).pptx`) is ready.

**Before** — the original deck. Every picture has no alt text, so a screen
reader announces the shape name:

> "Picture 4"

**After** — the same slide, same picture, remediated:

> "Laparoscopic surgery simulator with a monitor displaying a virtual surgical
> environment showing colorful anatomical structures and tools. The physical
> console includes hand controls and foot pedals for manipulating the virtual
> instruments."

### Fastest way to hear it — no VoiceOver setup needed

macOS ships the same speech engine VoiceOver uses. This speaks exactly what a
screen reader announces for each image, before and after:

```bash
.venv/bin/python scripts/screen_reader_preview.py \
    "decks/U1_Introduction to Machine Learning (1).pptx" \
    "out/demo_ASU_ML.pptx" --slide 13
```

Add `--save out/audio/demo` to write `.aiff` files instead of playing them —
drop those straight into the video. `--silent` prints without speaking.

**What it reveals on slide 13 of the real ASU deck:**

> **BEFORE:** "C:\Users\symbiosis\Desktop\IB2COM\box_fls.png"
> **AFTER:** "Laparoscopic surgery simulator with a monitor displaying a virtual
> surgical environment showing colorful anatomical structures and tools…"

That before is not a placeholder we invented. PowerPoint auto-filled the alt
text with the source file path, so a blind student in that course hears a
Windows directory read out letter by letter. Other images on the same slide
have no alt text at all and are announced as "Picture 6".

This is a preview, not proof — it reads the file the same way we wrote it, so it
does not independently verify PowerPoint exposes the field. Run VoiceOver below
for that.

### Running VoiceOver yourself

This is the one step nobody can automate for you — VoiceOver needs a real
keypress and Accessibility permission.

1. Open the **original** deck in PowerPoint or Keynote.
2. Turn VoiceOver on: **⌘F5**.
3. Navigate to the picture on slide 13 (**VO = Control+Option**; `VO + →` moves
   between elements). Listen: it says the shape name.
4. Turn VoiceOver off (**⌘F5**), open `out/demo_ASU_ML.pptx`, repeat.
5. Record both. Same slide, same picture, two very different experiences.

You can also see it without VoiceOver: right-click the picture → **Alt Text**
(PowerPoint) and the description is sitting there.

### What has been verified without a screen reader

- The text is written to the OOXML `descr` attribute on `p:cNvPr` — the exact
  field PowerPoint's Alt Text pane and screen readers read.
- 23 of 23 pictures carried alt text after save and reopen; zip integrity intact.
- 0 leftover filename `title` attributes (some readers announce those, so a
  student would otherwise hear `Screenshot 2026-09-02 at 9.25.40 AM.png`).
- **Keynote opens the remediated file with no repair prompt.**
- **LibreOffice Impress round-trip: 23/23 descriptions preserved byte-identical.**
  A separate OOXML implementation reads the `descr` field, keeps it, and writes
  it back — the same spec field PowerPoint and screen readers use.
- **PowerPoint itself is still untested** — it is not installed on the dev
  machine, and installing it needs an admin password. Run it once before
  claiming it on stage:
  `brew install --cask microsoft-powerpoint`

## Moment 2 — we caught our own tool deleting content

Silencing an image is the dangerous decision. A bad description gets read by a
human and corrected. A wrongly-silenced diagram is removed from the blind
student's experience entirely — and a confidence gate on *descriptions* does
nothing to protect it. Nothing reviewed those calls.

So we reviewed every image the tool had silenced.

Most were right. But in MIT's AI 101 deck, photographs of cats, dogs and a
crawling baby had been marked decorative — on slides reading **"1. Define a
problem"**, **"6. Test the model"**, and **"three types of learning:
supervised, unsupervised, reinforcement."**

In a machine-learning course those animals *are* the teaching content. Our tool
was deleting the point of the slide from the accessible version, and by design
no human would ever have seen it happen.

**The fix, shipped the same afternoon:** a decorative verdict is no longer
trusted on its own. Any image covering more than 12% of the slide goes to human
review with the reason stated. Verified logos and template icons measure
2–8.6%; the misclassified photos measured 10.3–42.7%.

Say the limitation out loud — it is the strongest part:

> "It catches 9 of the 12. A cat at 6.7% of the slide still slips through,
> because no size threshold that catches it leaves the queue usable. Size is a
> proxy for importance and an imperfect one."

## Moment 2b — the gate, on real input (optional)

19 images reached the review queue on real decks, with reasons like:

> "The image is extremely blurry and cropped, showing only a portion of what
> appears to be the digit…"

**Demo the real queue, not the blurred deck.** `scripts/make_review_demo.py`
still exists and is worth keeping as calibration evidence — degrading one image
by a measured amount moves confidence the right way (blur r=6 → 3, r=14 → 2) —
but with real review items you no longer need a constructed failure on stage.

## Moment 3 — the silent images (optional, strong)

Stanford CS106B's *fundamentals* deck: 71 images, 66 of them decorative — the
Stanford seal plus a briefcase icon repeated across ~40 slides. Without this,
a student hears "briefcase" forty times in one lecture. We write empty alt text
so a screen reader skips them entirely.

"We identified 66 images that should be silent" is a more sophisticated claim
than "we described 307 images", and most teams will not have it.

## Numbers to quote

See the Results table in [README.md](README.md); the raw data is
`out/eval/eval_summary.json`, regenerated by:

```bash
.venv/bin/python scripts/evaluate.py decks -o out/eval
```

## Do not claim

- That it works on PDF. It does not, by design, and it says so when handed one.
- That PowerPoint has been tested. Keynote has.
- That a screen reader has been run end to end, until you have run it.
- That the blurred image was a naturally occurring failure.
- That the decorative guard catches everything. It catches 9 of 12; say so.

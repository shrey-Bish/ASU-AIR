/* SlideSight front end.
 *
 * Four screens from the approved design, wired to the FastAPI backend:
 *   POST /api/upload                        -> job_id
 *   GET  /api/jobs/{id}                     -> progress, then the full report
 *   GET  /api/jobs/{id}/thumb/{slide}/{img} -> the picture being reviewed
 *   POST /api/jobs/{id}/approve             -> write a human-approved description
 *   GET  /api/jobs/{id}/download            -> the remediated .pptx
 *
 * The review queue is the point of the product: the pipeline deliberately did
 * not write those descriptions, so approving here is what puts them in the file.
 */

const SCREENS = [
  { key: "upload", label: "Upload" },
  { key: "processing", label: "Processing" },
  { key: "review", label: "Review queue" },
  { key: "results", label: "Results" },
];

const state = {
  screen: "upload",
  jobId: null,
  file: null,
  report: null,
  reviewItems: [],
  handled: {},      // image key -> "written" | "skipped"
  drafts: {},       // image key -> edited text
  poll: null,
};

const $ = (id) => document.getElementById(id);
const keyOf = (r) => `${r.slide}:${r.image_id}`;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ── navigation ─────────────────────────────────────── */

function reachable(key) {
  if (key === "upload") return true;
  if (key === "processing") return !!state.jobId;
  if (key === "review" || key === "results") return !!state.report;
  return false;
}

function show(key) {
  state.screen = key;
  for (const s of SCREENS) {
    $(`screen-${s.key}`).hidden = s.key !== key;
  }
  renderSteps();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderSteps() {
  const idx = SCREENS.findIndex((s) => s.key === state.screen);
  $("steps").innerHTML = SCREENS.map((s, i) => {
    const current = s.key === state.screen;
    const cls = ["step", i < idx ? "done" : ""].filter(Boolean).join(" ");
    const dis = reachable(s.key) ? "" : "disabled";
    return `<li><button type="button" class="${cls}" data-go="${s.key}" ${dis}
      ${current ? 'aria-current="step"' : ""}>
      <span class="num">${String(i + 1).padStart(2, "0")}</span><span>${s.label}</span>
    </button></li>`;
  }).join("");
  document.querySelectorAll("[data-go]").forEach((b) =>
    b.addEventListener("click", () => show(b.dataset.go)));
}

/* ── step one: upload ───────────────────────────────── */

function wireUpload() {
  const input = $("deck-file");
  const zone = $("dropzone");

  input.addEventListener("change", () => { state.file = input.files[0] || null; clearError(); });

  ["dragenter", "dragover"].forEach((e) =>
    zone.addEventListener(e, (ev) => { ev.preventDefault(); zone.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((e) =>
    zone.addEventListener(e, (ev) => { ev.preventDefault(); zone.classList.remove("drag"); }));
  zone.addEventListener("drop", (ev) => {
    const f = ev.dataTransfer?.files?.[0];
    if (f) { input.files = ev.dataTransfer.files; state.file = f; clearError(); }
  });

  $("btn-start").addEventListener("click", startRun);
}

function showError(msg) { const e = $("upload-error"); e.textContent = msg; e.hidden = false; }
function clearError() { $("upload-error").hidden = true; }

async function startRun() {
  if (!state.file) { showError("Choose a .pptx file first."); return; }
  clearError();
  $("btn-start").disabled = true;

  const body = new FormData();
  body.append("file", state.file);

  try {
    const res = await fetch("/api/upload", { method: "POST", body });
    const data = await res.json();
    if (!res.ok) { showError(data.error || "Upload failed."); $("btn-start").disabled = false; return; }
    state.jobId = data.job_id;
    resetProgress();
    show("processing");
    state.poll = setInterval(pollJob, 1200);
    pollJob();
  } catch (err) {
    showError("Could not reach the server. Is it running?");
    $("btn-start").disabled = false;
  }
}

/* ── step two: processing ───────────────────────────── */

function resetProgress() {
  $("feed").innerHTML = "";
  $("bar-fill").style.width = "0%";
  $("prog-slide").textContent = "Slide 0 of 0";
  $("prog-pct").textContent = "0%";
  $("live-status").textContent = "Reading the deck…";
}

const ACTION_TEXT = {
  auto_applied: (r) => r.alt_text,
  decorative_empty_alt: () => "Decorative — marked empty so screen readers skip it.",
  review_queue: (r) => `Held for review — ${r.reason || "low confidence"}`,
};

function renderFeed(records) {
  const rows = records.slice(-40).reverse();
  $("feed").innerHTML = rows.map((r) => {
    const text = (ACTION_TEXT[r.action] || ((x) => x.alt_text))(r) || "—";
    return `<li><span class="slide">Slide ${r.slide}</span><span class="text">${esc(text)}</span></li>`;
  }).join("");
}

async function pollJob() {
  if (!state.jobId) return;
  let job;
  try {
    job = await (await fetch(`/api/jobs/${state.jobId}`)).json();
  } catch { return; }

  if (job.status === "failed") {
    clearInterval(state.poll);
    show("upload");
    showError(job.error || "Remediation failed.");
    $("btn-start").disabled = false;
    return;
  }

  const pct = Math.round(job.progress_pct || 0);
  $("bar-fill").style.width = `${pct}%`;
  $("progressbar").setAttribute("aria-valuenow", String(pct));
  $("prog-pct").textContent = `${pct}%`;
  if (job.total_slides) $("prog-slide").textContent = `Slide ${job.current_slide || 0} of ${job.total_slides}`;
  renderFeed(job.records_so_far || []);

  if (job.status === "complete") {
    clearInterval(state.poll);
    state.report = job.report;
    $("live-status").textContent = "Done.";
    buildReview();
    show(state.reviewItems.length ? "review" : "results");
    if (!state.reviewItems.length) renderResults();
  } else {
    $("live-status").textContent =
      job.current_alt_text ? `Writing: ${job.current_alt_text.slice(0, 90)}…`
                           : "Describing images…";
  }
}

/* ── step three: review queue ───────────────────────── */

function buildReview() {
  state.reviewItems = (state.report?.images || []).filter((r) => r.action === "review_queue");
  renderReview();
}

function confidenceBar(score) { return `${Math.max(0, Math.min(5, score)) / 5 * 100}%`; }

function renderReview() {
  const items = state.reviewItems;
  $("review-intro").textContent = items.length
    ? `These ${items.length} images scored below the confidence threshold, so nothing was written for them yet. Read the draft, fix it if it is wrong, and approve it.`
    : "Nothing needed review in this deck.";
  updateReviewCount();

  $("review-list").innerHTML = items.map((r) => {
    const k = keyOf(r);
    const st = state.handled[k];
    const draft = state.drafts[k] ?? r.alt_text ?? "";
    const fid = `alt-${r.slide}-${r.image_id}`;
    const rid = `why-${r.slide}-${r.image_id}`;
    return `
    <li class="${st ? "handled" : ""}" data-key="${esc(k)}">
      <div class="review-grid">
        <div>
          <div class="thumb">
            <img src="/api/jobs/${state.jobId}/thumb/${r.slide}/${encodeURIComponent(r.image_id)}"
                 alt="Image being reviewed, slide ${r.slide}"
                 onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'ph',textContent:'no preview'}))">
          </div>
          <p class="thumb-cap">Slide ${r.slide} &middot; ${esc(r.image_id)}</p>
        </div>
        <div>
          <h3 class="review-title">Slide ${r.slide} image</h3>
          <p class="review-context">${r.decorative ? "Model called this decorative" : "Low confidence description"}</p>

          <label class="field-label" for="${fid}">Draft description</label>
          <textarea id="${fid}" rows="3" data-field="${esc(k)}"
            aria-describedby="${rid}">${esc(draft)}</textarea>
          <p class="charcount" data-count="${esc(k)}">${draft.length} characters</p>

          <dl class="meta">
            <dt>Confidence</dt>
            <dd class="conf">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#8A5A00" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"></path><path d="M12 9v4"></path><path d="M12 17h.01"></path></svg>
              <strong>${r.decorative ? "Needs a human" : "Low confidence"}</strong>
              <span class="score">${r.confidence} of 5</span>
              <span class="track" aria-hidden="true"><span style="width:${confidenceBar(r.confidence)}"></span></span>
            </dd>
            <dt id="${rid}">Why flagged</dt>
            <dd>${esc(r.reason || "The model was not confident enough to write this automatically.")}</dd>
          </dl>

          <div class="actions">
            <button type="button" class="btn btn-primary btn-sm" data-approve="${esc(k)}"
              ${st === "written" ? "disabled" : ""}>Approve description</button>
            <button type="button" class="btn btn-link" data-skip="${esc(k)}">Skip for now</button>
            <p aria-live="polite" class="state ${st || ""}" data-state="${esc(k)}">${
              st === "written" ? "✓ Written into the file"
              : st === "skipped" ? "Skipped — left unwritten" : ""}</p>
          </div>
        </div>
      </div>
    </li>`;
  }).join("");

  $("review-list").querySelectorAll("[data-field]").forEach((ta) => {
    ta.addEventListener("input", () => {
      const k = ta.dataset.field;
      state.drafts[k] = ta.value;
      const c = $("review-list").querySelector(`[data-count="${CSS.escape(k)}"]`);
      if (c) c.textContent = `${ta.value.length} characters`;
    });
  });
  $("review-list").querySelectorAll("[data-approve]").forEach((b) =>
    b.addEventListener("click", () => approve(b.dataset.approve)));
  $("review-list").querySelectorAll("[data-skip]").forEach((b) =>
    b.addEventListener("click", () => { state.handled[b.dataset.skip] = "skipped"; renderReview(); }));
}

function updateReviewCount() {
  const total = state.reviewItems.length;
  const done = Object.keys(state.handled).length;
  $("review-count").textContent = `${done} of ${total} handled · ${total - done} left`;
}

async function approve(k) {
  const item = state.reviewItems.find((r) => keyOf(r) === k);
  if (!item) return;
  const text = (state.drafts[k] ?? item.alt_text ?? "").trim();
  if (!text) { alert("Write a description before approving, or skip it."); return; }

  const res = await fetch(`/api/jobs/${state.jobId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slide: item.slide, image_id: item.image_id, alt_text: text }),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    alert(d.error || "Could not write that description.");
    return;
  }
  item.alt_text = text;
  state.handled[k] = "written";
  renderReview();
}

/* ── step four: results ─────────────────────────────── */

const CHECK_LABEL = {
  missing_title: "Slides with no title",
  small_text: "Text under 18pt",
  table_no_header: "Tables with no header row",
  vague_link: "Vague link text",
  reading_order: "Slides that read out of visual order",
};
const CHECK_DETAIL = {
  missing_title: "Screen readers navigate by slide title. A text box that looks like a title does not count.",
  small_text: "Body text below 18pt is hard to read projected or magnified.",
  table_no_header: "Without a header row a screen reader gives no column context.",
  vague_link: "“Click here” tells a screen reader user nothing — they navigate by link list.",
  reading_order: "Shapes are announced in XML order, not visual order. The slide can look right and read out backwards.",
};

function renderResults() {
  const rep = state.report || {};
  const written = Object.values(state.handled).filter((v) => v === "written").length;

  $("results-lede").textContent =
    `${rep.slides || 0} slides read from ${rep.source || "your deck"}. `
    + "Descriptions are saved inside the file, so they travel with it.";

  const counts = [
    ["Images found", rep.images_found || 0, `Across ${rep.slides || 0} slides, including repeats in the template.`],
    ["Described automatically", rep.auto_applied || 0, "Confidence 4 or 5 out of 5. Already written into the file."],
    ["Sent to review", rep.review_queue || 0, written ? `You approved ${written} of these in step three.` : "Below the threshold — nothing was written without you."],
    ["Marked decorative and silenced", rep.decorative || 0, "Logos, dividers and icons. Given empty alt text so screen readers skip them."],
  ];
  $("counts-body").innerHTML = counts.map(([label, value, note]) =>
    `<tr><th scope="row">${esc(label)}</th><td class="num">${value}</td><td class="note">${esc(note)}</td></tr>`).join("");

  // Before/after, taken from real records rather than invented.
  const described = (rep.images || []).filter((r) => r.action === "auto_applied" && r.alt_text).slice(0, 2);
  const silent = (rep.images || []).find((r) => r.action === "decorative_empty_alt");
  const cases = described.map((r) => ({
    name: `A described image (slide ${r.slide})`,
    before: `"Image. ${r.image_id.replace("_", " ")}."`,
    after: `"${r.alt_text}"`,
  }));
  if (silent) cases.push({
    name: `A decorative image (slide ${silent.slide})`,
    before: `"Image. ${silent.image_id.replace("_", " ")}." — repeated wherever the template puts it.`,
    after: "Nothing. The image is skipped entirely and the student hears the slide content instead.",
  });
  $("compare").innerHTML = cases.map((c) => `
    <div class="case">
      <p class="case-name">${esc(c.name)}</p>
      <dl>
        <dt>Before</dt><dd>${esc(c.before)}</dd>
        <dt>After</dt><dd class="after">${esc(c.after)}</dd>
      </dl>
    </div>`).join("") || `<p class="muted">No images in this deck.</p>`;

  // Real WCAG findings, grouped by check.
  const wcag = rep.wcag || { by_check: {}, issues: [] };
  const bySlide = {};
  (wcag.issues || []).forEach((i) => { (bySlide[i.check] ||= []).push(i.slide); });
  const rows = Object.entries(wcag.by_check || {}).sort((a, b) => b[1] - a[1]);
  $("issues").innerHTML = rows.length ? rows.map(([check, n]) => {
    const slides = [...new Set(bySlide[check] || [])].sort((a, b) => a - b);
    const shown = slides.slice(0, 12).join(", ") + (slides.length > 12 ? `, +${slides.length - 12} more` : "");
    return `<li>
      <div>
        <p class="name">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#8A5A00" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M12 8v5"></path><path d="M12 16h.01"></path></svg>
          <span>${esc(CHECK_LABEL[check] || check)}</span>
          <span class="count">${n} ${n === 1 ? "instance" : "instances"}</span>
        </p>
        <p class="detail">${esc(CHECK_DETAIL[check] || "")}</p>
      </div>
      <p class="slides">Slides ${esc(shown)}</p>
    </li>`;
  }).join("") : `<li><p class="detail">No other accessibility issues detected.</p></li>`;
}

/* ── wiring ─────────────────────────────────────────── */

function wireResults() {
  $("btn-finish").addEventListener("click", () => { renderResults(); show("results"); });
  $("btn-download").addEventListener("click", () => {
    window.location.href = `/api/jobs/${state.jobId}/download`;
  });
  $("btn-report").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(state.report, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `slidesight-report-${state.jobId?.slice(0, 8) || "deck"}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  });
  $("btn-restart").addEventListener("click", () => {
    Object.assign(state, { jobId: null, file: null, report: null, reviewItems: [], handled: {}, drafts: {} });
    $("deck-file").value = "";
    $("btn-start").disabled = false;
    clearError();
    show("upload");
  });
}

/* Resume a job from the URL (?job=<id>), so a refresh during a long run does
   not lose the work -- the job lives on the server, not in this tab. */
async function resumeFromUrl() {
  const id = new URLSearchParams(location.search).get("job");
  if (!id) return false;
  try {
    const job = await (await fetch(`/api/jobs/${id}`)).json();
    if (job.error) return false;
    state.jobId = id;
    if (job.status === "complete") {
      state.report = job.report;
      buildReview();
      renderResults();
      show(state.reviewItems.length ? "review" : "results");
    } else {
      resetProgress();
      show("processing");
      state.poll = setInterval(pollJob, 1200);
      pollJob();
    }
    return true;
  } catch { return false; }
}

wireUpload();
wireResults();
renderSteps();
resumeFromUrl().then((resumed) => { if (!resumed) show("upload"); });

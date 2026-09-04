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

/* ── picture preview ────────────────────────────────── */

/* Thumbnails are too small to judge a description against, so any picture can
   be opened full size. Focus moves into the dialog and back to whatever opened
   it, and Escape closes -- this is an accessibility tool, it has to be usable
   from the keyboard. */
let previewOpener = null;

function openPreview(src, caption, alt) {
  previewOpener = document.activeElement;
  const img = $("preview-img");
  const cap = $("preview-cap");

  // Say something while it loads, and say something useful if it never
  // arrives. An empty white box tells the user nothing.
  cap.textContent = "Loading the picture…";
  img.hidden = true;
  img.alt = alt || caption || "";
  img.onload = () => { img.hidden = false; cap.textContent = caption || ""; };
  img.onerror = () => {
    img.hidden = true;
    cap.textContent =
      "That picture could not be loaded. If the server restarted, the run is "
      + "gone — upload the file again.";
  };
  img.src = src;

  $("preview").hidden = false;
  $("preview-close").focus();
}

function closePreview() {
  $("preview").hidden = true;
  const img = $("preview-img");
  img.onload = img.onerror = null;
  img.removeAttribute("src");
  if (previewOpener && previewOpener.isConnected) previewOpener.focus();
  previewOpener = null;
}

function wirePreview() {
  $("preview-close").addEventListener("click", closePreview);
  $("preview").addEventListener("click", (e) => {
    if (e.target === $("preview")) closePreview();   // click the backdrop
  });
  document.addEventListener("keydown", (e) => {
    if ($("preview").hidden) return;
    if (e.key === "Escape") closePreview();
    if (e.key === "Tab") { e.preventDefault(); $("preview-close").focus(); }
  });
  // One listener for every zoomable picture, now and in future renders.
  document.addEventListener("click", (e) => {
    const z = e.target.closest("[data-zoom]");
    if (!z) return;
    e.preventDefault();
    openPreview(z.dataset.zoom, z.dataset.caption || "", z.dataset.alt || "");
  });
}

/* ── navigation ─────────────────────────────────────── */

function reachable(key) {
  if (key === "upload") return true;
  if (key === "processing") return !!state.jobId;
  if (key === "review" || key === "results") return !!state.report;
  return false;
}

function show(key, updateHash = true) {
  // Steps are deep-linkable: /#review, /#results. Useful for jumping straight
  // to a screen when demoing, and for sharing a run at a particular step.
  if (updateHash && location.hash.slice(1) !== key) {
    history.replaceState(null, "", `${location.search}#${key}`);
  }
  // Results must be rendered before it is shown: the nav enables that step as
  // soon as the job completes, so a presenter can jump straight to it.
  if (key === "results" && state.report) renderResults();
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
  if (!state.file) { showError("Pick a .pptx file first."); return; }
  clearInterval(state.poll);
  state.poll = null;
  clearError();
  $("btn-start").disabled = true;

  const body = new FormData();
  body.append("file", state.file);

  try {
    const res = await fetch("/api/upload", { method: "POST", body });
    const data = await res.json();
    if (!res.ok) { showError(data.error || "Upload failed."); $("btn-start").disabled = false; return; }
    state.jobId = data.job_id;
    // Make the run addressable so a refresh resumes instead of losing it.
    history.replaceState(null, "", `?job=${data.job_id}`);
    resetProgress();
    show("processing");
    state.poll = setInterval(pollJob, 1200);
    pollJob();
  } catch (err) {
    showError("We could not reach the server. Is it running?");
    $("btn-start").disabled = false;
  }
}

/* ── step two: processing ───────────────────────────── */

function resetProgress() {
  $("feed").innerHTML = "";
  $("bar-fill").style.width = "0%";
  $("prog-slide").textContent = "Image 0 of 0";
  $("prog-pct").textContent = "0%";
  $("live-status").textContent = "Opening your file…";
}

const ACTION_TEXT = {
  auto_applied: (r) => r.alt_text,
  decorative_empty_alt: () => "Hidden from screen readers — a logo or icon.",
  review_queue: () => "Set aside for you to check.",
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
  let job, res;
  try {
    res = await fetch(`/api/jobs/${state.jobId}`);
    job = await res.json();
  } catch {
    return;  // transient network blip: keep the last good state on screen
  }

  // A 404 or an error envelope has no status and no progress, and would
  // otherwise reset the bar to 0% and blank the feed while polling forever.
  if (!res.ok || job.error || job.status === "failed") {
    clearInterval(state.poll);
    state.poll = null;
    state.jobId = null;
    show("upload");
    showError(job.error || "We lost contact with the server.");
    $("btn-start").disabled = false;
    return;
  }

  const pct = Math.round(job.progress_pct || 0);
  $("bar-fill").style.width = `${pct}%`;
  $("progressbar").setAttribute("aria-valuenow", String(pct));
  $("prog-pct").textContent = `${pct}%`;
  // Images, not slides: the pipeline runs 4 at a time and finishes out of
  // order, so a slide number jumps around and disagrees with the percentage.
  const done = (job.records_so_far || []).length;
  if (job.total_images) $("prog-slide").textContent = `Image ${done} of ${job.total_images}`;
  renderFeed(job.records_so_far || []);

  if (job.status === "complete") {
    clearInterval(state.poll);
    state.report = job.report;
    $("live-status").textContent = "Done.";
    buildReview();
    show(state.reviewItems.length ? "review" : "results");
  } else {
    $("live-status").textContent =
      job.current_alt_text ? `Just wrote: ${job.current_alt_text.slice(0, 90)}…`
                           : "Writing descriptions…";
  }
}

/* ── step three: review queue ───────────────────────── */

function buildReview() {
  state.reviewItems = (state.report?.images || [])
    .filter((r) => r.action === "review_queue" || r.action === "human_approved");
  renderReview();
}

/* The model's own reason is written for an engineer. Lead with a sentence a
   professor can act on, and keep the original after it. */
function plainReason(r) {
  const raw = (r.reason || "").trim();
  if (r.decorative) {
    return "We nearly hid this picture, but it looks like part of the lesson. "
      + "Hiding it would take it away from a blind student completely.";
  }
  if (/blurr|cropped|too small|cannot|could not|not legible/i.test(raw)) {
    return "The picture was too unclear to describe properly. " + raw;
  }
  return raw || "We were not sure enough to write this on our own.";
}

function renderReview() {
  const items = state.reviewItems;
  const total = state.report?.images_found || items.length;
  $("review-intro").textContent = items.length
    ? `We wrote the descriptions for the rest of these slides ourselves. `
      + `These ${items.length} of ${total} images need you to look. `
      + `Read each description, change it if it is wrong, then approve it.`
    : "Nothing in this file needed checking.";
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
                    <button type="button" class="thumb zoom"
            data-zoom="/api/jobs/${state.jobId}/thumb/${r.slide}/${encodeURIComponent(r.image_id)}?w=1400"
            data-caption="Slide ${r.slide} — click outside or press Escape to close"
            data-alt="The picture from slide ${r.slide}, shown full size"
            title="Click to see this picture full size">
            <img loading="lazy"
                 src="/api/jobs/${state.jobId}/thumb/${r.slide}/${encodeURIComponent(r.image_id)}"
                 alt="Picture from slide ${r.slide}"
                 onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'ph',textContent:'no preview'}))">
          </button>
          <p class="thumb-cap">Slide ${r.slide} &middot; ${esc(r.image_id)}</p>
        </div>
        <div>
          <h3 class="review-title">Slide ${r.slide} image</h3>
          <p class="review-context">${r.decorative ? "We nearly hid this picture" : "We were not sure about this one"}</p>

          <label class="field-label" for="${esc(fid)}">${draft ? "Description we wrote" : "Nothing written yet — add one"}</label>
          <textarea id="${esc(fid)}" rows="3" data-field="${esc(k)}"
            placeholder="${draft ? "" : "We did not write anything for this one. Type a description, or skip it."}"
            aria-describedby="${esc(rid)}">${esc(draft)}</textarea>
          <p class="charcount" data-count="${esc(k)}">${draft.length} characters</p>

          <dl class="meta">
            <dt>Status</dt>
            <dd class="conf">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#8A5A00" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"></path><path d="M12 9v4"></path><path d="M12 17h.01"></path></svg>
              <strong>Needs a human</strong>
            </dd>
            <dt>Why</dt>
            <dd id="${esc(rid)}">${esc(plainReason(r))}</dd>
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

/* Writes a description into the saved file. Used by the review queue and by
   the inline editors on the results screen. Keeps the in-memory report in step
   so the counts and the "you" markers stay correct without a reload. */
async function writeDescription(item, text) {
  const res = await fetch(`/api/jobs/${state.jobId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slide: item.slide, image_id: item.image_id, alt_text: text }),
  });
  if (!res.ok) return false;
  item.alt_text = text;
  item.action = "human_approved";
  return true;
}

async function approve(k) {
  const item = state.reviewItems.find((r) => keyOf(r) === k);
  if (!item) return;
  const text = (state.drafts[k] ?? item.alt_text ?? "").trim();
  const say = (msg, cls) => {
    const el = $("review-list").querySelector(`[data-state="${CSS.escape(k)}"]`);
    if (el) { el.textContent = msg; el.className = `state ${cls}`; }
  };
  if (!text) { say("Type a description first, or skip this one.", "skipped"); return; }

  if (!(await writeDescription(item, text))) {
    say("We could not save that description.", "skipped");
    return;
  }
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
/* The checks describe themselves in their own terms. Say what is on the slide. */
function plainDetail(check, detail) {
  const d = String(detail || "");
  if (check === "missing_title") {
    return d.includes("no title placeholder")
      ? "This slide has no title box at all."
      : "The title box on this slide is empty.";
  }
  if (check === "small_text") {
    const m = d.match(/^([\d.]+)pt.*?:\s*(.*)$/);
    return m ? `${m[1]}pt text — ${m[2]}` : d;
  }
  if (check === "reading_order") {
    const m = d.match(/topmost is read at position (\d+) \((.*)\)/);
    return m
      ? `The box at the top of this slide, ${m[2]}, is read out ${ordinal(+m[1])} instead of first.`
      : d;
  }
  if (check === "table_no_header") return `This table has no header row. ${d}`;
  if (check === "vague_link") return `Link text that says little: ${d}`;
  return d;
}

function ordinal(n) {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

const CHECK_DETAIL = {
  missing_title: "People jump between slides using the titles. A text box that only looks like a title does not count.",
  small_text: "Text under 18pt is hard to read on a projector or when zoomed in.",
  table_no_header: "Without a header row, a screen reader cannot say which column a number belongs to.",
  vague_link: "“Click here” says nothing on its own. Many people browse a list of just the links.",
  reading_order: "A screen reader reads boxes in the order they were added, not the order they appear. The slide can look right and still be read out backwards.",
};

function renderResults() {
  const rep = state.report || {};
  const written = Object.values(state.handled).filter((v) => v === "written").length;
  // Count from the report so a resumed session shows the right number too.
  const approved = (rep.images || []).filter((r) => r.action === "human_approved").length || written;

  $("results-lede").textContent =
    `We read ${rep.slides || 0} slides in ${rep.source || "your file"}. `
    + "The descriptions are saved inside the file, so they stay with it wherever it goes.";

  const images = rep.images || [];
  const pick = (...actions) => images.filter((r) => actions.includes(r.action));
  const counts = [
    ["all", "Images found", rep.images_found || 0,
      `Every picture across ${rep.slides || 0} slides, counting ones that repeat.`, images],
    ["applied", "Described automatically", rep.auto_applied || 0,
      "We were sure about these, so they are already saved in the file.",
      pick("auto_applied")],
    ["review", "You checked these", (rep.review_queue || 0) + (rep.human_approved || 0),
      approved
        ? `You approved ${approved} of ${(rep.review_queue || 0) + approved} — marked “✓ you” in the list.`
        : "We did not save anything for these without you.",
      pick("review_queue", "human_approved")],
    ["silent", "Hidden from screen readers", rep.decorative || 0,
      "Logos, lines and small icons. A screen reader will skip past these instead of reading them out.",
      pick("decorative_empty_alt")],
  ];

  $("counts-body").innerHTML = counts.map(([key, label, value, note, rows]) => {
    // "Images found" is just the total of the three below it, so there is
    // nothing useful to open. The other three show the pictures themselves --
    // a list of descriptions means little without the image beside it.
    const canOpen = key !== "all" && rows.length > 0;
    const list = !canOpen ? "" : rows.map((r) => {
      const k = keyOf(r);
      const hidden = r.action === "decorative_empty_alt";
      const mine = r.action === "human_approved";
      const text = r.alt_text
        || (hidden ? "Hidden on purpose — a screen reader skips it." : "Nothing written yet.");
      return `<li data-row="${esc(k)}">
        <button type="button" class="zoom"
          data-zoom="/api/jobs/${state.jobId}/thumb/${r.slide}/${encodeURIComponent(r.image_id)}?w=1400"
          data-caption="Slide ${r.slide}"
          data-alt="The picture from slide ${r.slide}, shown full size"
          title="Click to see this picture full size">
          <img class="lp" loading="lazy" alt="Picture from slide ${r.slide}"
               src="/api/jobs/${state.jobId}/thumb/${r.slide}/${encodeURIComponent(r.image_id)}"
               onerror="this.closest('.zoom').remove()">
        </button>
        <span class="ln">Slide ${r.slide}${mine ? '<span class="you">✓ you</span>' : ""}</span>
        <span class="lt">
          <span class="lt-text">${esc(text)}</span>
          <textarea class="lt-edit" hidden rows="3"
            aria-label="Description for the picture on slide ${r.slide}">${esc(r.alt_text || "")}</textarea>
          <span class="lt-actions">
            <button type="button" class="linky" data-edit="${esc(k)}">${
              hidden ? "Describe this instead" : "Edit"}</button>
            <button type="button" class="linky save" data-save="${esc(k)}" hidden>Save</button>
            <button type="button" class="linky" data-cancel="${esc(k)}" hidden>Cancel</button>
            <span class="lt-msg" data-msg="${esc(k)}"></span>
          </span>
        </span></li>`;
    }).join("");
    return `<tr class="count-row">
        <th scope="row">${canOpen
          ? `<button type="button" class="disclose" data-open="${key}" aria-expanded="false"
               aria-controls="rows-${key}"><span class="chev" aria-hidden="true">▸</span>${esc(label)}</button>`
          : esc(label)}</th>
        <td class="num">${value}</td><td class="note">${esc(note)}</td>
      </tr>
      ${canOpen ? `<tr id="rows-${key}" class="count-detail" hidden><td colspan="3">
        <ul class="count-list">${list}</ul>
      </td></tr>` : ""}`;
  }).join("");

  // Inline edit for any picture, in any of the three groups. Writing a
  // description into a hidden picture un-hides it -- which is the escape hatch
  // for the case where we silenced something that mattered.
  const rowEls = (k) => {
    const li = $("counts-body").querySelector(`[data-row="${CSS.escape(k)}"]`);
    return li && {
      li,
      text: li.querySelector(".lt-text"),
      area: li.querySelector(".lt-edit"),
      edit: li.querySelector("[data-edit]"),
      save: li.querySelector("[data-save]"),
      cancel: li.querySelector("[data-cancel]"),
      msg: li.querySelector("[data-msg]"),
    };
  };
  const setEditing = (k, on) => {
    const e = rowEls(k);
    if (!e) return;
    e.text.hidden = on; e.area.hidden = !on;
    e.edit.hidden = on; e.save.hidden = !on; e.cancel.hidden = !on;
    if (on) e.area.focus();
  };

  $("counts-body").querySelectorAll("[data-edit]").forEach((b) =>
    b.addEventListener("click", () => setEditing(b.dataset.edit, true)));
  $("counts-body").querySelectorAll("[data-cancel]").forEach((b) =>
    b.addEventListener("click", () => setEditing(b.dataset.cancel, false)));
  $("counts-body").querySelectorAll("[data-save]").forEach((b) =>
    b.addEventListener("click", async () => {
      const k = b.dataset.save;
      const e = rowEls(k);
      const item = (state.report?.images || []).find((r) => keyOf(r) === k);
      const value = e.area.value.trim();
      if (!item) return;
      if (!value) { e.msg.textContent = "Type a description first."; return; }
      e.msg.textContent = "Saving…";
      const ok = await writeDescription(item, value);
      if (!ok) { e.msg.textContent = "Could not save that."; return; }
      e.text.textContent = value;
      e.msg.textContent = "Saved into your file.";
      setEditing(k, false);
      setTimeout(() => { if (e.msg) e.msg.textContent = ""; }, 4000);
    }));

  $("counts-body").querySelectorAll("[data-open]").forEach((b) => {
    b.addEventListener("click", () => {
      const panel = $(`rows-${b.dataset.open}`);
      const open = b.getAttribute("aria-expanded") === "true";
      b.setAttribute("aria-expanded", String(!open));
      b.querySelector(".chev").textContent = open ? "▸" : "▾";
      panel.hidden = open;
    });
  });

  // Before/after, taken from real records rather than invented.
  // The "before" is what the file actually carried, never invented. An image
  // with no alt text at all is announced only as a picture; one whose authoring
  // tool auto-filled a path is read out character by character.
  const spoken = (r) => {
    const had = (r.existing_alt || r.existing_title || "").trim();
    return had ? `"${had}"` : `"Image." — no description in the file.`;
  };
  const withJunk = (rep.images || []).filter(
    (r) => (r.existing_alt || r.existing_title || "").trim() && r.alt_text);
  const described = (rep.images || []).filter(
    (r) => (r.action === "auto_applied" || r.action === "human_approved") && r.alt_text);
  const picked = [...withJunk, ...described.filter((r) => !withJunk.includes(r))].slice(0, 2);
  const cases = picked.map((r) => ({
    name: `Slide ${r.slide}`,
    before: spoken(r),
    after: `"${r.alt_text}"`,
  }));
  const silent = (rep.images || []).find((r) => r.action === "decorative_empty_alt");
  if (silent) cases.push({
    name: `A decorative image (slide ${silent.slide})`,
    before: spoken(silent),
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
  const byCheck = {};
  (wcag.issues || []).forEach((i) => { (byCheck[i.check] ||= []).push(i); });

  $("issues").innerHTML = rows.length ? rows.map(([check, n]) => {
    const items = (byCheck[check] || []).slice().sort((a, b) => a.slide - b.slide);
    const lines = items.map((i) =>
      `<li>
        <button type="button" class="slidepic zoom"
          data-zoom="/api/jobs/${state.jobId}/slide/${i.slide}"
          data-caption="Slide ${i.slide}"
          data-alt="Slide ${i.slide}, shown full size"
          title="Click to see slide ${i.slide} full size">
          <img loading="lazy" alt="Slide ${i.slide}"
               src="/api/jobs/${state.jobId}/slide/${i.slide}"
               onerror="this.closest('.slidepic').remove()">
        </button>
        <span class="ln">Slide ${i.slide}</span>
        <span class="lt">${esc(plainDetail(check, i.detail))}</span>
      </li>`
    ).join("");
    return `<li>
      <div>
        <p class="name">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#8A5A00" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M12 8v5"></path><path d="M12 16h.01"></path></svg>
          <span>${esc(CHECK_LABEL[check] || check)}</span>
          <span class="count">${n} ${n === 1 ? "slide" : "slides"}</span>
        </p>
        <p class="detail">${esc(CHECK_DETAIL[check] || "")}</p>
      </div>
      <p class="slides">
        <button type="button" class="disclose" data-issue="${esc(check)}"
          aria-expanded="false" aria-controls="iss-${esc(check)}">
          <span class="chev" aria-hidden="true">▸</span>Which slides
        </button>
      </p>
      <ul id="iss-${esc(check)}" class="count-list issue-list" hidden>${lines}</ul>
    </li>`;
  }).join("") : `<li><p class="detail">We did not find any other problems.</p></li>`;

  $("issues").querySelectorAll("[data-issue]").forEach((b) => {
    b.addEventListener("click", () => {
      const panel = $(`iss-${b.dataset.issue}`);
      const open = b.getAttribute("aria-expanded") === "true";
      b.setAttribute("aria-expanded", String(!open));
      b.querySelector(".chev").textContent = open ? "▸" : "▾";
      panel.hidden = open;
    });
  });

  const note = $("wcag-note");
  if (note) note.textContent = wcag.note || "";
}

/* ── wiring ─────────────────────────────────────────── */

function wireResults() {
  $("btn-finish").addEventListener("click", () => { renderResults(); show("results"); });
  $("btn-download").addEventListener("click", () => {
    window.location.href = `/api/jobs/${state.jobId}/download`;
  });
  $("btn-report").addEventListener("click", async () => {
    // Re-fetch: the server rewrote the counts and actions as items were
    // approved, so its copy is the one that matches the downloaded deck.
    let rep = state.report;
    try {
      const res = await fetch(`/api/jobs/${state.jobId}/report`);
      if (res.ok) rep = await res.json();
    } catch { /* fall back to the in-memory copy */ }
    const blob = new Blob([JSON.stringify(rep, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `slidesight-report-${state.jobId?.slice(0, 8) || "deck"}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  });
  $("btn-restart").addEventListener("click", () => {
    clearInterval(state.poll);
    history.replaceState(null, "", location.pathname);
    Object.assign(state, { jobId: null, file: null, report: null, reviewItems: [],
                           handled: {}, drafts: {}, poll: null });
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
      const wanted = location.hash.slice(1);
      show(SCREENS.some((s) => s.key === wanted) ? wanted
           : state.reviewItems.length ? "review" : "results");
    } else {
      resetProgress();
      show("processing");
      state.poll = setInterval(pollJob, 1200);
      pollJob();
    }
    return true;
  } catch (err) {
    // A silent catch here once hid a ReferenceError and made resume look like
    // "no job in the URL". Surface it instead.
    console.error("Could not resume job from URL:", err);
    return false;
  }
}

wireUpload();
wireResults();
wirePreview();
renderSteps();
resumeFromUrl().then((resumed) => { if (!resumed) show("upload"); });

/**
 * Shared engine for scripted page walkthroughs, used by both the
 * staff dashboard demo and the diner-page demo. A page defines its
 * own step list (caption + action) and an optional cleanup function;
 * this module owns the panel UI, pacing, and pause/next/restart
 * controls, so that part isn't duplicated per page.
 */

const Demo = (() => {
  let steps = [];
  let onReset = async () => {};
  let paused = false;
  let stepIndex = -1;
  let active = false;
  let delayMs = 7000;
  let advanceTimer = null;
  let resolveAdvance = null;

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function waitFor(check, timeoutMs = 8000, intervalMs = 150) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const result = check();
      if (result) return result;
      await sleep(intervalMs);
    }
    return null;
  }

  function highlight(target) {
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.classList.add("demo-highlight");
    setTimeout(() => target.classList.remove("demo-highlight"), 2200);
  }

  function findRowByTitleSubstring(container, substring) {
    if (!container) return null;
    return Array.from(container.querySelectorAll(".row")).find((row) =>
      (row.querySelector(".title")?.textContent || "").includes(substring)
    );
  }

  /**
   * Visibly types text into a field, character by character, rather
   * than snapping the value in instantly, for text/number inputs
   * where that's genuinely possible. Native date/time/select controls
   * can't be simulated this way, no script API opens or visibly
   * drives their picker UI, so those still get set directly.
   */
  async function typeInto(input, text, charDelayMs = 45) {
    if (!input) return;
    input.focus();
    input.value = "";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    for (const ch of String(text)) {
      input.value += ch;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      await sleep(charDelayMs);
    }
    await sleep(200);
  }

  /** A brief visible "press" before the click actually fires. */
  async function clickWithFeedback(button) {
    if (!button) return;
    highlight(button);
    button.classList.add("demo-pressed");
    await sleep(160);
    button.classList.remove("demo-pressed");
    button.click();
  }

  /**
   * For native date/time/select controls, which can't be visibly
   * "typed into" or opened the way a real picker can, script can only
   * ever set .value directly, so the field gets its own pause and
   * flash instead: focus it, hold a beat so the viewer's eye actually
   * lands there before anything changes, then set the value and flash
   * it to confirm the change registered, rather than the value just
   * silently appearing mid-sequence with no visible acknowledgment.
   */
  async function setFieldWithEmphasis(input, value) {
    if (!input) return;
    input.scrollIntoView({ behavior: "smooth", block: "center" });
    input.classList.add("demo-field-focus");
    await sleep(500);
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    input.classList.remove("demo-field-focus");
    input.classList.add("demo-field-flash");
    await sleep(500);
    input.classList.remove("demo-field-flash");
  }

  let minimized = false;

  function ensureDemoPanel() {
    if (document.getElementById("demo-panel")) return;
    const panel = document.createElement("div");
    panel.id = "demo-panel";
    panel.className = "demo-panel";
    panel.innerHTML = `
      <div class="demo-panel-header">
        <span class="demo-step-count" id="demo-step-count"></span>
        <button id="demo-minimize-btn" type="button">Hide</button>
      </div>
      <div class="demo-panel-body" id="demo-panel-body">
        <div class="demo-caption" id="demo-caption">Ready.</div>
        <div class="demo-controls">
          <select id="demo-speed">
            <option value="4000">Fast (4s)</option>
            <option value="7000" selected>Normal (7s)</option>
            <option value="12000">Slow (12s)</option>
          </select>
          <button id="demo-pause-btn">Pause</button>
          <button id="demo-next-btn">Next</button>
          <button id="demo-restart-btn">Restart</button>
          <button id="demo-stop-btn">Close</button>
        </div>
      </div>
    `;
    document.body.appendChild(panel);

    document.getElementById("demo-pause-btn").onclick = () => {
      togglePause();
      document.getElementById("demo-pause-btn").textContent = paused ? "Play" : "Pause";
    };
    document.getElementById("demo-next-btn").onclick = () => advanceNow();
    document.getElementById("demo-restart-btn").onclick = async () => {
      stop();
      await onReset();
      start(steps, onReset, delayMs);
    };
    document.getElementById("demo-stop-btn").onclick = async () => {
      stop();
      await onReset();
    };
    document.getElementById("demo-speed").onchange = (e) => {
      delayMs = Number(e.target.value);
    };
    // Collapses the caption/controls so they don't cover whatever the
    // step just changed underneath, without pausing or stopping the
    // demo, it keeps running, just out of the way until brought back.
    document.getElementById("demo-minimize-btn").onclick = () => {
      minimized = !minimized;
      applyMinimizedState();
    };
  }

  function applyMinimizedState() {
    const panel = document.getElementById("demo-panel");
    if (!panel) return;
    panel.classList.toggle("demo-panel-minimized", minimized);
    const btn = document.getElementById("demo-minimize-btn");
    if (btn) btn.textContent = minimized ? "Show" : "Hide";
  }

  function showPanel() {
    ensureDemoPanel();
    document.getElementById("demo-panel").style.display = "flex";
    minimized = false;
    applyMinimizedState();
  }

  function hidePanel() {
    const panel = document.getElementById("demo-panel");
    if (panel) panel.style.display = "none";
  }

  function updatePanel() {
    ensureDemoPanel();
    const captionEl = document.getElementById("demo-caption");
    const count = document.getElementById("demo-step-count");
    if (stepIndex >= steps.length) {
      captionEl.textContent = "Demo complete.";
      count.textContent = `${steps.length} / ${steps.length}`;
    } else {
      // Captions can be a plain string or a function, evaluated fresh
      // each render, for steps whose wording depends on state that
      // isn't known until this step's own action has run (e.g. which
      // branch an LLM decision landed in).
      const raw = steps[stepIndex].caption;
      captionEl.textContent = typeof raw === "function" ? raw() : raw;
      count.textContent = `${stepIndex + 1} / ${steps.length}`;
    }
  }

  function awaitAdvance() {
    return new Promise((resolve) => {
      resolveAdvance = resolve;
      if (!paused) advanceTimer = setTimeout(resolve, delayMs);
    });
  }

  async function runStep(index) {
    stepIndex = index;
    updatePanel();
    try {
      await steps[index].action();
    } catch (err) {
      console.error("Demo step failed:", err);
    }
    // Re-render in case a dynamic caption's underlying state only
    // became known partway through this step's own action.
    updatePanel();
  }

  async function start(newSteps, resetFn, initialDelayMs) {
    if (active) return;
    steps = newSteps;
    onReset = resetFn || (async () => {});
    if (initialDelayMs) delayMs = initialDelayMs;
    active = true;
    paused = false;
    showPanel();

    for (let i = 0; i < steps.length; i++) {
      if (!active) return;
      await runStep(i);
      if (!active) return;
      if (i < steps.length - 1) await awaitAdvance();
    }
    stepIndex = steps.length;
    updatePanel();
  }

  function stop() {
    active = false;
    if (advanceTimer) clearTimeout(advanceTimer);
    // Unblock the runner loop immediately if it's mid-wait between
    // steps, otherwise it sits there until that wait's own timer
    // fires (or forever, if paused) before it next checks `active`.
    if (resolveAdvance) {
      const resolve = resolveAdvance;
      resolveAdvance = null;
      resolve();
    }
    hidePanel();
  }

  function advanceNow() {
    if (advanceTimer) clearTimeout(advanceTimer);
    if (resolveAdvance) resolveAdvance();
  }

  function togglePause() {
    paused = !paused;
    if (!paused && resolveAdvance) {
      if (advanceTimer) clearTimeout(advanceTimer);
      advanceTimer = setTimeout(resolveAdvance, delayMs);
    } else if (paused && advanceTimer) {
      clearTimeout(advanceTimer);
    }
    updatePanel();
  }

  return {
    start,
    stop,
    sleep,
    waitFor,
    highlight,
    findRowByTitleSubstring,
    typeInto,
    clickWithFeedback,
    setFieldWithEmphasis,
  };
})();

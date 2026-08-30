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

  function ensureDemoPanel() {
    if (document.getElementById("demo-panel")) return;
    const panel = document.createElement("div");
    panel.id = "demo-panel";
    panel.className = "demo-panel";
    panel.innerHTML = `
      <div class="demo-caption" id="demo-caption">Ready.</div>
      <div class="demo-controls">
        <span class="demo-step-count" id="demo-step-count"></span>
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
  }

  function showPanel() {
    ensureDemoPanel();
    document.getElementById("demo-panel").style.display = "flex";
  }

  function hidePanel() {
    const panel = document.getElementById("demo-panel");
    if (panel) panel.style.display = "none";
  }

  function updatePanel() {
    ensureDemoPanel();
    const caption = document.getElementById("demo-caption");
    const count = document.getElementById("demo-step-count");
    if (stepIndex >= steps.length) {
      caption.textContent = "Demo complete.";
      count.textContent = `${steps.length} / ${steps.length}`;
    } else {
      caption.textContent = steps[stepIndex].caption;
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

  return { start, stop, sleep, waitFor, highlight, findRowByTitleSubstring };
})();

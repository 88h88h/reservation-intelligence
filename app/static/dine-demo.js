/**
 * Diner-page walkthrough, auto-continues from the staff demo (arrives
 * via ?demo=1) or can be started standalone with the same button.
 */

let dinerDemoCreatedReservationId = null;

function pickDinerDemoTime() {
  // A handful of distinct times, not always 18:00, so repeated
  // rehearsal runs on the same day are less likely to collide even
  // before a reset happens.
  const options = ["17:30", "18:00", "18:30", "20:00", "20:30"];
  return options[Math.floor(Math.random() * options.length)];
}

function buildDinerSteps() {
  return [
    {
      caption: "Here's the same restaurant from a diner's side. The whole point of this view: let someone judge the atmosphere before committing, not just see a booking form.",
      action: async () => Demo.highlight(document.querySelector(".vibe-block")),
    },
    {
      caption: "That vibe isn't a label someone typed in, it's a plain computed heuristic off real occupancy data, deliberately no camera, no sensors, no LLM call for something this simple to derive.",
      action: async () => Demo.highlight(document.getElementById("occupancy-dots")),
    },
    {
      caption: () =>
        document.getElementById("offers-section").style.display !== "none"
          ? "Active promotional offers surface right here, enticing, not pushy, and only shown when the restaurant actually chose to run one."
          : "No promotional offers are running right now, and that's deliberate, they'd only surface here when occupancy is genuinely low enough to justify one.",
      action: async () => {
        const section = document.getElementById("offers-section");
        Demo.highlight(section.style.display !== "none" ? section : document.querySelector(".diner-card"));
      },
    },
    {
      caption: "Now the actual booking flow. It's the exact same POST /reservations endpoint the staff dashboard uses, one booking code path for both audiences, not two implementations to keep in sync.",
      action: async () => {
        const form = document.getElementById("booking-form");
        Demo.highlight(form);
        await Demo.setFieldWithEmphasis(document.getElementById("diner-time"), pickDinerDemoTime());
        await Demo.typeInto(document.getElementById("diner-party"), "2");
        const submitBtn = form.querySelector('button[type="submit"]');
        await Demo.clickWithFeedback(submitBtn);
        await Demo.waitFor(() => document.getElementById("diner-results").children.length > 0);
      },
    },
    {
      caption: "Reserved, simple as that, the same atomic guarantee from the staff side applies here too. Staff will see and confirm it from their dashboard.",
      action: async () => {
        const btn = await Demo.waitFor(() =>
          document.getElementById("diner-results").querySelector("button.primary")
        );
        if (!btn) return;
        await Demo.clickWithFeedback(btn);
        await Demo.waitFor(() => document.querySelector(".confirmation"));
        const reservations = await api(`/restaurants/${restaurantId}/reservations`);
        if (reservations[0]) dinerDemoCreatedReservationId = reservations[0].id;
      },
    },
    {
      caption: "That's the full loop: browse by vibe, check availability, book, and staff manage confirmation, conflicts, and every edge case from their own dashboard.",
      action: async () => {
        Demo.highlight(document.querySelector(".confirmation") || document.querySelector(".diner-card"));
        // The confirmation screen shown above is a static view, it
        // doesn't re-render live, so cleaning up here doesn't disturb
        // what's on screen, "the demo ending" should clean up too,
        // not just an explicit Restart/Close.
        await Demo.sleep(1500);
        await resetDinerDemo();
      },
    },
  ];
}

function resolveCaption(step) {
  return typeof step.caption === "function" ? step.caption() : step.caption;
}

async function resetDinerDemo() {
  if (dinerDemoCreatedReservationId) {
    try {
      await api(`/reservations/${dinerDemoCreatedReservationId}/cancel`, { method: "POST" });
    } catch (e) {
      // already cancelled or unreachable, fine to ignore for a reset
    }
    dinerDemoCreatedReservationId = null;
  }
  await loadOccupancy();
}

function startDinerDemo() {
  const steps = buildDinerSteps().map((s) => ({ ...s, caption: resolveCaption(s) }));
  Demo.start(steps, resetDinerDemo, 7000);
}

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("run-demo-btn");
  if (btn) btn.onclick = () => startDinerDemo();

  if (new URLSearchParams(window.location.search).get("demo") === "1") {
    // Wait for init() (in dine.js) to finish loading real data before
    // the script starts touching the page.
    const tryStart = () => {
      if (document.getElementById("vibe-label").className.includes("tier-")) {
        setTimeout(startDinerDemo, 800);
      } else {
        setTimeout(tryStart, 200);
      }
    };
    tryStart();
  }
});

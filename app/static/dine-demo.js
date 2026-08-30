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
      caption: "Here's the same restaurant from a diner's side, real-time vibe, active offers, and a simple booking flow.",
      action: async () => Demo.highlight(document.querySelector(".vibe-block")),
    },
    {
      caption: "The vibe updates live, a color-coded fill bar and a dot for every actual table, not just a percentage.",
      action: async () => Demo.highlight(document.getElementById("occupancy-dots")),
    },
    {
      caption: () =>
        document.getElementById("offers-section").style.display !== "none"
          ? "Active promotional offers surface right here, enticing, not pushy."
          : "No promotional offers are running right now, they'd surface right here the moment one goes live.",
      action: async () => {
        const section = document.getElementById("offers-section");
        Demo.highlight(section.style.display !== "none" ? section : document.querySelector(".diner-card"));
      },
    },
    {
      caption: "Let's book a table, picking who's booking, then a time.",
      action: async () => {
        const form = document.getElementById("booking-form");
        Demo.highlight(form);
        document.getElementById("diner-time").value = pickDinerDemoTime();
        document.getElementById("diner-party").value = "2";
        form.dispatchEvent(new Event("submit", { cancelable: true }));
        await Demo.waitFor(() => document.getElementById("diner-results").children.length > 0);
      },
    },
    {
      caption: "And reserved, simple as that. Staff confirm it from their side, back on the dashboard.",
      action: async () => {
        const btn = await Demo.waitFor(() =>
          document.getElementById("diner-results").querySelector("button.primary")
        );
        if (!btn) return;
        Demo.highlight(btn);
        btn.click();
        await Demo.waitFor(() => document.querySelector(".confirmation"));
        const reservations = await api(`/restaurants/${restaurantId}/reservations`);
        if (reservations[0]) dinerDemoCreatedReservationId = reservations[0].id;
      },
    },
    {
      caption: "That's the full loop, browse by vibe, check availability, book, staff manage confirmation and edge cases from their dashboard.",
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

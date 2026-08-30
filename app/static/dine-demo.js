/**
 * Diner-page walkthrough, auto-continues from the staff demo (arrives
 * via ?demo=1) or can be started standalone with the same button.
 */

let dinerDemoCreatedReservationId = null;
let demoCarriedDate = null;
let demoCarriedReservationIds = [];
let demoCarriedOfferId = null;

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
      caption: "This is the diner-facing side of the same system, a second, deliberately different frontend on the same backend and the same booking guarantees, not a separate product. The whole point of this view: let someone judge the atmosphere before committing, not just see a booking form.",
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
      caption: () =>
        demoCarriedDate
          ? `A moment ago, on the staff side, Table 1 got confirmed for 7 PM on ${demoCarriedDate}. Let's try that same table and time from here, the diner's side, and see what losing that race actually looks like from this end, not just that staff's request won.`
          : "This diner demo is running on its own right now, not chained from the staff one, so there's no live booking on the other side to collide with, skipping ahead to a normal booking.",
      action: async () => {
        if (!demoCarriedDate) return;
        const resultsEl = document.getElementById("diner-results");
        Demo.highlight(resultsEl);
        resultsEl.innerHTML = `<div class="callout suggest">Trying to reserve Table 1, 7 PM, ${demoCarriedDate}&hellip;</div>`;
        await Demo.sleep(1200);
        const tables = await api(`/restaurants/${restaurantId}/tables`);
        const table1 = tables.find((t) => t.name === "Table 1");
        if (!table1) return;
        await book(table1.id, { date: demoCarriedDate, hour: 19, minute: 0, duration: 60, partySize: 2 });
        await Demo.waitFor(() => document.getElementById("diner-results").textContent.includes("just got taken"));
      },
    },
    {
      caption: () =>
        demoCarriedDate
          ? "That's the real skill 1 flow, from the diner's own side this time, not staff clicking a button in a dashboard. Same endpoint, same reasoning, a genuinely reused capability, not two separate implementations to keep in sync."
          : "Nothing to show here this run, moving on.",
      action: async () => {
        if (!demoCarriedDate) return;
        const btn = document.getElementById("diner-results").querySelector("button.agent");
        if (!btn) return;
        await Demo.clickWithFeedback(btn);
        await Demo.waitFor(() => {
          const text = document.getElementById("diner-results").textContent;
          return text.includes("Reserve this instead") || text.includes("nothing else fits");
        });
      },
    },
    {
      caption: "Now let's see an ordinary booking, one that doesn't collide with anything. It's the exact same POST /reservations endpoint the staff dashboard uses, one booking code path for both audiences, not two implementations to keep in sync.",
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

async function resetDinerDemo() {
  if (dinerDemoCreatedReservationId) {
    try {
      await api(`/reservations/${dinerDemoCreatedReservationId}/cancel`, { method: "POST" });
    } catch (e) {
      // already cancelled or unreachable, fine to ignore for a reset
    }
    dinerDemoCreatedReservationId = null;
  }
  // Also cleans up whatever the staff leg created, including Table 1's
  // booking this demo deliberately collided with, since cleanup for
  // that leg was deferred here rather than run before the navigation
  // that brought us to this page.
  for (const id of demoCarriedReservationIds) {
    try {
      await api(`/reservations/${id}/cancel`, { method: "POST" });
    } catch (e) {
      // already cancelled or unreachable, fine to ignore for a reset
    }
  }
  demoCarriedReservationIds = [];
  if (demoCarriedOfferId) {
    try {
      await api(`/offers/${demoCarriedOfferId}`, { method: "DELETE" });
    } catch (e) {
      // already gone, fine to ignore for a reset
    }
    demoCarriedOfferId = null;
  }
  demoCarriedDate = null;
  sessionStorage.removeItem("demoCarryState");
  await loadOccupancy();
}

function startDinerDemo() {
  // Only read on the initial start, a Restart mid-run reuses this same
  // step list and its already-resolved closures, not a fresh build, so
  // re-reading here would just pick the same values back up anyway;
  // resetDinerDemo (called before every restart) is what actually
  // clears these once their state has been cleaned up.
  try {
    const raw = sessionStorage.getItem("demoCarryState");
    if (raw) {
      const carried = JSON.parse(raw);
      demoCarriedDate = carried.demoDate || null;
      demoCarriedReservationIds = carried.reservationIds || [];
      demoCarriedOfferId = carried.offerId || null;
    }
  } catch (e) {
    // malformed or inaccessible, just run without the carried leg
  }
  Demo.start(buildDinerSteps(), resetDinerDemo, 7000);
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

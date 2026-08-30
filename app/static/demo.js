/**
 * Staff-dashboard walkthrough for the explanation video. Drives the
 * real UI, real typed text, real button presses, real API calls, so
 * what's on screen is genuinely happening, not staged. Captions are
 * written to explain the reasoning behind each scenario, not just
 * narrate the click, so a viewer understands what's being tested and
 * why, not just that something happened. Ends by navigating into the
 * diner view, where a matching demo auto-continues.
 */

let demoCreatedReservationIds = [];
let demoCreatedOfferId = null;
let demoLastOfferStatus = null;
let demoDate = null;

function pickDemoDate() {
  const d = new Date();
  d.setDate(d.getDate() + 14 + Math.floor(Math.random() * 300));
  return d.toISOString().slice(0, 10);
}

async function fillAvailabilityForm(time, party) {
  await Demo.setFieldWithEmphasis(document.getElementById("res-date"), demoDate);
  await Demo.setFieldWithEmphasis(document.getElementById("res-time"), time);
  await Demo.typeInto(document.getElementById("res-party"), String(party));
}

async function submitAvailabilityForm(time, party) {
  await fillAvailabilityForm(time, party);
  const submitBtn = document.querySelector("#availability-form button[type=submit]");
  await Demo.clickWithFeedback(submitBtn);
  await Demo.waitFor(() => document.getElementById("availability-results").children.length > 0);
}

function buildStaffSteps() {
  const table1Name = "Table 1"; // window, capacity 2, min 1
  const table4Name = "Table 4"; // patio, capacity 6, min 4

  return [
    {
      caption: "This is Reservation Intelligence, a restaurant booking platform with an agentic layer on top. FastAPI backend, SQLite storage, no Docker, kept deliberately simple to run locally. What's worth watching for isn't the CRUD, it's how it handles real concurrency, and where an agent genuinely earns its place instead of being bolted on.",
      action: async () => Demo.highlight(document.querySelector("header.topbar")),
    },
    {
      caption: "One idea underneath almost everything you're about to see: reservations aren't stored as continuous time ranges, they're quantized into 15-minute slots, and a booking claims a specific set of those slots as its own rows. That turns double-booking prevention from a hard interval-overlap problem into a plain database uniqueness constraint, correctness enforced by the schema, not application code trying to get a race condition right.",
      action: async () => Demo.highlight(document.getElementById("tables-grid").closest(".card")),
    },
    {
      caption: "You'll also see a Reservation Operations Agent along the way: three distinct skills, each with its own deliberate autonomy boundary, some only ever suggest, one can act on its own within a pre-approved range, bound together through real LLM tool-calling, not a hardcoded router. More on each as they come up.",
      action: async () => {},
    },
    {
      caption: "Five tables here, each with a real type, capacity, and minimum party size, the actual inventory the rest of this demo works against.",
      action: async () => Demo.highlight(document.getElementById("tables-grid").closest(".card")),
    },
    {
      caption: "Let's set up a normal booking, Table 1, two guests, 7 PM, claiming four of those 15-minute slots. This becomes the baseline we'll deliberately collide with next.",
      action: async () => {
        Demo.highlight(document.getElementById("availability-form"));
        await submitAvailabilityForm("19:00", 2);
      },
    },
    {
      caption: "Table 1 is free. Booking it now, invisibly, this request carries a unique idempotency key generated client-side, so a duplicate click or a retried request can never create two reservations. Watch the price too, it's computed live from current occupancy and demand, not a fixed number pulled off the table.",
      action: async () => {
        const row = await Demo.waitFor(() =>
          Demo.findRowByTitleSubstring(document.getElementById("availability-results"), table1Name)
        );
        await Demo.clickWithFeedback(row?.querySelector("button.primary"));
        await Demo.waitFor(() => document.getElementById("booking-outcome").textContent.includes("Booked as HELD"));
      },
    },
    {
      caption: "It's held, not confirmed yet, visible right there in the badge. Every slot this reservation needs got claimed together in one database transaction, all or nothing, so no one can ever observe a half-booked reservation. Something invisible is also true right now: if nobody confirms it in time, a background sweep releases it automatically, so a stale hold can never silently block this table forever.",
      action: async () => {
        const row = await Demo.waitFor(() => document.getElementById("reservations-list").querySelector(".row"));
        Demo.highlight(row);
      },
    },
    {
      caption: "Let's confirm it.",
      action: async () => {
        const row = document.getElementById("reservations-list").querySelector(".row");
        await Demo.clickWithFeedback(row?.querySelector("button.primary"));
        await Demo.sleep(600);
        const table1Id = tablesCache.find((t) => t.name === table1Name)?.id;
        const reservations = await api(`/restaurants/${restaurantId}/reservations`);
        const match = reservations.find((r) => r.table_id === table1Id && r.status === "CONFIRMED");
        if (match) demoCreatedReservationIds.push(match.id);
      },
    },
    {
      caption: "Now the real test: a second request for that exact same table and time, the classic check-then-act race condition. Triggered directly here since the normal search would already filter this table out for being taken, which is itself part of the point, the guarantee holds even if something bypasses the UI.",
      action: async () => {
        Demo.highlight(document.getElementById("booking-outcome"));
        const table1Id = tablesCache.find((t) => t.name === table1Name)?.id;
        await book(table1Id, { date: demoDate, hour: 19, minute: 0, duration: 60, partySize: 2 });
        await Demo.waitFor(() => document.getElementById("booking-outcome").textContent.includes("just became unavailable"));
      },
    },
    {
      caption: "Rejected outright, a UNIQUE constraint on the slot table does this, not application code checking and then writing in two separate steps, that gap is exactly where races like this usually slip through. This is where the agent adds value: suggesting a fix, not just failing.",
      action: async () => {
        const btn = document.getElementById("booking-outcome").querySelector("button.agent");
        await Demo.clickWithFeedback(btn);
        await Demo.waitFor(() => document.getElementById("booking-outcome").querySelector(".callout.agent-result, .callout.error"));
      },
    },
    {
      caption: "It reasoned through table type, timing, then capacity, in that priority order, a real LLM call over data we already computed, not the model guessing at availability itself. Let's accept its suggestion.",
      action: async () => {
        const btn = await Demo.waitFor(() =>
          Array.from(document.getElementById("booking-outcome").querySelectorAll("button")).find((b) =>
            b.textContent.includes("Book this instead")
          )
        );
        if (!btn) return;
        await Demo.clickWithFeedback(btn);
        await Demo.waitFor(() => document.getElementById("booking-outcome").textContent.includes("Booked as HELD"));
        const reservations = await api(`/restaurants/${restaurantId}/reservations`);
        const latest = reservations[0];
        if (latest) demoCreatedReservationIds.push(latest.id);
      },
    },
    {
      caption: "A different edge case now: what happens when a party doesn't meet a table's minimum size? Does the system just block them and lose the booking outright?",
      action: async () => {
        Demo.highlight(document.getElementById("availability-form"));
        await submitAvailabilityForm("20:00", 2);
      },
    },
    {
      caption: "Table 4 still shows up, just flagged, minimum party size is a soft preference, never a hard block in the core booking API. That's a deliberate architectural choice, not a missing validation. Let's ask the agent whether it's worth seating them here anyway.",
      action: async () => {
        const row = await Demo.waitFor(() =>
          Demo.findRowByTitleSubstring(document.getElementById("availability-results"), table4Name)
        );
        const notice = row?.nextElementSibling?.classList.contains("callout") ? row.nextElementSibling : null;
        const btn = notice?.querySelector("button");
        if (!btn) return;
        await Demo.clickWithFeedback(btn);
        await Demo.waitFor(() => notice.className.includes("agent-result") || notice.className.includes("error"));
      },
    },
    {
      caption: "It weighs real signals here, current demand, how idle this table's been today, how close to closing, before recommending, not a fixed threshold. This is the kind of context-dependent judgment call that doesn't reduce cleanly to an if-statement, which is exactly why it's the agent's job, not hardcoded logic.",
      action: async () => {},
    },
    {
      caption: "One more decision point: is now a good moment for a promotional offer? This reuses the exact same occupancy signal that drives the diner-facing vibe display and dynamic pricing, one computed value, three uses, not three separate systems. Below a threshold, it skips the LLM call entirely rather than paying for a guaranteed no.",
      action: async () => {
        const btn = document.getElementById("recommend-offer-btn");
        Demo.highlight(btn);
        btn.classList.add("demo-pressed");
        await Demo.sleep(160);
        btn.classList.remove("demo-pressed");
        const result = await askForOfferRecommendation();
        if (result?.offer_id) demoCreatedOfferId = result.offer_id;
        await Demo.sleep(500);
      },
    },
    {
      caption: () =>
        demoLastOfferStatus === "PENDING_CONFIRMATION"
          ? "This is the graduated autonomy boundary in action: this discount was above the pre-approved range, so it's sitting here waiting for a real person, badge and all, not gone live on its own."
          : demoLastOfferStatus === "ACTIVE"
          ? "This one landed within the pre-approved range, so it went live immediately, no approval step needed, that's the other half of the same graduated boundary."
          : "No offer was warranted this time, occupancy wasn't low enough to justify one, the threshold check skipped the LLM call entirely rather than paying for a guaranteed no.",
      action: async () => {
        demoLastOfferStatus = null;
        if (!demoCreatedOfferId) {
          Demo.highlight(document.getElementById("offers-list"));
          return;
        }
        const offer = await api(`/restaurants/${restaurantId}/offers`).then((offers) =>
          offers.find((o) => o.id === demoCreatedOfferId)
        );
        demoLastOfferStatus = offer?.status || null;
        Demo.highlight(document.getElementById("offers-list"));
      },
    },
    {
      caption: () =>
        demoLastOfferStatus === "PENDING_CONFIRMATION"
          ? "The agent never even saw that ceiling when it proposed a number, so it couldn't just game staying under it, the boundary is enforced in code afterward. Let's approve it."
          : "Nothing to approve here, moving on.",
      action: async () => {
        if (demoLastOfferStatus !== "PENDING_CONFIRMATION") return;
        const approveBtn = Array.from(document.getElementById("offers-list").querySelectorAll("button")).find(
          (b) => b.textContent === "Approve"
        );
        await Demo.clickWithFeedback(approveBtn);
      },
    },
    {
      caption: "Finally, the actual Reservation Operations Agent: real LLM tool-calling, both skills bound as callable tools, the model reads a plain description and decides which one applies itself, not a hardcoded if-else router matching keywords.",
      action: async () => {
        Demo.highlight(document.getElementById("agent-form"));
        await Demo.typeInto(
          document.getElementById("agent-situation"),
          "A party of 2 wants a table that normally needs 4 people minimum, would that be okay right now?"
        );
        const submitBtn = document.querySelector("#agent-form button[type=submit]");
        await Demo.clickWithFeedback(submitBtn);
        await Demo.waitFor(() => document.getElementById("agent-result").textContent.includes(":"));
      },
    },
    {
      caption: "It correctly routed this to the minimum-party-size skill, the same one triggered manually a moment ago, proving it's real routing, not a special case.",
      action: async () => Demo.highlight(document.getElementById("agent-result")),
    },
    {
      caption: "And staff keep full control throughout, cancelling reuses the same transactional release logic as everything else here, delete the slot claims and update the status together, atomically, so the table is genuinely free again, not just marked as if it were.",
      action: async () => {
        const rows = Array.from(document.getElementById("reservations-list").querySelectorAll(".row"));
        const confirmedRow = rows.find((r) => r.querySelector(".badge")?.textContent === "CONFIRMED");
        if (!confirmedRow) return;
        const cancelBtn = Array.from(confirmedRow.querySelectorAll("button")).find((b) => b.textContent === "Cancel");
        await Demo.clickWithFeedback(cancelBtn);
        await Demo.sleep(600);
      },
    },
    {
      caption: "That's the staff side, booking, conflict handling, and three agent skills, each with a real, distinct autonomy boundary. Now, the diner's side, starting with browsing restaurants by vibe.",
      action: async () => {
        Demo.highlight(document.getElementById("diner-view-link"));
        await Demo.sleep(2000);
        // The demo "ending" by moving on is still an ending, clean up
        // whatever it created before leaving, the same as Restart/Close
        // would, rather than only cleaning up on an explicit stop.
        await cleanupDemoData();
        window.location.href = "/dine?demo=1";
      },
    },
  ];
}

async function cleanupDemoData() {
  for (const id of demoCreatedReservationIds) {
    try {
      await api(`/reservations/${id}/cancel`, { method: "POST" });
    } catch (e) {
      // already cancelled or unreachable, fine to ignore for cleanup
    }
  }
  demoCreatedReservationIds = [];

  if (demoCreatedOfferId) {
    try {
      await api(`/offers/${demoCreatedOfferId}`, { method: "DELETE" });
    } catch (e) {
      // already gone, fine to ignore for cleanup
    }
    demoCreatedOfferId = null;
  }

  await Promise.all([loadReservations(), loadOccupancy(), loadOffers()]);
}

// Kept as the name the demo panel's onReset hook expects; just an
// alias so the intent (this runs on Restart/Close) stays readable.
const resetStaffDemo = cleanupDemoData;

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("run-demo-btn");
  if (btn) {
    btn.onclick = () => {
      demoDate = pickDemoDate();
      demoCreatedReservationIds = [];
      demoCreatedOfferId = null;
      Demo.start(buildStaffSteps(), resetStaffDemo, 7000);
    };
  }
});

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
let demoAltBookingInfo = null;
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
      caption: "This is Reservation Intelligence, a restaurant booking platform with an AI agent layer that helps staff make decisions. Let's walk through it.",
      action: async () => Demo.highlight(document.querySelector("header.topbar")),
    },
    {
      caption: "One quick thing to know going in: every booking is split into 15-minute time slots behind the scenes. That's what makes double-booking truly impossible, more on that after the demo.",
      action: async () => Demo.highlight(document.getElementById("tables-grid").closest(".card")),
    },
    {
      caption: "Quick heads-up: you'll see two different occupancy percentages during this demo, for example one for how full the restaurant is right now, and a separate one for how full a specific future booking's time slot is. Both are correct, just answering different questions.",
      action: async () => Demo.highlight(document.getElementById("occupancy-pill")),
    },
    {
      caption: "Five tables here, each with its own type, capacity, and minimum party size.",
      action: async () => Demo.highlight(document.getElementById("tables-grid").closest(".card")),
    },
    {
      caption: "Let's book Table 1 for two guests at 7 PM.",
      action: async () => {
        Demo.highlight(document.getElementById("availability-form"));
        await submitAvailabilityForm("19:00", 2);
      },
    },
    {
      caption: "Table 1 is free, let's book it.",
      action: async () => {
        const row = await Demo.waitFor(() =>
          Demo.findRowByTitleSubstring(document.getElementById("availability-results"), table1Name)
        );
        await Demo.clickWithFeedback(row?.querySelector("button.primary"));
        await Demo.waitFor(() => document.getElementById("booking-outcome").textContent.includes("Booked as HELD"));
      },
    },
    {
      caption: "It's held, not confirmed yet. If nobody confirms it in time, it's released automatically, so a table can never get stuck.",
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
      caption: "This is that guarantee from the intro getting tested directly: someone else trying to book that exact same table and time, at the same moment.",
      action: async () => {
        const outcomeEl = document.getElementById("booking-outcome");
        Demo.highlight(outcomeEl);
        outcomeEl.innerHTML = `<div class="callout suggest">Simulating a second request for Table 1, 7 PM, right now&hellip;</div>`;
        await Demo.sleep(1400);
        const table1Id = tablesCache.find((t) => t.name === table1Name)?.id;
        await book(table1Id, { date: demoDate, hour: 19, minute: 0, duration: 60, partySize: 2 });
        await Demo.waitFor(() => document.getElementById("booking-outcome").textContent.includes("just became unavailable"));
      },
    },
    {
      caption: "Rejected, that table's genuinely taken. Now the agent steps in to suggest an alternative instead of just failing.",
      action: async () => {
        const btn = document.getElementById("booking-outcome").querySelector("button.agent");
        await Demo.clickWithFeedback(btn);
        await Demo.waitFor(() => document.getElementById("booking-outcome").querySelector(".callout.agent-result, .callout.error"));
      },
    },
    {
      caption: () => {
        if (!demoAltBookingInfo) {
          return "It found an alternative that fits. Let's accept it.";
        }
        const { tableName, basePrice, actualPrice } = demoAltBookingInfo;
        return actualPrice > basePrice
          ? `Booked ${tableName} at $${actualPrice.toFixed(2)}, a bit above its usual $${basePrice.toFixed(2)}, since demand for this time just went up.`
          : `Booked ${tableName} at its usual price, $${actualPrice.toFixed(2)}.`;
      },
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
        if (latest) {
          demoCreatedReservationIds.push(latest.id);
          const table = tablesCache.find((t) => t.id === latest.table_id);
          demoAltBookingInfo = { tableName: table?.name || `Table ${latest.table_id}`, basePrice: table?.base_price ?? 0, actualPrice: latest.price };
        }
      },
    },
    {
      caption: "A different scenario now: a party of two, searching at a time when Table 4 normally needs at least four people.",
      action: async () => {
        Demo.highlight(document.getElementById("availability-form"));
        await submitAvailabilityForm("20:00", 2);
      },
    },
    {
      caption: "Table 4 still shows up, just flagged, since the minimum is a soft preference, not a hard rule. Let's ask the agent if it's still a good idea to seat them here.",
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
      caption: "One more decision: is now a good time to run a promotional offer?",
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
          ? "This discount was above what's pre-approved, so it needs a staff member to approve it first."
          : demoLastOfferStatus === "ACTIVE"
          ? "This discount was within the pre-approved range, so it went live immediately, no approval needed."
          : "No offer this time, occupancy wasn't low enough to justify one.",
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
        demoLastOfferStatus === "PENDING_CONFIRMATION" ? "Let's approve it." : "Nothing to approve here, moving on.",
      action: async () => {
        if (demoLastOfferStatus !== "PENDING_CONFIRMATION") return;
        const approveBtn = Array.from(document.getElementById("offers-list").querySelectorAll("button")).find(
          (b) => b.textContent === "Approve"
        );
        await Demo.clickWithFeedback(approveBtn);
      },
    },
    {
      caption: "Now let's try the agent's free-text interface: describe a situation in plain English, and it figures out what to do.",
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
      caption: "It correctly figured out this is the same minimum-party-size situation from a moment ago.",
      action: async () => Demo.highlight(document.getElementById("agent-result")),
    },
    {
      caption: "Staff can also cancel a reservation any time, that frees the table right away.",
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
      caption: "That covers the staff side. Now let's see the diner's experience, including what happens when a diner tries to book that same Table 1.",
      action: async () => {
        Demo.highlight(document.getElementById("diner-view-link"));
        await Demo.sleep(2000);
        // Table 1's confirmed booking needs to still be live when the
        // diner demo deliberately collides with it a few steps from
        // now, so cleanup of everything this run created is deferred
        // to the diner demo's own end instead of happening here.
        // Carried across the page navigation via sessionStorage, since
        // in-memory state doesn't survive a real page load.
        sessionStorage.setItem(
          "demoCarryState",
          JSON.stringify({
            demoDate,
            reservationIds: demoCreatedReservationIds,
            offerId: demoCreatedOfferId,
          })
        );
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
      demoAltBookingInfo = null;
      Demo.start(buildStaffSteps(), resetStaffDemo, 7000);
    };
  }
});

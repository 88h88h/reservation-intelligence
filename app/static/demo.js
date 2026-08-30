/**
 * Staff-dashboard walkthrough for the explanation video. Drives the
 * real UI, real form fills, real button clicks, real API calls, so
 * what's on screen is genuinely happening, not staged. Ends by
 * navigating into the diner view, where a matching demo auto-continues.
 */

let demoCreatedReservationIds = [];
let demoCreatedOfferId = null;
let demoDate = null;

function pickDemoDate() {
  const d = new Date();
  d.setDate(d.getDate() + 14 + Math.floor(Math.random() * 300));
  return d.toISOString().slice(0, 10);
}

function setInputValue(id, value) {
  document.getElementById(id).value = value;
}

async function submitAvailabilityForm(time, party) {
  setInputValue("res-date", demoDate);
  setInputValue("res-time", time);
  setInputValue("res-party", party);
  document.getElementById("availability-form").dispatchEvent(new Event("submit", { cancelable: true }));
  await Demo.waitFor(() => document.getElementById("availability-results").children.length > 0);
}

function buildStaffSteps() {
  const table1Name = "Table 1"; // window, capacity 2, min 1
  const table4Name = "Table 4"; // patio, capacity 6, min 4

  return [
    {
      caption: "This is the staff operations dashboard, tables, reservations, offers, and the agent, all in one place.",
      action: async () => Demo.highlight(document.querySelector("header.topbar")),
    },
    {
      caption: "Five tables, each with its own type, capacity, and minimum party size.",
      action: async () => Demo.highlight(document.getElementById("tables-grid").closest(".card")),
    },
    {
      caption: "Let's book Table 1, a window table, for two guests at 7 PM.",
      action: async () => {
        Demo.highlight(document.getElementById("availability-form"));
        await submitAvailabilityForm("19:00", 2);
      },
    },
    {
      caption: "Table 1 is free. Booking it now, the same request flow a host would use.",
      action: async () => {
        const row = await Demo.waitFor(() =>
          Demo.findRowByTitleSubstring(document.getElementById("availability-results"), table1Name)
        );
        Demo.highlight(row);
        row.querySelector("button.primary").click();
        await Demo.waitFor(() => document.getElementById("booking-outcome").textContent.includes("Booked as HELD"));
      },
    },
    {
      caption: "It's held, not confirmed yet, that's the atomic slot claim working. Let's confirm it.",
      action: async () => {
        const row = await Demo.waitFor(() => document.getElementById("reservations-list").querySelector(".row"));
        Demo.highlight(row);
        row.querySelector("button.primary").click();
        await Demo.sleep(600);
        const table1Id = tablesCache.find((t) => t.name === table1Name)?.id;
        const reservations = await api(`/restaurants/${restaurantId}/reservations`);
        const match = reservations.find((r) => r.table_id === table1Id && r.status === "CONFIRMED");
        if (match) demoCreatedReservationIds.push(match.id);
      },
    },
    {
      caption: "Now imagine a second request comes in for that exact same table and time, a genuine double-booking attempt.",
      action: async () => {
        Demo.highlight(document.getElementById("booking-outcome"));
        const table1Id = tablesCache.find((t) => t.name === table1Name)?.id;
        await book(table1Id, { date: demoDate, hour: 19, minute: 0, duration: 60, partySize: 2 });
        await Demo.waitFor(() => document.getElementById("booking-outcome").textContent.includes("just became unavailable"));
      },
    },
    {
      caption: "The database rejects it outright, no double-booking is possible. Staff can ask the agent for an alternative.",
      action: async () => {
        const btn = document.getElementById("booking-outcome").querySelector("button.agent");
        Demo.highlight(btn);
        btn.click();
        await Demo.waitFor(() => document.getElementById("booking-outcome").querySelector(".callout.agent-result, .callout.error"));
      },
    },
    {
      caption: "It found the best alternative for this exact request, weighing table type, timing, and capacity. Let's book it.",
      action: async () => {
        const btn = await Demo.waitFor(() =>
          Array.from(document.getElementById("booking-outcome").querySelectorAll("button")).find((b) =>
            b.textContent.includes("Book this instead")
          )
        );
        if (!btn) return;
        Demo.highlight(btn);
        btn.click();
        await Demo.waitFor(() => document.getElementById("booking-outcome").textContent.includes("Booked as HELD"));
        const reservations = await api(`/restaurants/${restaurantId}/reservations`);
        const latest = reservations[0];
        if (latest) demoCreatedReservationIds.push(latest.id);
      },
    },
    {
      caption: "Now something different, a smaller party wanting the patio table, which normally needs at least four people.",
      action: async () => {
        Demo.highlight(document.getElementById("availability-form"));
        await submitAvailabilityForm("20:00", 2);
      },
    },
    {
      caption: "Table 4 still shows up, but flagged below its usual minimum. Let's ask the agent whether it's worth seating them there anyway.",
      action: async () => {
        const row = await Demo.waitFor(() =>
          Demo.findRowByTitleSubstring(document.getElementById("availability-results"), table4Name)
        );
        const notice = row?.nextElementSibling?.classList.contains("callout") ? row.nextElementSibling : null;
        const btn = notice?.querySelector("button");
        if (!btn) return;
        Demo.highlight(notice);
        btn.click();
        await Demo.waitFor(() => notice.className.includes("agent-result") || notice.className.includes("error"));
      },
    },
    {
      caption: "The agent weighs real signals here, current demand, how idle that table's been today, proximity to closing, before recommending.",
      action: async () => {},
    },
    {
      caption: "Let's check whether now is a good moment to run a promotional offer.",
      action: async () => {
        Demo.highlight(document.getElementById("recommend-offer-btn"));
        const result = await askForOfferRecommendation();
        if (result?.offer_id) demoCreatedOfferId = result.offer_id;
        await Demo.sleep(500);
      },
    },
    {
      caption: "Watch the outcome, if the discount is within the pre-approved range it goes live immediately; above it, it waits for a human.",
      action: async () => {
        if (!demoCreatedOfferId) {
          Demo.highlight(document.getElementById("offers-list"));
          return;
        }
        const offer = await api(`/restaurants/${restaurantId}/offers`).then((offers) =>
          offers.find((o) => o.id === demoCreatedOfferId)
        );
        if (offer?.status === "PENDING_CONFIRMATION") {
          const approveBtn = Array.from(document.getElementById("offers-list").querySelectorAll("button")).find(
            (b) => b.textContent === "Approve"
          );
          if (approveBtn) {
            Demo.highlight(approveBtn.closest(".row"));
            approveBtn.click();
          }
        } else {
          Demo.highlight(document.getElementById("offers-list"));
        }
      },
    },
    {
      caption: "Finally, let's talk to the agent directly in plain language and watch it decide which tool applies on its own.",
      action: async () => {
        Demo.highlight(document.getElementById("agent-form"));
        document.getElementById("agent-situation").value =
          "A party of 2 wants a table that normally needs 4 people minimum, would that be okay right now?";
        document.getElementById("agent-form").dispatchEvent(new Event("submit", { cancelable: true }));
        await Demo.waitFor(() => document.getElementById("agent-result").textContent.includes(":"));
      },
    },
    {
      caption: "It correctly identified this as the minimum-party-size question, and reused the exact same skill, no separate code path.",
      action: async () => Demo.highlight(document.getElementById("agent-result")),
    },
    {
      caption: "And staff can cancel anytime, freeing the table back up instantly.",
      action: async () => {
        const rows = Array.from(document.getElementById("reservations-list").querySelectorAll(".row"));
        const confirmedRow = rows.find((r) => r.querySelector(".badge")?.textContent === "CONFIRMED");
        if (!confirmedRow) return;
        Demo.highlight(confirmedRow);
        const cancelBtn = Array.from(confirmedRow.querySelectorAll("button")).find((b) => b.textContent === "Cancel");
        cancelBtn?.click();
        await Demo.sleep(600);
      },
    },
    {
      caption: "That's the staff side, booking, conflict handling, and three agent skills, each with a real, distinct autonomy boundary. Now, the diner's side.",
      action: async () => {
        const link = document.getElementById("diner-view-link");
        Demo.highlight(link);
        await Demo.sleep(2000);
        // The demo "ending" by moving on is still an ending, clean up
        // whatever it created before leaving, the same as Restart/Close
        // would, rather than only cleaning up on an explicit stop.
        await cleanupDemoData();
        window.location.href = link.href + "?demo=1";
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

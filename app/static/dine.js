let restaurantId = null;

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = new Error(data?.detail || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}

function el(html) {
  const template = document.createElement("template");
  template.innerHTML = html.trim();
  return template.content.firstElementChild;
}

function fmtMoney(n) {
  return `$${Number(n).toFixed(2)}`;
}

function tierClass(ratio) {
  if (ratio <= 0.2) return "tier-quiet";
  if (ratio <= 0.5) return "tier-comfortable";
  if (ratio <= 0.8) return "tier-lively";
  return "tier-buzzing";
}

async function init() {
  restaurantId = Number(window.location.pathname.split("/").filter(Boolean).pop());

  const restaurant = await api(`/restaurants/${restaurantId}`);
  document.getElementById("restaurant-name").textContent = restaurant.name;
  document.title = `${restaurant.name} - Book a table`;

  const now = new Date();
  document.getElementById("diner-date").value = now.toISOString().slice(0, 10);

  await Promise.all([loadOccupancy(), loadUsers(), loadActiveOffers()]);
}

// ---------- vibe / occupancy ----------

async function loadOccupancy() {
  const occ = await api(`/restaurants/${restaurantId}/occupancy`);
  const tier = tierClass(occ.occupancy_ratio);

  const label = document.getElementById("vibe-label");
  label.textContent = occ.vibe_label;
  label.className = "vibe-label " + tier;

  const fill = document.getElementById("occupancy-fill");
  fill.style.width = `${Math.round(occ.occupancy_ratio * 100)}%`;
  fill.className = "occupancy-fill " + tier;

  const dots = document.getElementById("occupancy-dots");
  dots.innerHTML = "";
  for (let i = 0; i < occ.total_tables; i++) {
    const dot = document.createElement("span");
    dot.className = "dot" + (i < occ.occupied_tables ? " filled" : "");
    dots.appendChild(dot);
  }

  document.getElementById("occupancy-caption").textContent =
    `${occ.occupied_tables} of ${occ.total_tables} tables full right now`;
}

// ---------- users (who's booking) ----------

async function loadUsers() {
  const users = await api("/users");
  const select = document.getElementById("diner-user");
  select.innerHTML = "";
  users.forEach((u) => {
    const opt = document.createElement("option");
    opt.value = u.id;
    opt.textContent = u.name;
    select.appendChild(opt);
  });
}

// ---------- active offers ----------

async function loadActiveOffers() {
  const offers = await api(`/restaurants/${restaurantId}/offers`);
  const active = offers.filter((o) => o.status === "ACTIVE");
  const section = document.getElementById("offers-section");
  const list = document.getElementById("offers-strip-list");
  list.innerHTML = "";

  if (!active.length) {
    section.style.display = "none";
    return;
  }

  const menuItems = await api(`/restaurants/${restaurantId}/menu-items`);
  active.forEach((o) => {
    const item = menuItems.find((m) => m.id === o.menu_item_id);
    list.appendChild(
      el(`
      <div class="offer-card">
        <div class="main">
          <div class="title">${item ? item.name : "Special offer"}</div>
          <div class="subtitle">Available right now, while tables are open</div>
        </div>
        <div class="discount">${fmtMoney(o.proposed_value)} off</div>
      </div>
    `)
    );
  });
  section.style.display = "flex";
}

// ---------- booking ----------

document.getElementById("booking-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const date = document.getElementById("diner-date").value;
  const [hourStr, minuteStr] = document.getElementById("diner-time").value.split(":");
  const duration = Number(document.getElementById("diner-duration").value);
  const partySize = Number(document.getElementById("diner-party").value);
  const request = { date, hour: Number(hourStr), minute: Number(minuteStr), duration, partySize };

  const resultsEl = document.getElementById("diner-results");
  resultsEl.innerHTML = `<div class="empty">Looking for a table&hellip;</div>`;

  try {
    const available = await api(
      `/restaurants/${restaurantId}/availability?date=${date}&hour=${hourStr}&minute=${minuteStr}&duration_minutes=${duration}&person_count=${partySize}`
    );
    renderResults(available, request);
  } catch (err) {
    resultsEl.innerHTML = "";
    resultsEl.appendChild(el(`<div class="callout error">${err.message}</div>`));
  }
});

function renderResults(tables, request) {
  const resultsEl = document.getElementById("diner-results");
  resultsEl.innerHTML = "";
  if (!tables.length) {
    resultsEl.appendChild(el(`<div class="empty">No tables free at that time. Try a different time?</div>`));
    return;
  }
  tables.forEach((t) => {
    const card = el(`
      <div class="diner-table-card" style="margin-bottom: 0.6rem;">
        <div class="main">
          <div class="title">${t.name} <span class="type-tag">${t.type || "standard"}</span></div>
          <div class="subtitle">Seats up to ${t.capacity} &middot; ${fmtMoney(t.base_price)}</div>
        </div>
        <div class="actions"></div>
      </div>
    `);
    const bookBtn = el(`<button class="primary">Reserve</button>`);
    bookBtn.onclick = () => book(t.id, request);
    card.querySelector(".actions").appendChild(bookBtn);
    resultsEl.appendChild(card);
  });
}

async function book(tableId, request) {
  const resultsEl = document.getElementById("diner-results");
  resultsEl.innerHTML = `<div class="empty">Reserving your table&hellip;</div>`;
  const userId = Number(document.getElementById("diner-user").value);
  const idempotencyKey = crypto.randomUUID();

  try {
    const reservation = await api("/reservations", {
      method: "POST",
      body: JSON.stringify({
        restaurant_id: restaurantId,
        table_id: tableId,
        user_id: userId,
        person_count: request.partySize,
        date: request.date,
        hour: request.hour,
        minute: request.minute,
        duration_minutes: request.duration,
        idempotency_key: idempotencyKey,
      }),
    });
    showConfirmation(reservation, request);
    await loadOccupancy();
  } catch (err) {
    if (err.status === 409) {
      offerAlternative(tableId, request, resultsEl);
    } else {
      resultsEl.innerHTML = "";
      resultsEl.appendChild(el(`<div class="callout error">${err.message}</div>`));
    }
  }
}

function showConfirmation(reservation, request) {
  const resultsEl = document.getElementById("diner-results");
  resultsEl.innerHTML = "";
  const box = el(`
    <div class="confirmation">
      <div class="checkmark">&#10003;</div>
      <h2>You're booked!</h2>
      <p class="hint">${request.date} at ${String(request.hour).padStart(2, "0")}:${String(request.minute).padStart(2, "0")}, ${fmtMoney(reservation.price)}.</p>
      <p class="hint">A staff member will confirm your table shortly.</p>
    </div>
  `);
  resultsEl.appendChild(box);
}

async function offerAlternative(tableId, request, container) {
  container.innerHTML = "";
  const box = el(`<div class="callout error"></div>`);
  box.textContent = "That table just got taken. ";
  const tryBtn = el(`<button class="agent" style="margin-left: 0.4rem;">See what else is open</button>`);
  tryBtn.onclick = async () => {
    box.textContent = "Checking… ";
    try {
      const suggestion = await api("/agent/find-alternatives", {
        method: "POST",
        body: JSON.stringify({
          restaurant_id: restaurantId,
          table_id: tableId,
          date: request.date,
          hour: request.hour,
          minute: request.minute,
          duration_minutes: request.duration,
          person_count: request.partySize,
        }),
      });
      if (!suggestion.has_recommendation) {
        box.className = "callout error";
        box.textContent = "Sorry, nothing else fits right now, try a different time.";
        return;
      }
      box.className = "callout agent-result";
      box.textContent = suggestion.reasoning + " ";
      const bookBtn = el(`<button class="agent" style="margin-left: 0.4rem;">Reserve this instead</button>`);
      bookBtn.onclick = () =>
        book(suggestion.table_id, {
          date: suggestion.date,
          hour: suggestion.hour,
          minute: suggestion.minute,
          duration: suggestion.duration_minutes,
          partySize: request.partySize,
        });
      box.appendChild(bookBtn);
    } catch (err) {
      box.className = "callout error";
      box.textContent = err.message;
    }
  };
  box.appendChild(tryBtn);
  container.appendChild(box);
}

init();

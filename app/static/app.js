let restaurantId = null;
let tablesCache = [];
let menuItemsCache = [];
let lastRequestContext = null; // last availability-check params, reused as default context for the free-text agent panel

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

function fmtDateTime(iso) {
  if (!iso) return "n/a";
  return iso.replace("T", " ").slice(0, 16);
}

function setReasoning(container, className, prefix) {
  container.className = className;
  container.textContent = "";
  if (prefix) container.appendChild(document.createTextNode(prefix));
  return container;
}

// ---------- init ----------

async function init() {
  const restaurants = await api("/restaurants");
  const restaurant = restaurants[0];
  restaurantId = restaurant.id;
  document.getElementById("restaurant-name").textContent = restaurant.name;

  const now = new Date();
  document.getElementById("res-date").value = now.toISOString().slice(0, 10);

  await Promise.all([loadOccupancy(), loadTables(), loadReservations(), loadMenuItems(), loadOffers()]);
}

// ---------- occupancy ----------

async function loadOccupancy() {
  const occ = await api(`/restaurants/${restaurantId}/occupancy`);
  document.getElementById("occupancy-label").textContent = `Occupancy: ${Math.round(occ.occupancy_ratio * 100)}%`;
}

// ---------- tables ----------

async function loadTables() {
  tablesCache = await api(`/restaurants/${restaurantId}/tables`);
  const grid = document.getElementById("tables-grid");
  grid.classList.remove("skeleton");
  grid.innerHTML = "";
  tablesCache.forEach((t) => {
    grid.appendChild(
      el(`
      <div class="table-chip">
        <div class="name">${t.name}</div>
        <div class="meta">${t.type || "standard"} &middot; seats ${t.capacity} &middot; min ${t.min_party_size}</div>
        <div class="meta">${fmtMoney(t.base_price)} base${t.is_bookable ? "" : " &middot; closed"}</div>
      </div>
    `)
    );
  });
}

// ---------- reservations ----------

async function loadReservations() {
  const reservations = await api(`/restaurants/${restaurantId}/reservations`);
  const list = document.getElementById("reservations-list");
  list.classList.remove("skeleton");
  list.innerHTML = "";
  if (!reservations.length) {
    list.appendChild(el(`<div class="empty">No reservations yet.</div>`));
    return;
  }
  reservations.forEach((r) => {
    const table = tablesCache.find((t) => t.id === r.table_id);
    const row = el(`
      <div class="row">
        <div class="main">
          <div class="title">${table ? table.name : "Table " + r.table_id} &middot; ${r.person_count} guests</div>
          <div class="subtitle">${fmtMoney(r.price)} &middot; created ${fmtDateTime(r.created_at)}</div>
        </div>
        <span class="badge ${r.status}">${r.status}</span>
        <div class="actions"></div>
      </div>
    `);
    const actions = row.querySelector(".actions");
    if (r.status === "HELD") {
      const confirmBtn = el(`<button class="primary">Confirm</button>`);
      confirmBtn.onclick = () => actOnReservation(r.id, "confirm");
      actions.appendChild(confirmBtn);
      const cancelBtn = el(`<button>Cancel</button>`);
      cancelBtn.onclick = () => actOnReservation(r.id, "cancel");
      actions.appendChild(cancelBtn);
    } else if (r.status === "CONFIRMED") {
      const cancelBtn = el(`<button>Cancel</button>`);
      cancelBtn.onclick = () => actOnReservation(r.id, "cancel");
      actions.appendChild(cancelBtn);
    }
    list.appendChild(row);
  });
}

async function actOnReservation(id, action) {
  try {
    await api(`/reservations/${id}/${action}`, { method: "POST" });
    await Promise.all([loadReservations(), loadOccupancy()]);
  } catch (e) {
    alert(e.message);
  }
}

// ---------- availability + booking ----------

document.getElementById("availability-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const date = document.getElementById("res-date").value;
  const [hourStr, minuteStr] = document.getElementById("res-time").value.split(":");
  const duration = Number(document.getElementById("res-duration").value);
  const partySize = Number(document.getElementById("res-party").value);

  const resultsEl = document.getElementById("availability-results");
  resultsEl.innerHTML = `<div class="empty">Checking&hellip;</div>`;
  document.getElementById("booking-outcome").innerHTML = "";

  const request = { date, hour: Number(hourStr), minute: Number(minuteStr), duration, partySize };
  lastRequestContext = request;

  try {
    const available = await api(
      `/restaurants/${restaurantId}/availability?date=${date}&hour=${hourStr}&minute=${minuteStr}&duration_minutes=${duration}&person_count=${partySize}`
    );
    renderAvailability(available, request);
  } catch (err) {
    resultsEl.innerHTML = "";
    resultsEl.appendChild(setReasoning(el(`<div class="callout error"></div>`), "callout error", err.message));
  }
});

function renderAvailability(tables, request) {
  const resultsEl = document.getElementById("availability-results");
  resultsEl.innerHTML = "";
  if (!tables.length) {
    resultsEl.appendChild(el(`<div class="empty">No tables free for this time.</div>`));
    return;
  }
  tables.forEach((t) => {
    const row = el(`
      <div class="row">
        <div class="main">
          <div class="title">${t.name} &middot; ${t.type || "standard"}</div>
          <div class="subtitle">seats ${t.capacity} &middot; min ${t.min_party_size} &middot; ${fmtMoney(t.base_price)} base</div>
        </div>
        <div class="actions"></div>
      </div>
    `);
    const actions = row.querySelector(".actions");
    const bookBtn = el(`<button class="primary">Book</button>`);
    bookBtn.onclick = () => book(t.id, request);
    actions.appendChild(bookBtn);
    resultsEl.appendChild(row);

    if (!t.meets_min_party_size) {
      const notice = el(`<div class="callout suggest"></div>`);
      notice.textContent = `This table normally seats a minimum of ${t.min_party_size}. `;
      const askBtn = el(`<button class="agent" style="margin-left: 0.4rem;">Ask agent if it's OK</button>`);
      askBtn.onclick = () => askMinPartyOverride(t.id, request, notice);
      notice.appendChild(askBtn);
      resultsEl.appendChild(notice);
    }
  });
}

async function askMinPartyOverride(tableId, request, container) {
  setReasoning(container, "callout suggest", "Asking the agent…");
  try {
    const decision = await api("/agent/evaluate-min-party-override", {
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
    const prefix = decision.recommend_seating ? "Agent recommends seating them here: " : "Agent recommends against it: ";
    setReasoning(container, "callout " + (decision.recommend_seating ? "agent-result" : "error"), prefix + decision.reasoning);
  } catch (err) {
    setReasoning(container, "callout error", err.message);
  }
}

async function book(tableId, request) {
  const outcomeEl = document.getElementById("booking-outcome");
  outcomeEl.innerHTML = `<div class="empty">Booking&hellip;</div>`;
  const idempotencyKey = crypto.randomUUID();
  try {
    const reservation = await api("/reservations", {
      method: "POST",
      body: JSON.stringify({
        restaurant_id: restaurantId,
        table_id: tableId,
        user_id: 1,
        person_count: request.partySize,
        date: request.date,
        hour: request.hour,
        minute: request.minute,
        duration_minutes: request.duration,
        idempotency_key: idempotencyKey,
      }),
    });
    setReasoning(
      outcomeEl,
      "callout agent-result",
      `Booked as HELD, ${fmtMoney(reservation.price)}. Confirm it below in Reservations.`
    );
    document.getElementById("availability-results").innerHTML = "";
    await Promise.all([loadReservations(), loadOccupancy()]);
  } catch (err) {
    if (err.status === 409) {
      outcomeEl.innerHTML = "";
      const box = el(`<div class="callout error"></div>`);
      box.textContent = "That slot just became unavailable. ";
      const findBtn = el(`<button class="agent" style="margin-left: 0.4rem;">Ask agent for alternatives</button>`);
      findBtn.onclick = () => findAlternatives(tableId, request, outcomeEl);
      box.appendChild(findBtn);
      outcomeEl.appendChild(box);
    } else {
      setReasoning(outcomeEl, "callout error", err.message);
    }
  }
}

async function findAlternatives(tableId, request, container) {
  setReasoning(container, "callout suggest", "Asking the agent…");
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
      setReasoning(container, "callout error", suggestion.reasoning);
      return;
    }
    container.innerHTML = "";
    const box = el(`<div class="callout agent-result"></div>`);
    box.textContent = suggestion.reasoning + " ";
    const bookBtn = el(`<button class="agent" style="margin-left: 0.4rem;">Book this instead</button>`);
    bookBtn.onclick = () =>
      book(suggestion.table_id, {
        date: suggestion.date,
        hour: suggestion.hour,
        minute: suggestion.minute,
        duration: suggestion.duration_minutes,
        partySize: request.partySize,
      });
    box.appendChild(bookBtn);
    container.appendChild(box);
  } catch (err) {
    setReasoning(container, "callout error", err.message);
  }
}

// ---------- menu & offers ----------

async function loadMenuItems() {
  menuItemsCache = await api(`/restaurants/${restaurantId}/menu-items`);
  const list = document.getElementById("menu-items-list");
  list.classList.remove("skeleton");
  list.innerHTML = "";
  const select = document.getElementById("offer-menu-item");
  select.innerHTML = "";
  menuItemsCache.forEach((m) => {
    list.appendChild(
      el(`
      <div class="row">
        <div class="main">
          <div class="title">${m.name}</div>
          <div class="subtitle">${fmtMoney(m.price)} &middot; auto-approve up to ${fmtMoney(m.max_auto_discount)} off</div>
        </div>
      </div>
    `)
    );
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = m.name;
    select.appendChild(opt);
  });

  if (!document.getElementById("recommend-offer-btn")) {
    const askOfferBtn = el(
      `<button id="recommend-offer-btn" class="agent" style="margin-top:0.6rem;">Ask agent for a promo recommendation</button>`
    );
    askOfferBtn.onclick = askForOfferRecommendation;
    list.after(askOfferBtn);
  }
}

async function askForOfferRecommendation() {
  let outcome = document.getElementById("offer-recommendation-outcome");
  if (!outcome) {
    outcome = el(`<div id="offer-recommendation-outcome" class="callout suggest"></div>`);
    document.getElementById("manual-offer-form").after(outcome);
  }
  setReasoning(outcome, "callout suggest", "Asking the agent…");
  try {
    const result = await api(`/agent/recommend-offer?restaurant_id=${restaurantId}`, { method: "POST" });
    const prefix = result.has_recommendation
      ? `${result.status === "ACTIVE" ? "Live now" : "Pending your approval"}: `
      : "";
    setReasoning(outcome, "callout agent-result", prefix + result.reasoning);
    await loadOffers();
  } catch (err) {
    setReasoning(outcome, "callout error", err.message);
  }
}

async function loadOffers() {
  const offers = await api(`/restaurants/${restaurantId}/offers`);
  const list = document.getElementById("offers-list");
  list.classList.remove("skeleton");
  list.innerHTML = "";
  if (!offers.length) {
    list.appendChild(el(`<div class="empty">No offers yet.</div>`));
    return;
  }
  offers.forEach((o) => {
    const item = menuItemsCache.find((m) => m.id === o.menu_item_id);
    const row = el(`
      <div class="row">
        <div class="main">
          <div class="title">${item ? item.name : "Item " + o.menu_item_id} &middot; ${fmtMoney(o.proposed_value)} off</div>
          <div class="subtitle">created ${fmtDateTime(o.created_at)}</div>
        </div>
        <span class="badge ${o.status}">${o.status}</span>
        <div class="actions"></div>
      </div>
    `);
    if (o.status === "PENDING_CONFIRMATION") {
      const actions = row.querySelector(".actions");
      const approveBtn = el(`<button class="primary">Approve</button>`);
      approveBtn.onclick = () => actOnOffer(o.id, "approve");
      actions.appendChild(approveBtn);
      const rejectBtn = el(`<button>Reject</button>`);
      rejectBtn.onclick = () => actOnOffer(o.id, "reject");
      actions.appendChild(rejectBtn);
    }
    list.appendChild(row);
  });
}

async function actOnOffer(id, action) {
  try {
    await api(`/offers/${id}/${action}`, { method: "POST" });
    await loadOffers();
  } catch (e) {
    alert(e.message);
  }
}

document.getElementById("manual-offer-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const menuItemId = Number(document.getElementById("offer-menu-item").value);
  const amount = Number(document.getElementById("offer-amount").value);
  try {
    await api("/offers", {
      method: "POST",
      body: JSON.stringify({ menu_item_id: menuItemId, proposed_value: amount }),
    });
    await loadOffers();
  } catch (err) {
    alert(err.message);
  }
});

// ---------- agent free-text panel ----------

document.getElementById("agent-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const situation = document.getElementById("agent-situation").value.trim();
  const resultEl = document.getElementById("agent-result");
  if (!situation) return;
  setReasoning(resultEl, "callout suggest", "Thinking…");

  const ctx = lastRequestContext || { date: document.getElementById("res-date").value, hour: 19, minute: 0, duration: 60, partySize: 2 };
  const defaultTableId = tablesCache.length ? tablesCache[0].id : null;

  try {
    const response = await api("/agent/handle", {
      method: "POST",
      body: JSON.stringify({
        situation,
        restaurant_id: restaurantId,
        table_id: defaultTableId,
        date: ctx.date,
        hour: ctx.hour,
        minute: ctx.minute,
        duration_minutes: ctx.duration,
        person_count: ctx.partySize,
      }),
    });
    if (!response.handled) {
      setReasoning(resultEl, "callout error", response.message);
      return;
    }
    resultEl.innerHTML = "";
    const label = el(`<strong></strong>`);
    label.textContent = response.tool_used + ": ";
    resultEl.appendChild(label);
    resultEl.className = "callout agent-result";
    resultEl.appendChild(document.createTextNode(response.result.reasoning || JSON.stringify(response.result)));
    await Promise.all([loadOffers(), loadReservations()]);
  } catch (err) {
    setReasoning(resultEl, "callout error", err.message);
  }
});

init();

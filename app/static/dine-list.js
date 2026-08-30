async function api(path) {
  const res = await fetch(path);
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.detail || `Request failed (${res.status})`);
  return data;
}

function el(html) {
  const template = document.createElement("template");
  template.innerHTML = html.trim();
  return template.content.firstElementChild;
}

function tierClass(ratio) {
  if (ratio <= 0.2) return "tier-quiet";
  if (ratio <= 0.5) return "tier-comfortable";
  if (ratio <= 0.8) return "tier-lively";
  return "tier-buzzing";
}

async function init() {
  const restaurants = await api("/restaurants");
  const list = document.getElementById("restaurant-list");
  list.classList.remove("skeleton");
  list.innerHTML = "";

  const withOccupancy = await Promise.all(
    restaurants.map(async (r) => ({ restaurant: r, occupancy: await api(`/restaurants/${r.id}/occupancy`) }))
  );

  withOccupancy.forEach(({ restaurant, occupancy }) => {
    const tier = tierClass(occupancy.occupancy_ratio);
    const card = el(`
      <a class="restaurant-card" href="/dine/${restaurant.id}">
        <div class="main">
          <div class="name">${restaurant.name}</div>
          <div class="vibe-mini ${tier}"><span class="dot"></span>${occupancy.vibe_label}</div>
          <div class="caption">${occupancy.occupied_tables} of ${occupancy.total_tables} tables full right now</div>
        </div>
        <div class="arrow">&#8594;</div>
      </a>
    `);
    list.appendChild(card);
  });
}

init();

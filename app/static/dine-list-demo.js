/**
 * Restaurant browse-list walkthrough, the actual demonstration of the
 * "compare by vibe" feature: three restaurants seeded with genuinely
 * different occupancy, not identical placeholders. Auto-continues from
 * the staff demo (?demo=1) or runs standalone via its own button, then
 * clicks into The Rosemary to continue the chain into that page's demo.
 */

function buildDineListSteps() {
  return [
    {
      caption: "Three restaurants, each shows its own live occupancy, or 'vibe'. Let's compare them.",
      action: async () => {
        const cards = Array.from(document.querySelectorAll(".restaurant-card"));
        for (const card of cards) {
          Demo.highlight(card);
          await Demo.sleep(700);
        }
      },
    },
    {
      caption: () => {
        const labels = Array.from(document.querySelectorAll(".restaurant-card")).map(
          (c) => `${c.querySelector(".name")?.textContent}: ${c.querySelector(".vibe-mini")?.textContent}`
        );
        return `${labels.join(". ")}.`;
      },
      action: async () => Demo.highlight(document.querySelector(".restaurant-card")?.closest("main")),
    },
    {
      caption: "Let's look at The Rosemary specifically.",
      action: async () => {
        const card = Array.from(document.querySelectorAll(".restaurant-card")).find((c) =>
          c.querySelector(".name")?.textContent.includes("The Rosemary")
        );
        if (!card) return;
        card.href = card.getAttribute("href") + "?demo=1";
        await Demo.clickWithFeedback(card);
      },
    },
  ];
}

function startDineListDemo() {
  Demo.start(buildDineListSteps(), async () => {}, 6000);
}

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.getElementById("run-demo-btn");
  if (btn) btn.onclick = () => startDineListDemo();

  if (new URLSearchParams(window.location.search).get("demo") === "1") {
    const tryStart = () => {
      if (document.querySelector(".restaurant-card")) {
        setTimeout(startDineListDemo, 800);
      } else {
        setTimeout(tryStart, 200);
      }
    };
    tryStart();
  }
});

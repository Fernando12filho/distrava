// Drag a session card onto another day column. The card moves immediately and
// shows a saving state; the page reloads from the server once the move is
// stored, or the card snaps back if the save fails.
function initCoachBoard() {
  const grid = document.getElementById("week-grid");
  const errorBanner = document.getElementById("move-error");
  if (!grid) return;

  let dragged = null;
  let origin = null;

  function clearTargets() {
    grid.querySelectorAll(".drop-target").forEach((col) => col.classList.remove("drop-target"));
  }

  grid.addEventListener("dragstart", (event) => {
    const card = event.target.closest("[data-move-url]");
    if (!card) return;
    dragged = card;
    origin = card.parentElement;
    card.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", card.dataset.moveUrl);
  });

  grid.addEventListener("dragend", () => {
    if (dragged) dragged.classList.remove("dragging");
    clearTargets();
  });

  grid.addEventListener("dragover", (event) => {
    const column = event.target.closest(".day-col");
    if (!column || !dragged) return;
    event.preventDefault();
    if (!column.classList.contains("drop-target")) {
      clearTargets();
      column.classList.add("drop-target");
    }
  });

  grid.addEventListener("drop", async (event) => {
    const column = event.target.closest(".day-col");
    if (!column || !dragged) return;
    event.preventDefault();
    clearTargets();

    const card = dragged;
    dragged = null;
    if (column.contains(origin)) return;

    column.querySelector(".day-sessions").appendChild(card);
    card.classList.add("is-saving");
    errorBanner.hidden = true;

    const body = new FormData();
    body.append("day_index", column.dataset.day);
    try {
      const response = await fetch(card.dataset.moveUrl, {
        method: "POST",
        body,
        headers: { "X-Requested-With": "fetch" },
      });
      if (!response.ok) throw new Error(`move failed: ${response.status}`);
      window.location.reload();
    } catch (error) {
      origin.appendChild(card);
      card.classList.remove("is-saving");
      errorBanner.hidden = false;
    }
  });
}

// Set edits reload the page; until they do, the form shows it's saving and
// can't be submitted twice.
document.addEventListener("submit", (event) => {
  const form = event.target.closest("[data-saving-form]");
  if (!form) return;
  form.classList.add("is-saving");
  const button = form.querySelector("button[type=submit]");
  if (button) button.textContent = "Saving…";
});

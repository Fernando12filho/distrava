// Drag a session card onto another day column. The card moves immediately and
// shows a saving state; the board re-renders from the server once the move is
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
      const page = await fetch(window.location.href);
      swapCoachLayout(await page.text(), page.url);
    } catch (error) {
      origin.appendChild(card);
      card.classList.remove("is-saving");
      errorBanner.hidden = false;
    }
  });
}

// Replaces the board and the Coach panel with a fresh render, keeping the
// page (and the left bar, scroll position, open panels) where it was.
function swapCoachLayout(html, url, { scrollThread = false } = {}) {
  const fresh = new DOMParser().parseFromString(html, "text/html").querySelector(".coach-layout");
  const current = document.querySelector(".coach-layout");
  if (!fresh || !current) {
    window.location.assign(url);
    return;
  }
  const boardScroll = current.querySelector(".coach-board").scrollTop;
  current.replaceWith(fresh);
  fresh.querySelector(".coach-board").scrollTop = boardScroll;
  const panelBody = fresh.querySelector(".coach-panel-body");
  if (scrollThread && panelBody) panelBody.scrollTop = panelBody.scrollHeight;
  history.replaceState(null, "", url);
  initCoachBoard();
  if (window.syncCollapsibles) window.syncCollapsibles();
}

// The question appears in the thread at once, with the coach visibly working,
// so a slow model never looks like a frozen page.
function showPendingMessage(form) {
  const textarea = form.querySelector("textarea");
  const text = textarea.value.trim();
  const panelBody = document.querySelector(".coach-panel-body");
  let thread = panelBody.querySelector(".coach-thread");
  if (!thread) {
    thread = document.createElement("div");
    thread.className = "coach-thread";
    panelBody.appendChild(thread);
  }

  const question = document.createElement("div");
  question.className = "msg user";
  question.textContent = text;
  const thinking = document.createElement("div");
  thinking.className = "msg coach thinking";
  const who = document.createElement("span");
  who.className = "who";
  who.textContent = "COACH";
  thinking.append(who, "Coach is thinking…");
  thread.append(question, thinking);
  textarea.value = "";
  growComposer(textarea);
  panelBody.scrollTop = panelBody.scrollHeight;

  return {
    fail() {
      question.remove();
      thinking.remove();
      const note = document.createElement("span");
      note.className = "msg-note";
      note.textContent = "Couldn't reach the coach. Nothing changed; your message is back in the box.";
      thread.appendChild(note);
      textarea.value = text;
      growComposer(textarea);
    },
  };
}

// A chat reads from its latest message, so a reload opens there, not at the top.
function scrollThreadToEnd() {
  const panelBody = document.querySelector(".coach-panel-body");
  if (panelBody && panelBody.querySelector(".coach-thread")) panelBody.scrollTop = panelBody.scrollHeight;
}

// DS-07: the message box fits what's typed; the CSS max-height caps it at about
// 8 lines, after which it scrolls inside.
function growComposer(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = `${textarea.scrollHeight}px`;
}

// Forms marked data-live-form post in the background and re-render the board
// and panel in place instead of reloading the whole page.
function initLiveForms() {
  document.addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-live-form]");
    if (!form) return;
    event.preventDefault();
    if (form.classList.contains("is-saving")) return;

    const body = new FormData(form);
    const isQuestion = form.classList.contains("composer");
    const pending = isQuestion ? showPendingMessage(form) : null;
    const button = event.submitter || form.querySelector("button[type=submit]");
    // innerHTML, not text: icon buttons (send, new chat) must come back intact.
    const label = button.innerHTML;
    form.classList.add("is-saving");
    button.disabled = true;
    // An empty busy label keeps the button as it is: the thread shows the wait.
    if (form.dataset.busyLabel !== "") button.textContent = form.dataset.busyLabel || "Saving…";

    try {
      const response = await fetch(form.action, { method: "POST", body });
      if (!response.ok) throw new Error(`save failed: ${response.status}`);
      swapCoachLayout(await response.text(), response.url, { scrollThread: isQuestion });
    } catch (error) {
      form.classList.remove("is-saving");
      button.disabled = false;
      button.innerHTML = label;
      if (pending) pending.fail();
      else document.getElementById("move-error").hidden = false;
    }
  });

  // DS-07, as in Claude and ChatGPT: Enter sends, Shift+Enter makes a new line.
  // Not while an input method is still composing a character.
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    const form = event.target.closest(".composer[data-live-form]");
    if (!form) return;
    event.preventDefault();
    form.requestSubmit();
  });

  document.addEventListener("input", (event) => {
    if (event.target.matches(".composer textarea")) growComposer(event.target);
  });
}

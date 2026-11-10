// DS-12: left and right arrows walk through activities like the Newer / Older
// buttons, unless you're typing or adjusting a control.
document.addEventListener("keydown", (event) => {
  if (event.target.closest("input, select, textarea, [contenteditable]")) return;
  if (event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
  const direction = { ArrowLeft: "newer", ArrowRight: "older" }[event.key];
  const link = direction && document.querySelector(`[data-nav="${direction}"]`);
  if (link) window.location.assign(link.href);
});

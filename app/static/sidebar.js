// The collapsed/expanded choice is remembered on this machine; base.html reads
// it back in <head> so the page never flashes the wrong state.
(() => {
  const KEY = "distrava.sidebarCollapsed";
  const root = document.documentElement;
  const toggle = document.querySelector("[data-sidebar-toggle]");
  if (!toggle) return;

  const sync = () => {
    const collapsed = root.classList.contains("sidebar-collapsed");
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.title = collapsed ? "Show sidebar" : "Hide sidebar";
  };

  toggle.addEventListener("click", () => {
    const collapsed = root.classList.toggle("sidebar-collapsed");
    try {
      localStorage.setItem(KEY, collapsed ? "1" : "0");
    } catch (e) {}
    sync();
    // Chart.js re-measures on window resize, not when its container widens.
    window.dispatchEvent(new Event("resize"));
  });

  sync();
})();

// The collapsed/expanded choice is remembered on this machine; base.html reads
// it back in <head> so the page never flashes the wrong state.
(() => {
  const KEY = "distrava.sidebarCollapsed";
  // Must match the transitions in style.css (DS-02).
  const FADE_MS = 120;
  const RESIZE_MS = 220;

  const root = document.documentElement;
  const toggle = document.querySelector("[data-sidebar-toggle]");
  if (!toggle) return;

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  let busy = false;

  const sync = () => {
    const collapsed = root.classList.contains("sidebar-collapsed");
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.title = collapsed ? "Show sidebar" : "Hide sidebar";
  };

  const remember = (collapsed) => {
    try {
      localStorage.setItem(KEY, collapsed ? "1" : "0");
    } catch (e) {}
  };

  // Chart.js re-measures on window resize, not when its container widens.
  const reflowCharts = () => window.dispatchEvent(new Event("resize"));

  toggle.addEventListener("click", async () => {
    if (busy) return;
    const collapse = !root.classList.contains("sidebar-collapsed");
    remember(collapse);

    if (reducedMotion.matches) {
      root.classList.toggle("sidebar-collapsed", collapse);
      sync();
      reflowCharts();
      return;
    }

    busy = true;
    root.classList.add("sidebar-fading");
    await wait(FADE_MS);
    root.classList.toggle("sidebar-collapsed", collapse);
    sync();
    await wait(RESIZE_MS);
    root.classList.remove("sidebar-fading");
    reflowCharts();
    busy = false;
  });

  sync();
})();

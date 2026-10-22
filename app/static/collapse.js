// Side panels that collapse to a rail: the left bar (DS-02) and the Coach
// panel (DS-04). Each choice is remembered on this machine; base.html reads it
// back in <head> so the page never flashes the wrong state.
(() => {
  // Must match the transitions in style.css.
  const FADE_MS = 120;
  const RESIZE_MS = 220;

  const PANELS = [
    { toggle: "[data-sidebar-toggle]", name: "sidebar", key: "distrava.sidebarCollapsed", label: "sidebar" },
    { toggle: "[data-coach-panel-toggle]", name: "coach-panel", key: "distrava.coachPanelCollapsed", label: "coach" },
  ];

  const root = document.documentElement;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  // Chart.js re-measures on window resize, not when its container widens.
  const reflowCharts = () => window.dispatchEvent(new Event("resize"));

  function collapsible({ toggle: selector, name, key, label }) {
    const collapsedClass = `${name}-collapsed`;
    const fadingClass = `${name}-fading`;
    let busy = false;

    const toggles = () => document.querySelectorAll(selector);
    const sync = () => {
      const collapsed = root.classList.contains(collapsedClass);
      toggles().forEach((t) => {
        t.setAttribute("aria-expanded", String(!collapsed));
        t.title = `${collapsed ? "Show" : "Hide"} ${label}`;
      });
    };

    const remember = (collapsed) => {
      try {
        localStorage.setItem(key, collapsed ? "1" : "0");
      } catch (e) {}
    };

    // Delegated, so toggles swapped in later (the Coach page re-renders its
    // panel in place) keep working.
    document.addEventListener("click", async (event) => {
      if (!event.target.closest(selector) || busy) return;
      const collapse = !root.classList.contains(collapsedClass);
      remember(collapse);

      if (reducedMotion.matches) {
        root.classList.toggle(collapsedClass, collapse);
        sync();
        reflowCharts();
        return;
      }

      busy = true;
      root.classList.add(fadingClass);
      await wait(FADE_MS);
      root.classList.toggle(collapsedClass, collapse);
      sync();
      await wait(RESIZE_MS);
      root.classList.remove(fadingClass);
      reflowCharts();
      busy = false;
    });

    sync();
    return sync;
  }

  const syncs = PANELS.map(collapsible);
  window.syncCollapsibles = () => syncs.forEach((sync) => sync());
})();

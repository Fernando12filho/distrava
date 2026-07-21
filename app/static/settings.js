function initSettingsForm(postUrl) {
  const form = document.getElementById("settings-form");
  const saveStatus = document.getElementById("save-status");
  const maxHrInput = document.getElementById("max-hr-input");
  const restingHrInput = document.getElementById("resting-hr-input");
  const zoneChips = document.querySelectorAll("#hr-zones-list .hr-zone-chip");
  const unitsInput = document.getElementById("units-input");
  const unitsButtons = document.querySelectorAll("#units-segmented .segmented-btn");
  const wipeForm = document.getElementById("wipe-form");
  const weightInput = document.getElementById("weight-input");
  const weightUnitLabel = document.getElementById("weight-unit-label");
  const LB_PER_KG = 2.20462262;

  let saveTimer = null;

  function markDirty() {
    saveStatus.textContent = "Unsaved changes · auto-saved locally";
    saveStatus.classList.add("dirty");
    clearTimeout(saveTimer);
    saveTimer = setTimeout(autosave, 700);
  }

  function markSaved() {
    saveStatus.textContent = "All changes saved";
    saveStatus.classList.remove("dirty");
  }

  async function autosave() {
    const formData = new FormData(form);
    try {
      await fetch(postUrl, { method: "POST", body: formData, headers: { "X-Requested-With": "fetch" } });
      markSaved();
    } catch (err) {
      /* keep dirty status; next edit will retry */
    }
  }

  function recomputeZones() {
    const maxHr = parseInt(maxHrInput.value, 10) || parseInt(maxHrInput.placeholder, 10) || 190;
    const restingHr = parseInt(restingHrInput.value, 10) || parseInt(restingHrInput.placeholder, 10) || 60;
    const reserve = maxHr - restingHr;
    zoneChips.forEach((chip, i) => {
      const lo = parseFloat(chip.dataset.lo);
      const hi = parseFloat(chip.dataset.hi);
      const loBpm = Math.round(restingHr + lo * reserve);
      const hiBpm = Math.round(restingHr + hi * reserve);
      chip.querySelector(".hr-zone-bpm").textContent =
        i === 0 ? "< " + hiBpm + " bpm" : loBpm + "–" + hiBpm + " bpm";
    });
  }

  form.addEventListener("input", () => {
    recomputeZones();
    markDirty();
  });

  unitsButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const previousUnits = unitsInput.value;
      const nextUnits = btn.dataset.units;
      if (nextUnits === previousUnits) return;

      unitsButtons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      unitsInput.value = nextUnits;

      if (weightInput && weightInput.value) {
        const current = parseFloat(weightInput.value);
        if (!isNaN(current)) {
          const kg = previousUnits === "imperial" ? current / LB_PER_KG : current;
          const converted = nextUnits === "imperial" ? kg * LB_PER_KG : kg;
          weightInput.value = converted.toFixed(1);
        }
      }
      if (weightUnitLabel) {
        weightUnitLabel.textContent = nextUnits === "imperial" ? "lb" : "kg";
      }

      markDirty();
    });
  });

  if (wipeForm) {
    wipeForm.addEventListener("submit", (e) => {
      if (!confirm("Permanently delete all imported activities? This cannot be undone.")) {
        e.preventDefault();
      }
    });
  }
}

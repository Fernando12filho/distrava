// Forms marked data-saving-form reload the page when they're stored; until
// then the form shows it's saving and can't be submitted twice.
document.addEventListener("submit", (event) => {
  const form = event.target.closest("[data-saving-form]");
  if (!form) return;
  form.classList.add("is-saving");
  const button = event.submitter || form.querySelector("button[type=submit]");
  if (button) button.textContent = "Saving…";
});

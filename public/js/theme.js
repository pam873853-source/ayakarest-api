/* Applies saved theme before first paint (theme preference only — never secrets). */
(function () {
  try {
    var t = localStorage.getItem("ayaka-theme");
    if (!t) t = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", t);
  } catch (e) { /* ignore */ }
  document.documentElement.classList.remove("no-js");
})();

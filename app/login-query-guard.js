/* REelo login query guard */
(function () {
  "use strict";

  function requestedLogin() {
    try {
      return new URLSearchParams(window.location.search).get("auth") === "login";
    } catch {
      return false;
    }
  }

  function openLoginSheet() {
    if (!requestedLogin()) return false;
    const sheet = document.getElementById("auth");
    if (!sheet) return false;

    sheet.classList.add("show");
    sheet.style.display = "flex";
    sheet.setAttribute("aria-hidden", "false");
    sheet.dataset.loginRequested = "true";

    const username = document.getElementById("authUser");
    if (username && document.activeElement !== username) {
      window.setTimeout(() => username.focus({ preventScroll: true }), 0);
    }
    return true;
  }

  function start() {
    openLoginSheet();
    [100, 400, 1200, 2500].forEach((delay) => window.setTimeout(openLoginSheet, delay));
    const observer = new MutationObserver(() => openLoginSheet());
    observer.observe(document.documentElement, { childList: true, subtree: true });
    window.addEventListener("pagehide", () => observer.disconnect(), { once: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
  window.addEventListener("pageshow", openLoginSheet);
}());

// Registers the PWA service worker when the page window is friendly.
// The worker is fetched from /sw.js which carries Service-Worker-Allowed: /.
(function () {
  "use strict";
  if (!("serviceWorker" in navigator)) return;
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {
      // Registration failure is non-fatal; the app still works online.
    });
  });
})();
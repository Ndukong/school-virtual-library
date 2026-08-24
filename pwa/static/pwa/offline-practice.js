// Offline practice (WP8): lets a student store one quiz on this device and
// answer it without the internet. Submissions made offline are queued in
// localStorage and replayed (in order) when the connection returns.
//
// Privacy: the queue is device-local and holds only the student's own
// answers; the server still enforces ownership and validity when the POST is
// replayed. The attempt page itself is only cached after the student taps
// "Take this quiz offline".
(function () {
  "use strict";
  var ATTEMPTS_CACHE = "svl-attempts-v1";
  var QUEUE_KEY = "svl-attempt-queue";

  function el() {
    return document.querySelector("[data-offline-practice]");
  }

  function readQueue() {
    try {
      var raw = localStorage.getItem(QUEUE_KEY);
      var parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return [];
    }
  }

  function writeQueue(queue) {
    try {
      localStorage.setItem(QUEUE_KEY, JSON.stringify(queue.slice(-10)));
    } catch (err) { /* storage full: answers were lost; offline save is best-effort */ }
  }

  function statusText(text) {
    var node = el();
    if (node) {
      var out = node.querySelector("[data-offline-status]");
      if (out) out.textContent = text;
    }
  }

  function cacheAttemptPage() {
    if (!("caches" in window)) return Promise.resolve(false);
    var path = window.location.pathname;
    return caches.open(ATTEMPTS_CACHE).then(function (cache) {
      return Promise.all([
        cache.add(path).catch(function () { return true; }),
        cache.add("/static/css/site.css").catch(function () { return true; }),
      ]).then(function () { return true; });
    });
  }

  function flush() {
    var node = el();
    var submitUrl = node ? node.getAttribute("data-submit-url") : "";
    var queue = readQueue();
    if (!queue.length || !submitUrl) return;

    var item = queue[0];
    var attempt = fetch(submitUrl, {
      method: "POST",
      body: item.body,
      credentials: "same-origin",
      redirect: "follow",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });

    attempt.then(function (response) {
      if (response.redirected && response.url.indexOf("/login/") !== -1) {
        // Session ended while offline: keep the answers, ask for login.
        statusText(node.getAttribute("data-login-needed-label"));
        return;
      }
      if (response.ok && response.redirected) {
        queue.shift();
        writeQueue(queue);
        window.location.href = response.url;
        return;
      }
      if (response.status === 403 || response.status === 404) {
        queue.shift(); // ownership rejected / attempt gone: stop retrying
        writeQueue(queue);
        statusText("");
        flush();
        return;
      }
      // Transient failure or a form error page: try again on the next event.
      statusText(node.getAttribute("data-retry-label"));
    }).catch(function () {
      // Still offline (or the fetch raced the connection): keep the queue.
    });
  }

  function init() {
    var node = el();
    if (!node) return;

    var form = node.querySelector("form[data-offline-form]");
    var cacheButton = node.querySelector("[data-offline-cache]");
    if (!form || !cacheButton) return;

    cacheButton.addEventListener("click", function (event) {
      event.preventDefault();
      cacheButton.disabled = true;
      cacheAttemptPage().then(function () {
        statusText(node.getAttribute("data-saved-label"));
      }).finally(function () {
        cacheButton.disabled = false;
      });
    });

    form.addEventListener("submit", function (event) {
      if (navigator.onLine) return true; // normal online submit
      event.preventDefault();
      var body = new URLSearchParams(new FormData(form)).toString();
      var queue = readQueue();
      queue.push({
        url: node.getAttribute("data-submit-url"),
        body: body,
      });
      writeQueue(queue);
      statusText(node.getAttribute("data-queued-label"));
      return false;
    });

    window.addEventListener("online", flush);
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", flush);
    } else {
      flush();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
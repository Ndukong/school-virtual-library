// Offline reading (WP8): the reader panel on a resource page lets the user
// explicitly save a document to this device. Saving caches the read page
// plus its PDF stream URL under svl-files-v1; the service worker serves
// those exact URLs from cache when the network is gone. Nothing is cached
// unless the user asks for it.
(function () {
  "use strict";
  var CACHE_NAME = "svl-files-v1";

  function panel() {
    return document.querySelector("[data-offline-reader]");
  }

  function buttons() {
    var node = panel();
    if (!node) return null;
    return {
      panel: node,
      status: node.querySelector("[data-offline-status]"),
      save: node.querySelector("[data-offline-save]"),
      remove: node.querySelector("[data-offline-remove]"),
    };
  }

  function urls() {
    var node = panel();
    return [node.getAttribute("data-read-url"), node.getAttribute("data-stream-url")]
      .filter(Boolean);
  }

  function fmtSize(bytes) {
    if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + " MB";
    if (bytes >= 1024) return Math.round(bytes / 1024) + " KB";
    return bytes + " B";
  }

  function setSavedState(saved) {
    var parts = buttons();
    if (!parts) return;
    parts.save.hidden = saved;
    parts.remove.hidden = !saved;
    if (saved) {
      var size = parseInt(panel().getAttribute("data-size") || "0", 10);
      parts.status.textContent = parts.panel.getAttribute("data-saved-label") + " (" + fmtSize(size) + ")";
    } else {
      parts.status.textContent = "";
    }
  }

  function isSaved() {
    var urlsToCheck = urls();
    if (!urlsToCheck.length) return Promise.resolve(false);
    return caches.open(CACHE_NAME).then(function (cache) {
      return Promise.all(urlsToCheck.map(function (u) { return cache.match(u); })).then(function (hits) {
        return hits.every(Boolean);
      });
    });
  }

  function save() {
    return caches.open(CACHE_NAME).then(function (cache) {
      return Promise.all(urls().map(function (u) {
        return cache.add(u).catch(function () { return true; });
      }));
    });
  }

  function remove() {
    return caches.open(CACHE_NAME).then(function (cache) {
      return Promise.all(urls().map(function (u) { return cache.delete(u); }));
    });
  }

  function refresh() {
    isSaved().then(setSavedState).catch(function () {});
  }

  function init() {
    if (!panel() || !("caches" in window)) return;

    var parts = buttons();
    parts.save.addEventListener("click", function (event) {
      event.preventDefault();
      parts.save.disabled = true;
      save().then(refresh).finally(function () {
        parts.save.disabled = false;
      });
    });
    parts.remove.addEventListener("click", function (event) {
      event.preventDefault();
      parts.remove.disabled = true;
      remove().then(refresh).finally(function () {
        parts.remove.disabled = false;
      });
    });

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", refresh);
    } else {
      refresh();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
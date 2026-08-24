// Cleared on the log-in page: arriving here means the previous session ended,
// so offline copies from that session are erased (shared lab machines,
// AGENTS.md section 6). This only touches the caches the page scripts build.
(function () {
  "use strict";
  if (!("caches" in window)) return;
  Promise.all([
    caches.delete("svl-files-v1"),
    caches.delete("svl-attempts-v1"),
  ]).catch(function () {});
})();
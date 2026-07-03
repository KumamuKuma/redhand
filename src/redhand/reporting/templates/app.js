// redhand dashboard — tiny, dependency-free interactivity (offline-safe).
(function () {
  "use strict";
  function all(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }

  document.addEventListener("click", function (e) {
    var t = e.target;
    if (t && t.id === "expand-all") {
      all("details.case").forEach(function (d) { d.open = true; });
    } else if (t && t.id === "collapse-all") {
      all("details.case").forEach(function (d) { d.open = false; });
    }
  });
})();

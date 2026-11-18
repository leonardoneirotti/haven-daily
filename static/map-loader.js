/* Haven Daily: starts the port chart after the text (#104).
   The basemap is the biggest file of the site (about half of a day page). Loaded with a plain
   <script> tag it held up the whole page; now the text, news and status show first, and this
   file adds the basemap and the chart (map.js) once the page has painted. Both come from the
   same folder as this file: nothing is loaded from another site (hard rule 14). */
(function () {
  "use strict";

  var el = document.getElementById("port-map");
  if (!el || !document.getElementById("map-data") || !window.L || !window.HavenPins) return;

  var root = document.documentElement;
  var note = document.getElementById("chart-loading");
  var folder = document.currentScript.src.replace(/[^/]*$/, ""); // read now: it is gone in callbacks
  root.classList.add("has-map"); // shows the chart's controls and the "Loading chart…" note

  // If a file can't load, the page falls back to the text: the plain-text stand-ins show again.
  function fail() {
    root.classList.remove("has-map");
  }

  function add(name, then) {
    var script = document.createElement("script");
    script.src = folder + name;
    script.async = false; // added scripts run in the order they were added, not as they arrive
    script.onload = then || null;
    script.onerror = fail;
    document.head.appendChild(script);
  }

  function start() {
    add("basemap.js");
    add("map.js", function () {
      // map.js has built the chart; it is drawn in the next frame.
      requestAnimationFrame(function () {
        if (note) note.hidden = true;
      });
    });
  }

  // requestAnimationFrame runs just before the next paint; the timeout moves the start just after it.
  requestAnimationFrame(function () {
    setTimeout(start, 0);
  });
})();

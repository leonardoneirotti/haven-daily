/* Haven Daily: where a numbered marker sits on the chart (#85), who takes a swipe (#111), and the
   card a clicked number opens (#134). Pure: no Leaflet and no page access, so tests/test_pins_geometry.py
   and tests/test_map_upgrades.py can run it in Node. map.js measures the markers and uses these to
   place, merge and nudge them, and to fill the pin card. */
(function (root) {
  "use strict";

  // A marker's box. The first item's number is centred on its place; the rest of the marker runs
  // to the right of it, or (side "left") its labels run to the left of the numbers; rows run down.
  // size: w, h = the whole marker; half = half a number square; lead = width of the numbers in front.
  function boxAt(point, size, side, rows) {
    var left = side === "left" ? point.x - size.half - (size.w - size.lead) : point.x - size.half;
    var top = rows ? point.y - size.half : point.y - size.h / 2;
    return { left: left, right: left + size.w, top: top, bottom: top + size.h };
  }

  // Two boxes closer than `gap` pixels count as overlapping.
  function overlaps(a, b, gap) {
    return a.left < b.right + gap && b.left < a.right + gap && a.top < b.bottom + gap && b.top < a.bottom + gap;
  }

  // Two single markers that would overlap (#148): sides that keep them apart, or null, and then
  // map.js merges them. First the sides they prefer (the ones they had: a number keeps its side),
  // then the outer sides (the western pin's label to the left, the eastern pin's to the right),
  // then the rest. A choice must leave `gap` px between the two, keep both inside the chart's free
  // area (`margin` px from its left and right edges, as map.js places markers) and clear every box
  // in `others`. a, b: the two places on screen; sizeA, sizeB: their marker sizes (see boxAt);
  // preferred: [side of a, side of b]. Returns [side of a, side of b].
  function separateSides(a, b, sizeA, sizeB, preferred, chart, gap, margin, others) {
    var outer = a.x <= b.x ? ["left", "right"] : ["right", "left"];
    var tries = [preferred, outer, ["right", "right"], ["left", "left"], ["left", "right"], ["right", "left"]];
    var left = chart.left + margin, right = chart.right - margin, seen = {};
    for (var i = 0; i < tries.length; i++) {
      var sides = tries[i], key = sides.join(",");
      if (seen[key]) continue;
      seen[key] = true;
      var boxA = boxAt(a, sizeA, sides[0], false), boxB = boxAt(b, sizeB, sides[1], false);
      var fits = [boxA, boxB].every(function (box) { return box.left >= left && box.right <= right; });
      var clear = (others || []).every(function (box) {
        return !overlaps(boxA, box, margin) && !overlaps(boxB, box, margin);
      });
      if (fits && clear && !overlaps(boxA, boxB, gap)) return [sides[0], sides[1]];
    }
    return null;
  }

  // A place on the chart's free area (edges included; left = right edge of the panel). Its marker
  // is shown with its whole number: nudgeInside moves it inward when it sticks out. The home view
  // uses this to decide which of the day's pins are on screen (owner, PR #91).
  function onChart(point, chart) {
    return point.x >= chart.left && point.x <= chart.right && point.y >= chart.top && point.y <= chart.bottom;
  }

  // A marker whose place is on the chart but whose box sticks out of it (a place at the chart's
  // edge, such as 5 East Anchorage on a phone) moves inward just enough to keep `margin` pixels
  // from the edge, so no number is cut. A place off the chart, or under the panel, is left alone:
  // its marker is not pulled into view. chart = the free area (left = right edge of the panel).
  function nudgeInside(box, point, chart, margin) {
    if (!onChart(point, chart)) return { x: 0, y: 0 };
    var left = chart.left + margin, right = chart.right - margin, top = chart.top + margin, bottom = chart.bottom - margin;
    return {
      x: box.left < left ? left - box.left : box.right > right ? right - box.right : 0,
      y: box.top < top ? top - box.top : box.bottom > bottom ? bottom - box.bottom : 0,
    };
  }

  // Who takes a one-finger swipe that starts on the chart (#111): "map", "page", or null while it
  // is too short to tell (under `threshold` pixels both ways). A mostly vertical swipe goes to the
  // page whenever the chart can't move that way, so the page never gets stuck on the chart; any
  // other swipe moves the chart (one-finger drag, P1). room: how many pixels the chart can still
  // move to show more of the north and of the south. A finger moving down shows more of the north.
  function swipeTaker(dx, dy, room, threshold) {
    if (Math.abs(dx) < threshold && Math.abs(dy) < threshold) return null;
    if (Math.abs(dy) <= Math.abs(dx)) return "map";
    return (dy > 0 ? room.north : room.south) > 1 ? "map" : "page";
  }

  // The pin card (#134): what opens next to a number clicked on the chart. `item` is one of the
  // page's map callouts (haven/render.py map_payload): title (always English, #153), credit (a
  // Dutch item's source), severity, summary or note, url, translate_url. Everything is escaped;
  // a link that isn't there (no url) is left out. Pure text in, HTML out, so it runs in Node too.
  function escapeText(text) {
    return String(text).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function cardHtml(item, rank) {
    var sev = escapeText(item.severity), links = [];
    if (item.url) links.push('<a class="btn" href="' + escapeText(item.url) + '">Read original ↗</a>');
    if (item.translate_url) links.push('<a class="btn" href="' + escapeText(item.translate_url) + '">Read in English ↗</a>');
    links.push('<a class="btn" href="#item-' + rank + '">Full item ↓</a>');
    var text = item.summary
      ? '<p class="chart-card-summary">' + escapeText(item.summary) + "</p>"
      : item.note ? '<p class="chart-card-summary is-empty">' + escapeText(item.note) + "</p>" : "";
    var credit = item.credit ? '<p class="chart-card-credit">' + escapeText(item.credit) + "</p>" : "";
    return '<div class="chart-card-body" role="dialog" aria-labelledby="chart-card-title" tabindex="-1">' +
      '<p class="chart-card-top"><span class="num num-' + sev + '">' + rank + '</span><span class="sev sev-' + sev + '">' +
      sev + '</span><button type="button" class="btn chart-card-close" data-action="close-card" aria-label="Close" title="Close">' +
      '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
      'aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg></button></p>' +
      '<h3 class="chart-card-title" id="chart-card-title">' + escapeText(item.title) + "</h3>" +
      credit + text + '<p class="chart-card-links">' + links.join("") + "</p></div>";
  }

  root.HavenPins = { boxAt: boxAt, overlaps: overlaps, separateSides: separateSides, onChart: onChart,
    nudgeInside: nudgeInside, swipeTaker: swipeTaker,
    cardHtml: cardHtml };
})(typeof window !== "undefined" ? window : globalThis);

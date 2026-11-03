/* Haven Daily: where a numbered marker sits on the chart (#85).
   Pure geometry in screen pixels: no Leaflet and no page access, so tests/test_pins_geometry.py
   can run it in Node. map.js measures the markers and uses these to place, merge and nudge them. */
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

  // A marker whose place is on the chart but whose box sticks out of it (a place at the chart's
  // edge, such as 5 East Anchorage on a phone) moves inward just enough to keep `margin` pixels
  // from the edge, so no number is cut. A place off the chart, or under the panel, is left alone:
  // its marker is not pulled into view. chart = the free area (left = right edge of the panel).
  function nudgeInside(box, point, chart, margin) {
    if (point.x < chart.left || point.x > chart.right || point.y < chart.top || point.y > chart.bottom) {
      return { x: 0, y: 0 };
    }
    var left = chart.left + margin, right = chart.right - margin, top = chart.top + margin, bottom = chart.bottom - margin;
    return {
      x: box.left < left ? left - box.left : box.right > right ? right - box.right : 0,
      y: box.top < top ? top - box.top : box.bottom > bottom ? bottom - box.bottom : 0,
    };
  }

  root.HavenPins = { boxAt: boxAt, overlaps: overlaps, nudgeInside: nudgeInside };
})(typeof window !== "undefined" ? window : globalThis);

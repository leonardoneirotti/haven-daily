/* Haven Daily port chart.
   Draws the basemap (static/basemap.js), the day's ships and the numbered items
   with Leaflet, and links the chart to the brief: selecting an item flies the
   chart to where it happens, clicking a number on the chart finds the item.
   The page still works without it: everything on the chart is also listed as text. */
(function () {
  "use strict";

  var el = document.getElementById("port-map");
  var dataEl = document.getElementById("map-data");
  if (!el || !dataEl || !window.L || !window.HAVEN_BASEMAP || !window.HavenPins) return;
  document.documentElement.classList.add("has-map");

  var data = JSON.parse(dataEl.textContent);
  var basemap = window.HAVEN_BASEMAP;
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var chart = document.getElementById("chart");
  var focusBox = document.getElementById("chart-focus");
  var focusText = document.getElementById("chart-focus-text");
  var announcer = document.getElementById("chart-announcer");

  // Colours come from the tokens in style.css.
  function token(name) {
    return getComputedStyle(el).getPropertyValue(name).trim();
  }
  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // ---------- The sheet ----------
  // The chart is a fixed "sheet": the area covered by the basemap. It never zooms out
  // past the sheet, and pans past its edge only on the open-sea side under the panel
  // (below). On wide screens the news panel floats over its western side, so the chart
  // opens on the whole port in the space to the right of the panel. Phones open on the
  // western port. Both move to show the day's pins (#85). On a day with nothing
  // on the chart (#81) the panel sits beside or above a short strip instead of over
  // it; panelCover() is then 0, so the strip simply fits the same views.
  var bbox = basemap.bbox; // south, west, north, east
  var sheet = L.latLngBounds([bbox[0], bbox[1]], [bbox[2], bbox[3]]);
  var panel = document.querySelector(".panel");

  // How many pixels of the chart the panel covers on the left (0 when it sits below the chart).
  function panelCover() {
    if (!panel || getComputedStyle(panel).position !== "absolute") return 0;
    return Math.max(0, panel.getBoundingClientRect().right - el.getBoundingClientRect().left);
  }
  function boundsOf(view) {
    return L.latLngBounds([view.south, view.west], [view.north, view.east]);
  }
  // Room kept free around whatever the chart shows: the panel on the left, the
  // ship filter on top, the legend and buttons at the bottom.
  function viewPadding(maxZoom) {
    var options = { paddingTopLeft: [panelCover() + 48, 72], paddingBottomRight: [72, 64] };
    if (maxZoom) options.maxZoom = maxZoom;
    return options;
  }

  var map = L.map(el, {
    zoomControl: false,
    attributionControl: false,
    scrollWheelZoom: false, // the page scrolls past the chart; zoom with buttons, pinch or double-click
    zoomSnap: 0,
    zoomDelta: 0.5,
    maxZoom: 15,
    maxBounds: sheet,
    maxBoundsViscosity: 1,
  });
  map.setMinZoom(map.getBoundsZoom(sheet, true)); // smallest zoom that stays inside the sheet

  // West of the sheet there is only open sea. On wide screens the chart may move past the
  // sheet's western edge by the width of the panel, so a pin at the outer anchorages can sit
  // right of the panel instead of under it (#85). Past that edge the chart is plain water.
  var seaRoom = panelCover() ? ((panelCover() + 48) * 360) / (256 * Math.pow(2, map.getMinZoom())) : 0;
  map.setMaxBounds(L.latLngBounds([bbox[0], bbox[1] - seaRoom], [bbox[2], bbox[3]]));

  // ---------- The home view ----------
  // The normal view of the port, moved (and zoomed out if needed) just enough to show every pin
  // of the day, clear of the panel (#85). If the chart can't zoom out that far (on a phone, an
  // anchorage and the city on the same day), as many pins as fit, most severe item first.
  var NUM_HALF = 18; // half a number square (2.25rem): closer to the edge, the number is cut

  function homeView() {
    var port = boundsOf(el.clientWidth < 640 ? data.view_compact : data.view_home);
    var pins = data.callouts.slice().sort(function (a, b) { return a.rank - b.rank; })
      .map(function (callout) { return L.latLng(callout.lat, callout.lon); });
    // _getBoundsCenterZoom and _limitCenter are Leaflet's own steps of fitBounds (fit, then keep
    // inside maxBounds), internal but stable in the self-hosted 1.9.4. Working out the view
    // first, instead of trying views on the chart, avoids repainting the basemap each time.
    var normal = map._getBoundsCenterZoom(port, panelCover() ? viewPadding() : {});
    var roomy = panelCover() ? viewPadding() : { paddingTopLeft: [NUM_HALF + 6, NUM_HALF + 6], paddingBottomRight: [NUM_HALF + 6, NUM_HALF + 6] };
    var topLeft = L.point(roomy.paddingTopLeft), bottomRight = L.point(roomy.paddingBottomRight);
    for (var count = pins.length; count > 0; count--) {
      var some = L.latLngBounds(pins.slice(0, count));
      var zoom = Math.min(normal.zoom, map.getBoundsZoom(some, false, topLeft.add(bottomRight)));
      var view = moveToShow(normal.center, zoom, some, topLeft, bottomRight);
      if (count === 1 || showsPins(view, pins.slice(0, count))) return view;
    }
    return { center: map._limitCenter(normal.center, normal.zoom, map.options.maxBounds), zoom: normal.zoom };
  }
  // The smallest move of the view that brings the pins inside the padded area.
  function moveToShow(center, zoom, pins, topLeft, bottomRight) {
    var middle = map.project(center, zoom), half = map.getSize().divideBy(2);
    var min = middle.subtract(half).add(topLeft), max = middle.add(half).subtract(bottomRight);
    var sw = map.project(pins.getSouthWest(), zoom), ne = map.project(pins.getNorthEast(), zoom);
    var shift = L.point(
      sw.x < min.x ? sw.x - min.x : ne.x > max.x ? ne.x - max.x : 0,
      ne.y < min.y ? ne.y - min.y : sw.y > max.y ? sw.y - max.y : 0
    );
    return { center: map._limitCenter(map.unproject(middle.add(shift), zoom), zoom, map.options.maxBounds), zoom: zoom };
  }
  // Every pin's number fully on the chart, and right of the panel on wide screens.
  function showsPins(view, pins) {
    var size = map.getSize(), middle = map.project(view.center, view.zoom), left = panelCover() + NUM_HALF;
    return pins.every(function (pin) {
      var p = map.project(pin, view.zoom).subtract(middle).add(size.divideBy(2));
      return p.x >= left && p.x <= size.x - NUM_HALF && p.y >= NUM_HALF && p.y <= size.y - NUM_HALF;
    });
  }
  function goHome(animate) {
    var view = homeView();
    map.setView(view.center, view.zoom, { animate: animate });
  }
  goHome(false);

  // Bottom-right corner, from the bottom up: attribution, scale, zoom, "whole port".
  // (Leaflet stacks each new bottom control above the previous one.)
  var attribution = L.control.attribution({ position: "bottomright", prefix: false }).addTo(map);
  attribution.addAttribution('Map data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors');
  if (data.ships_source) attribution.addAttribution("Ships: " + escapeHtml(data.ships_source));
  L.control.scale({ position: "bottomright", imperial: false, maxWidth: 110 }).addTo(map);
  L.control.zoom({ position: "bottomright" }).addTo(map);

  // Above the zoom buttons: back to the whole port. Wide screens show the words "Whole port"
  // next to the icon (#82); phones show the icon only (style.css), with the same spoken name.
  var HomeControl = L.Control.extend({
    options: { position: "bottomright" },
    onAdd: function () {
      var button = L.DomUtil.create("button", "chart-home");
      button.type = "button";
      button.title = "Whole port";
      button.setAttribute("aria-label", "Show the whole port");
      button.innerHTML =
        '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
        'stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="m21 3-7 7"/><path d="m3 21 7-7"/></svg>' +
        '<span class="chart-home-label">Whole port</span>';
      L.DomEvent.disableClickPropagation(button);
      L.DomEvent.on(button, "click", overview);
      return button;
    },
  });
  new HomeControl().addTo(map);

  // ---------- Basemap ----------
  // Painted by the browser on one canvas, in this order: the water; lines in the
  // water that follow the coast; the land with a soft shadow; then the land detail
  // (roads, railways, breakwaters, storage tanks). The lines in the water are
  // decoration, each one a fixed distance from the shore. They are not depths.

  // Everything is converted once to "world pixels" (Web Mercator at zoom 0, the same
  // numbers as Leaflet's L.CRS.EPSG3857, written out because there are ~200,000 points).
  // At zoom z a world pixel is 2^z screen pixels, so redrawing is only a multiplication.
  function toWorld(lat, lon) {
    var sin = Math.sin((lat * Math.PI) / 180);
    return { x: 256 * (0.5 + lon / 360), y: 256 * (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) };
  }
  function withBox(pts) {
    var shape = { pts: pts, minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
    for (var i = 0; i < pts.length; i += 2) {
      shape.minX = Math.min(shape.minX, pts[i]);
      shape.maxX = Math.max(shape.maxX, pts[i]);
      shape.minY = Math.min(shape.minY, pts[i + 1]);
      shape.maxY = Math.max(shape.maxY, pts[i + 1]);
    }
    return shape;
  }
  function landRing(ring) {
    var pts = new Float64Array(ring.length * 2);
    ring.forEach(function (lonLat, i) {
      var p = toWorld(lonLat[1], lonLat[0]);
      pts[2 * i] = p.x;
      pts[2 * i + 1] = p.y;
    });
    return withBox(pts);
  }
  // Detail lines come as grid steps (see tools/build_basemap.py): add them up to get each point.
  // Every point lies on the 0.0001 degree grid, so the slow part of the conversion (the
  // Mercator formula for latitude) is worked out once per grid row and then looked up.
  var detail = basemap.detail;
  var rowY = new Float64Array(Math.round((bbox[2] - bbox[0]) * detail.grid) + 2);
  for (var row = 0; row < rowY.length; row++) rowY[row] = toWorld(bbox[0] + row / detail.grid, 0).y;
  var columnX0 = toWorld(0, bbox[1]).x, columnStep = 256 / 360 / detail.grid;
  function detailLine(steps) {
    var pts = new Float64Array(steps.length);
    for (var i = 0, x = 0, y = 0; i < steps.length; i += 2) {
      x += steps[i];
      y += steps[i + 1];
      pts[i] = columnX0 + x * columnStep;
      pts[i + 1] = rowY[y];
    }
    return withBox(pts);
  }

  var landRings = [];
  basemap.land.coordinates.forEach(function (polygon) {
    polygon.forEach(function (ring) { landRings.push(landRing(ring)); });
  });
  var lines = {};
  ["minor", "major", "rail", "jetty"].forEach(function (kind) { lines[kind] = detail[kind].map(detailLine); });
  var tanks = [];
  for (var t = 0; t < detail.tanks.length; t += 3) {
    tanks.push({ x: columnX0 + detail.tanks[t] * columnStep, y: rowY[detail.tanks[t + 1]], r: detail.tanks[t + 2] });
  }
  var worldPerMetre = 256 / (2 * Math.PI * 6378137 * Math.cos((sheet.getCenter().lat * Math.PI) / 180));

  // Fine speckle laid over the land, so it reads as a material rather than a flat fill.
  var grain = document.createElement("canvas");
  grain.width = grain.height = 128;
  var grainCtx = grain.getContext("2d");
  var speckle = grainCtx.createImageData(128, 128);
  for (var g = 0; g < speckle.data.length; g += 4) {
    speckle.data[g] = speckle.data[g + 1] = speckle.data[g + 2] = Math.random() < 0.5 ? 0 : 255;
    speckle.data[g + 3] = Math.random() * 22;
  }
  grainCtx.putImageData(speckle, 0, 0);

  var COAST_LINE_GAP = 6; // minimum pixels between two lines in the water
  var COAST_LINE_REACH = 120; // how far from the shore the lines go, in pixels
  var COAST_LINE_WIDTH = 0.8;

  // The lines in the water are the slowest part to draw (two wide strokes each), so
  // they are drawn on their own canvas at one pixel per screen point, even on retina
  // screens, then copied onto the chart. Fine lines on dark water still look sharp,
  // and it is four times less work on a retina screen.
  var waterCanvas = document.createElement("canvas");
  var waterCtx = waterCanvas.getContext("2d", { alpha: false });

  function paint(ctx) {
    var zoom = map.getZoom();
    var s = map.getZoomScale(zoom, 0);
    var origin = map.getPixelOrigin();
    var size = map.getSize();
    var pad = size.multiplyBy(base.options.padding);
    var min = map.containerPointToLayerPoint(pad.multiplyBy(-1));
    var max = map.containerPointToLayerPoint(size.add(pad));
    var perMetre = worldPerMetre * s; // screen pixels per metre

    // Lines every 25, 50, 100, 200... metres: the closest spacing still COAST_LINE_GAP apart.
    // Zooming in by one step halves the spacing, so the lines already drawn stay where they are.
    var step = 25;
    while (step * perMetre < COAST_LINE_GAP) step *= 2;
    var gap = step * perMetre;
    var count = Math.floor(COAST_LINE_REACH / gap);
    var reach = count * gap;

    // Only shapes near the canvas are drawn. Box in world pixels, widened by `margin` screen pixels.
    function near(shape, margin) {
      return shape.maxX * s - origin.x >= min.x - margin && shape.minX * s - origin.x <= max.x + margin &&
        shape.maxY * s - origin.y >= min.y - margin && shape.minY * s - origin.y <= max.y + margin;
    }
    // Outline of a set of shapes, skipping points closer than `tolerance` pixels to the last one.
    function trace(shapes, tolerance, margin, close) {
      var path = new Path2D();
      shapes.forEach(function (shape) {
        if (!near(shape, margin)) return;
        var pts = shape.pts, n = pts.length;
        var lx = pts[0] * s - origin.x, ly = pts[1] * s - origin.y;
        path.moveTo(lx, ly);
        for (var i = 2; i < n; i += 2) {
          var x = pts[i] * s - origin.x, y = pts[i + 1] * s - origin.y;
          if (i < n - 2 && Math.abs(x - lx) + Math.abs(y - ly) < tolerance) continue;
          path.lineTo(x, y);
          lx = x;
          ly = y;
        }
        if (close) path.closePath();
      });
      return path;
    }
    // Lines far from the shore are smooth, so they can use a much simpler coastline.
    var coastPaths = {};
    function coastFor(distance) {
      var tolerance = [10, 5, 2, 0.75].filter(function (tol) { return tol <= Math.max(0.75, distance / 15); })[0];
      return coastPaths[tolerance] || (coastPaths[tolerance] = trace(landRings, tolerance, reach, true));
    }

    var colours = {
      water: token("--water"), waterLine: token("--water-line"), land: token("--land"), coast: token("--coast"),
      road: token("--road"), rail: token("--rail"), tank: token("--tank"), shadow: token("--land-shadow"),
    };

    // Water and its lines, on the low-resolution canvas (same coordinates as the chart).
    var w = Math.ceil(max.x - min.x), h = Math.ceil(max.y - min.y);
    if (waterCanvas.width !== w || waterCanvas.height !== h) {
      waterCanvas.width = w;
      waterCanvas.height = h;
    }
    var wc = waterCtx;
    wc.setTransform(1, 0, 0, 1, -min.x, -min.y);
    wc.lineJoin = "round";
    wc.fillStyle = colours.water;
    wc.fillRect(min.x, min.y, w, h);

    // Each line in the water: a wide stroke of the coastline in the line colour, then
    // a slightly narrower one in the water colour on top. What is left is a thin line
    // at exactly that distance from the nearest shore. Drawn from the outside in.
    for (var i = count; i >= 1; i--) {
      var distance = i * gap, coast = coastFor(distance);
      wc.globalAlpha = 0.06 + 0.5 * Math.pow(1 - (i - 1) / count, 1.8);
      wc.strokeStyle = colours.waterLine;
      wc.lineWidth = 2 * distance + COAST_LINE_WIDTH;
      wc.stroke(coast);
      wc.globalAlpha = 1;
      wc.strokeStyle = colours.water;
      wc.lineWidth = 2 * distance - COAST_LINE_WIDTH;
      wc.stroke(coast);
    }

    ctx.save();
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.drawImage(waterCanvas, min.x, min.y, w, h);

    // Land, lifted off the water by a shadow (a dark copy shifted down, much cheaper
    // than a blurred shadow), with grain and a light coastline.
    var land = coastFor(0);
    ctx.fillStyle = colours.shadow;
    ctx.translate(0, 2.5);
    ctx.fill(land, "evenodd");
    ctx.translate(0, -2.5);
    ctx.fillStyle = colours.land;
    ctx.fill(land, "evenodd");
    ctx.fillStyle = ctx.createPattern(grain, "repeat");
    ctx.fill(land, "evenodd");
    ctx.strokeStyle = colours.coast;
    ctx.lineWidth = 0.8;
    ctx.stroke(land);

    // Roads and railways cut into the land; breakwaters stand out in the water.
    function width(base) {
      return Math.max(0.35, Math.min(base * Math.pow(1.55, zoom - 11), base * 4));
    }
    function strokeLines(kind, colour, lineWidth) {
      ctx.strokeStyle = colour;
      ctx.lineWidth = lineWidth;
      ctx.stroke(trace(lines[kind], 0.75, lineWidth, false));
    }
    strokeLines("minor", colours.road, width(0.7));
    strokeLines("major", colours.road, width(1.4));
    strokeLines("rail", colours.rail, width(0.6));
    strokeLines("jetty", colours.land, width(1.3));

    // Storage tanks at their real size, each with a small shadow, like buildings in relief.
    var discs = new Path2D();
    tanks.forEach(function (tank) {
      var x = tank.x * s - origin.x, y = tank.y * s - origin.y, r = Math.max(0.6, tank.r * perMetre);
      if (x < min.x - r || x > max.x + r || y < min.y - r || y > max.y + r) return;
      discs.moveTo(x + r, y);
      discs.arc(x, y, r, 0, 2 * Math.PI);
    });
    ctx.translate(0.6, 1);
    ctx.fillStyle = colours.road;
    ctx.fill(discs);
    ctx.translate(-0.6, -1);
    ctx.fillStyle = colours.tank;
    ctx.fill(discs);
    ctx.restore();
  }

  // A Leaflet vector layer that paints the whole basemap itself. Leaflet's canvas
  // renderer sizes the canvas, keeps it sharp on retina screens, scales it smoothly
  // while zooming and asks for a repaint when the map stops moving.
  var ChartBase = L.Path.extend({
    options: { interactive: false },
    initialize: function (options) { L.setOptions(this, options); },
    _project: function () {},
    _update: function () {},
    _updatePath: function () { paint(this._renderer._ctx); },
    _containsPoint: function () { return false; },
  });
  map.createPane("basemap").style.zIndex = 250; // under the place names and ships
  var base = L.canvas({ pane: "basemap", padding: 0.1 }); // a small margin, so a short pan shows no gap
  new ChartBase({ renderer: base }).addTo(map);

  // Place names: water in italic, land in spaced capitals (nautical chart convention).
  basemap.labels.forEach(function (label) {
    var angle = label.angle ? ' style="--angle:' + label.angle + 'deg"' : "";
    L.marker([label.lat, label.lon], {
      interactive: false,
      keyboard: false,
      icon: L.divIcon({
        className: "chart-label chart-label-" + label.kind,
        html: "<span" + angle + ">" + escapeHtml(label.text) + "</span>",
        iconSize: [0, 0],
      }),
    }).addTo(map);
  });

  // ---------- Ships ----------
  // Hulls seen from above (shapes from haven/render.py), turned to the heading and
  // drawn at the ship's real length (see .ship svg in style.css). The deck shows the
  // type. Ships under way trail a wake that grows with speed; anchored ships are hollow.
  var shapes = data.ship_shapes;
  function shipIcon(ship) {
    var classes = "ship ship-" + ship.status;
    if (ship.news_severity) classes += " is-linked sev-" + ship.news_severity;
    var wake = "";
    if (ship.status === "underway") {
      var end = (15.5 + Math.min(ship.speed_kn, 20) * 0.6).toFixed(1);
      wake = '<path class="wake" d="M-1.6,12.5L-3.6,' + end + "M1.6,12.5L3.6," + end + '"/>';
    }
    return L.divIcon({
      className: classes,
      iconSize: [0, 0],
      html:
        '<svg viewBox="-6 -12 12 24" style="--heading:' + ship.heading + "deg;--length-m:" + ship.length_m +
        '" aria-hidden="true"><circle class="ring" r="15"/>' + wake +
        '<path class="hull" d="' + shapes.hull + '"/><path class="deck" d="' + shapes.decks[ship.type] + '"/></svg>',
    });
  }

  function shipPopup(ship) {
    var status = ship.status_label + (ship.status === "underway" ? ", " + ship.speed_kn + " kn" : "");
    var destination = ship.destination ? escapeHtml(ship.destination) : "Unknown";
    var raw = ship.destination_raw ? escapeHtml(ship.destination_raw) : "(blank)";
    var html =
      '<p class="pop-name">' + escapeHtml(ship.name) + "</p>" +
      '<p class="pop-type">' + escapeHtml(ship.type_label) + " · " + ship.length_m + " m · " + escapeHtml(ship.flag_name) + "</p>" +
      '<dl class="pop-facts">' +
      "<div><dt>Status</dt><dd>" + escapeHtml(status) + "</dd></div>" +
      "<div><dt>Area</dt><dd>" + escapeHtml(ship.area) + "</dd></div>" +
      "<div><dt>Destination</dt><dd>" + destination + ' <span class="ais-text">AIS: ' + raw + "</span></dd></div>" +
      "</dl>";
    if (ship.news_item) {
      html += '<button type="button" class="pop-news sev-' + ship.news_severity + '" data-action="show-item" data-rank="' +
        ship.news_item + '">At the terminal in item ' + ship.news_item + "</button>";
    }
    return html;
  }

  var shipLayer = L.layerGroup().addTo(map);
  var ships = (data.ships || []).map(function (ship) {
    var marker = L.marker([ship.lat, ship.lon], {
      icon: shipIcon(ship),
      title: ship.name + ", " + ship.type_label + ", " + ship.status_label,
      riseOnHover: true,
    }).bindPopup(shipPopup(ship), { className: "chart-popup", maxWidth: 280, offset: [0, -6] });
    marker.addTo(shipLayer);
    return { ship: ship, marker: marker };
  });

  // ---------- Numbered items ----------
  // Each item with a place shows its number on the chart, with the place's name beside it.
  // Items whose markers would overlap at the current zoom share one marker: their numbers side
  // by side on the first item's place, then their places ("2 4 Europoort · Calandkanaal"). It
  // splits again when zooming in makes room (#85). A shared marker too wide for the chart lists
  // its items in rows instead. Every number is its own button, so each item in a shared marker
  // can still be picked, also by keyboard.
  var callouts = {};
  data.callouts.forEach(function (callout) { callouts[callout.rank] = { data: callout }; });
  var ranks = Object.keys(callouts).map(Number).sort(function (a, b) { return a - b; });
  var calloutLayer = L.layerGroup().addTo(map);
  var MARKER_GAP = 4; // pixels kept free between two markers, and between a marker and the chart's edge
  var pinGeometry = window.HavenPins; // the geometry: static/pins.js
  var activeRank = null, hoverRank = null; // kept here, because markers are rebuilt when they merge or split

  // A group's items in marker order: by rank, but items at the same place side by side
  // (they share one label). The first is the anchor: the marker sits on its place.
  function inPlaceOrder(list) {
    var sorted = list.slice().sort(function (a, b) { return a - b; }), order = [];
    sorted.forEach(function (rank) {
      if (order.indexOf(rank) >= 0) return;
      sorted.forEach(function (other) {
        if (callouts[other].data.label === callouts[rank].data.label) order.push(other);
      });
    });
    return order;
  }

  function listWords(words) {
    return words.length < 2 ? words.join("") : words.slice(0, -1).join(", ") + " and " + words[words.length - 1];
  }

  function itemButton(rank, withLabel) {
    var item = callouts[rank].data, name = "Item " + rank + ", " + item.label + ": " + item.title;
    return '<button type="button" class="callout-item sev-' + item.severity + '" data-action="show-item" data-rank="' +
      rank + '" title="' + escapeHtml(name) + '" aria-label="' + escapeHtml(name) + '"><span class="num num-' +
      item.severity + '">' + rank + "</span>" + (withLabel ? labelHtml([item.label]) : "") + "</button>";
  }
  function labelHtml(places) {
    return '<span class="callout-label">' + escapeHtml(places.join(" · ")) + "</span>";
  }
  function placesOf(group) {
    return group.map(function (rank) { return callouts[rank].data.label; })
      .filter(function (label, i, all) { return all.indexOf(label) === i; });
  }

  // One item: its number and label, as one button. Shared, on one line: the numbers, then the
  // places. Shared, in rows: one row per place, its number(s) then its label.
  function markerHtml(group, rows) {
    var html;
    if (group.length === 1) {
      html = itemButton(group[0], true);
    } else if (!rows) {
      html = '<span class="callout-nums">' + group.map(function (rank) { return itemButton(rank, false); }).join("") +
        "</span>" + labelHtml(placesOf(group));
    } else {
      html = placesOf(group).map(function (place) {
        var here = group.filter(function (rank) { return callouts[rank].data.label === place; });
        if (here.length === 1) return itemButton(here[0], true);
        return '<span class="callout-place">' + here.map(function (rank) { return itemButton(rank, false); }).join("") +
          labelHtml([place]) + "</span>";
      }).join("");
    }
    var shared = group.length > 1
      ? ' role="group" aria-label="' + escapeHtml("Items " + listWords(group.map(String)) + " share this marker: " +
        placesOf(group).join(", ")) + '" style="--nums:' + group.length + '"'
      : "";
    return '<span class="callout-inner"' + shared + ">" + html + "</span>";
  }

  function markerClass(marker) {
    var shared = marker.ranks.length > 1 ? (marker.rows ? " callout-rows" : " callout-merged") : "";
    return "callout" + (marker.side === "left" ? " callout-left" : "") + shared;
  }

  // Marker sizes, measured once in a hidden copy (they depend on the text and on one line or
  // rows, not on the side). The fonts change them, so they are measured again once loaded.
  // `lead` is the width of the numbers at the front; `half` is half a number square.
  var ruler = L.DomUtil.create("div", "callout-ruler", map.getPane("markerPane"));
  ruler.setAttribute("aria-hidden", "true");
  ruler.style.cssText = "position:absolute;left:0;top:0;visibility:hidden";
  var sizes = {};
  function sizeOf(group, rows) {
    var key = group.join(",") + (rows ? " rows" : "");
    if (!sizes[key]) {
      ruler.className = "callout-ruler" + (rows && group.length > 1 ? " callout-rows" : "");
      ruler.innerHTML = markerHtml(group, rows);
      var box = ruler.firstChild.getBoundingClientRect(), num = ruler.querySelector(".num").getBoundingClientRect();
      var nums = ruler.querySelector(".callout-nums");
      sizes[key] = { w: box.width, h: box.height, half: num.width / 2, lead: nums ? nums.getBoundingClientRect().width : num.width };
      ruler.innerHTML = "";
    }
    return sizes[key];
  }


  // Each marker on the side its place prefers (`side` in config/places.toml), on one line.
  // If it would run off the chart or under the panel: the other side; then, for a shared
  // marker, rows on either side; if nothing fits, the narrowest of these. Last, a marker at
  // the chart's edge moves inward just enough that no number is cut (owner, PR #91).
  function placeMarker(marker) {
    var anchor = callouts[marker.ranks[0]].data;
    var point = map.latLngToContainerPoint([anchor.lat, anchor.lon]);
    var size = map.getSize(), chart = { left: panelCover(), top: 0, right: size.x, bottom: size.y };
    var left = chart.left + MARKER_GAP, right = chart.right - MARKER_GAP;
    var preferred = anchor.side === "left" ? "left" : "right", other = preferred === "left" ? "right" : "left";
    var layouts = [[preferred, false], [other, false]];
    if (marker.ranks.length > 1) layouts.push([preferred, true], [other, true]);
    var best = null;
    layouts.forEach(function (layout) {
      var box = pinGeometry.boxAt(point, sizeOf(marker.ranks, layout[1]), layout[0], layout[1]);
      var fits = box.left >= left && box.right <= right;
      if (!best || (fits && !best.fits) || (!best.fits && box.right - box.left < best.box.right - best.box.left)) {
        best = { side: layout[0], rows: layout[1], box: box, fits: fits };
      }
    });
    var nudge = pinGeometry.nudgeInside(best.box, point, chart, MARKER_GAP);
    marker.side = best.side;
    marker.rows = best.rows;
    marker.nudge = { x: Math.round(nudge.x), y: Math.round(nudge.y) };
    marker.box = {
      left: best.box.left + marker.nudge.x, right: best.box.right + marker.nudge.x,
      top: best.box.top + marker.nudge.y, bottom: best.box.bottom + marker.nudge.y,
    };
    return marker;
  }

  // Start with one marker per item; while two overlap, merge them, and check again.
  function planMarkers() {
    var markers = ranks.map(function (rank) { return placeMarker({ ranks: [rank] }); });
    for (;;) {
      var pair = null;
      for (var i = 0; i < markers.length && !pair; i++) {
        for (var j = i + 1; j < markers.length && !pair; j++) {
          if (pinGeometry.overlaps(markers[i].box, markers[j].box, MARKER_GAP)) pair = [markers[i], markers[j]];
        }
      }
      if (!pair) return markers;
      markers = markers.filter(function (m) { return m !== pair[0] && m !== pair[1]; });
      markers.push(placeMarker({ ranks: inPlaceOrder(pair[0].ranks.concat(pair[1].ranks)) }));
    }
  }

  var shownPlan = null;
  function showCallouts(remeasure) {
    if (!ranks.length) return;
    if (remeasure) sizes = {};
    var plan = planMarkers().sort(function (a, b) { return a.ranks[0] - b.ranks[0]; }); // keyboard order: item 1 first
    var key = plan.map(function (m) {
      return m.ranks.join(",") + m.side + (m.rows ? " rows" : "") + " " + m.nudge.x + "," + m.nudge.y;
    }).sort().join("|");
    if (key === shownPlan) return;
    shownPlan = key;
    // A rebuilt marker is a new element: keep the keyboard focus on the same item.
    var focused = document.activeElement && document.activeElement.closest && document.activeElement.closest(".callout-item");
    var focusedRank = focused && el.contains(focused) ? focused.getAttribute("data-rank") : null;
    calloutLayer.clearLayers();
    plan.forEach(function (planned) {
      var anchor = callouts[planned.ranks[0]].data;
      var marker = L.marker([anchor.lat, anchor.lon], {
        interactive: false, // the buttons inside take the clicks (see the document click handler)
        keyboard: false,
        zIndexOffset: 1000,
        icon: L.divIcon({
          className: markerClass(planned),
          iconSize: [0, 0],
          iconAnchor: [-planned.nudge.x, -planned.nudge.y], // Leaflet shifts the icon by minus the anchor
          html: markerHtml(planned.ranks, planned.rows),
        }),
      }).addTo(calloutLayer);
      L.DomEvent.disableClickPropagation(marker.getElement()); // no map drag or zoom from a number
    });
    markCallouts();
    if (focusedRank) {
      var again = calloutButton(focusedRank);
      if (again) again.focus({ preventScroll: true });
    }
  }

  function calloutButton(rank) {
    return el.querySelector('.callout-item[data-rank="' + rank + '"]');
  }

  // The selected and the hovered item stand out; in a shared marker, only that item.
  function markCallouts() {
    var buttons = el.querySelectorAll(".callout-item");
    for (var i = 0; i < buttons.length; i++) {
      var rank = Number(buttons[i].getAttribute("data-rank"));
      buttons[i].classList.toggle("is-active", rank === activeRank);
      buttons[i].classList.toggle("is-hover", rank === hoverRank);
    }
    var markers = el.querySelectorAll(".leaflet-marker-pane .callout");
    for (var j = 0; j < markers.length; j++) {
      markers[j].classList.toggle("is-active", !!markers[j].querySelector(".callout-item.is-active"));
    }
  }

  showCallouts(false);
  map.on("moveend", function () { showCallouts(false); });
  if (document.fonts) {
    document.fonts.addEventListener("loadingdone", function () { showCallouts(true); });
    document.fonts.ready.then(function () { showCallouts(true); });
  }

  // ---------- Focus: items, groups of ships, one ship ----------
  function markerEl(marker) {
    return marker.getElement() || document.createElement("span");
  }

  function clearFocus() {
    el.classList.remove("is-focused");
    ships.forEach(function (s) { markerEl(s.marker).classList.remove("is-hot"); });
    activeRank = null;
    markCallouts();
    var active = document.querySelectorAll(".item.is-active, .panel-item.is-active");
    for (var i = 0; i < active.length; i++) active[i].classList.remove("is-active");
    var pressed = document.querySelectorAll('[data-action="show-item"][aria-pressed="true"]');
    for (var j = 0; j < pressed.length; j++) pressed[j].setAttribute("aria-pressed", "false");
  }

  function showFocus(html, spoken) {
    focusText.innerHTML = html;
    focusBox.hidden = false;
    announcer.textContent = spoken;
  }

  function hideFocus() {
    focusBox.hidden = true;
    announcer.textContent = "";
  }

  function flyTo(points, maxZoom) {
    var bounds = L.latLngBounds(points);
    var options = viewPadding(maxZoom);
    if (reduceMotion) map.fitBounds(bounds, options);
    else map.flyToBounds(bounds, L.extend({ duration: 0.9 }, options));
  }

  // Selecting from the full brief below: bring the chart back into view before it moves.
  function revealChart() {
    var box = chart.getBoundingClientRect();
    var visible = Math.min(box.bottom, window.innerHeight) - Math.max(box.top, 0);
    if (visible < box.height * 0.6) {
      chart.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
    }
  }

  function setHash(hash) {
    try {
      history.replaceState(null, "", hash ? "#" + hash : location.pathname + location.search);
    } catch (e) {
      // Some embedded viewers do not allow it; the chart still works.
    }
  }

  function selectItem(rank, options) {
    options = options || {};
    var item = document.getElementById("item-" + rank);
    var entry = panel && panel.querySelector('.panel-item[data-rank="' + rank + '"]');
    var callout = callouts[rank];
    clearFocus();
    if (item) {
      item.classList.add("is-active");
      var button = item.querySelector('[data-action="show-item"]');
      if (button) button.setAttribute("aria-pressed", "true");
    }
    if (entry) entry.classList.add("is-active");
    // No place on the chart: the item opens in the panel like any other (#82), the chart
    // stays where it is, and the focus box of an earlier item is taken away.
    if (!callout) {
      hideFocus();
      announcer.textContent = "Item " + rank + " has no place on the chart.";
      setHash("item-" + rank);
      return;
    }

    el.classList.add("is-focused");
    activeRank = rank;
    markCallouts();
    var points = [[callout.data.lat, callout.data.lon]];
    var linked = ships.filter(function (s) { return s.ship.news_item === rank; });
    linked.forEach(function (s) {
      points.push([s.ship.lat, s.ship.lon]);
      markerEl(s.marker).classList.add("is-hot");
    });
    var detail = linked.length ? " · " + linked.length + " ships at this terminal" : "";
    showFocus(
      '<span class="num num-' + callout.data.severity + '">' + rank + "</span>" +
        "<span><strong>" + escapeHtml(callout.data.label.replace(/\s*→$/, "")) + "</strong>" + detail + "</span>",
      "Chart shows item " + rank + ": " + callout.data.title + detail
    );
    // Clicked on the chart: show the item next to it, in the panel when it floats over
    // the chart, otherwise in the full brief below.
    if (options.fromChart && entry && panelCover()) {
      entry.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "nearest" });
    } else if (options.fromChart && item) {
      item.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "center" });
    } else if (!options.quiet) {
      revealChart();
    }
    flyTo(points, linked.length ? 13.6 : 11.8);
    setHash("item-" + rank);
  }

  function showShips(status) {
    var group = ships.filter(function (s) { return s.ship.status === status; });
    if (!group.length) return;
    clearFocus();
    el.classList.add("is-focused");
    group.forEach(function (s) { markerEl(s.marker).classList.add("is-hot"); });
    var words = { anchored: "at anchor", underway: "under way" }[status];
    showFocus("<span><strong>" + group.length + " ships " + words + "</strong></span>", group.length + " ships " + words);
    revealChart();
    flyTo(group.map(function (s) { return [s.ship.lat, s.ship.lon]; }), 12.5);
    setHash("");
  }

  function showShip(name) {
    var found = ships.filter(function (s) { return s.ship.name === name; })[0];
    if (!found) return;
    clearFocus();
    hideFocus();
    if (!shipLayer.hasLayer(found.marker)) found.marker.addTo(shipLayer); // even if filtered out
    revealChart();
    map.setView([found.ship.lat, found.ship.lon], 13.5, { animate: !reduceMotion });
    found.marker.openPopup();
    setHash("");
  }

  function overview() {
    clearFocus();
    hideFocus();
    map.closePopup();
    goHome(!reduceMotion);
    setHash("");
  }

  // ---------- Ship filter ----------
  function filterShips(kind) {
    ships.forEach(function (s) {
      var show = kind === "all" || s.ship.type === kind;
      if (show && !shipLayer.hasLayer(s.marker)) s.marker.addTo(shipLayer);
      if (!show && shipLayer.hasLayer(s.marker)) shipLayer.removeLayer(s.marker);
    });
    var buttons = document.querySelectorAll("[data-ship-filter]");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].setAttribute("aria-pressed", String(buttons[i].getAttribute("data-ship-filter") === kind));
    }
  }

  // ---------- Wiring ----------
  document.addEventListener("click", function (event) {
    var target = event.target.closest("[data-action], [data-ship-filter]");
    if (target) {
      var action = target.getAttribute("data-action");
      // Panel entries are links to the full item, so they still work without the chart.
      if (target.tagName === "A") event.preventDefault();
      if (target.hasAttribute("data-ship-filter")) filterShips(target.getAttribute("data-ship-filter"));
      else if (action === "show-item") selectItem(Number(target.getAttribute("data-rank")), { fromChart: el.contains(target) });
      else if (action === "show-ships") showShips(target.getAttribute("data-status"));
      else if (action === "show-ship") showShip(target.getAttribute("data-ship"));
      else if (action === "overview") overview();
      return;
    }
    // A click anywhere on an item card (not on a link) also shows it on the chart.
    var card = event.target.closest(".item[data-place]");
    if (card && !event.target.closest("a, button")) selectItem(Number(card.getAttribute("data-rank")));
  });

  // Hovering an item, in the panel or in the full brief, lights up its number on the chart.
  var CARD = ".item[data-place], .panel-item[data-action]";
  var lists = document.querySelectorAll(".items, .panel-items");
  for (var l = 0; l < lists.length; l++) {
    lists[l].addEventListener("mouseover", function (event) {
      var card = event.target.closest(CARD);
      var rank = card && Number(card.getAttribute("data-rank"));
      if (rank && callouts[rank]) {
        hoverRank = rank;
        markCallouts();
      }
    });
    lists[l].addEventListener("mouseout", function (event) {
      var card = event.target.closest(CARD);
      if (card && hoverRank !== null && !card.contains(event.relatedTarget)) {
        hoverRank = null;
        markCallouts();
      }
    });
  }

  // Ships are drawn to scale: tell the stylesheet how many pixels a metre is at this zoom.
  // Zoomed far out, a smaller minimum size keeps the anchorage from turning into a blob.
  function updateScale() {
    var zoom = map.getZoom();
    el.setAttribute("data-zoom", zoom < 10.5 ? "far" : "near");
    el.style.setProperty("--px-per-m", (worldPerMetre * map.getZoomScale(zoom, 0)).toFixed(4) + "px");
  }
  map.on("zoomend", updateScale);
  updateScale();

  // A link to #item-2 opens with the chart already on item 2.
  var linked = /^#item-(\d+)$/.exec(location.hash);
  if (linked) selectItem(Number(linked[1]), { quiet: true });
})();

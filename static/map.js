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
  var pinGeometry = window.HavenPins; // marker geometry: static/pins.js (the home view uses it too)
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var chart = document.getElementById("chart");
  var focusBox = document.getElementById("chart-focus");
  var focusText = document.getElementById("chart-focus-text");
  var announcer = document.getElementById("chart-announcer");
  // This file's folder: the worker for the water lines (water.js) sits next to it (#111).
  var folder = document.currentScript ? document.currentScript.src.replace(/[^/]*$/, "") : "static/";

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
    // Only Ctrl + wheel and a touchpad pinch reach Leaflet's wheel zoom; a plain wheel scrolls
    // the page (the gate under "Wheel and touchpad", #111).
    scrollWheelZoom: true,
    zoomSnap: 0, // flying to an item lands exactly
    zoomDelta: 1, // buttons, double-click and keys: one level a step (#111; was 0.5)
    maxZoom: 15,
    maxBounds: sheet,
    // The edges give a little while dragging and spring back on release, so the chart shows it
    // is at an edge instead of seeming stuck (#111; was 1, a hard stop).
    maxBoundsViscosity: 0.8,
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
  var NUM_HALF = 18; // half a number square (2.25rem): room kept around the pins when the view can move

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
  // Every pin on the chart, right of the panel on wide screens. A pin close to the edge counts:
  // its marker is nudged inward so the whole number shows (pins.js; owner, PR #91).
  function showsPins(view, pins) {
    var size = map.getSize(), middle = map.project(view.center, view.zoom);
    var chart = { left: panelCover(), top: 0, right: size.x, bottom: size.y };
    return pins.every(function (pin) {
      return pinGeometry.onChart(map.project(pin, view.zoom).subtract(middle).add(size.divideBy(2)), chart);
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
  // updateWhenIdle: the scale bar changes when a move ends, not on every frame of a drag (#104).
  L.control.scale({ position: "bottomright", imperial: false, maxWidth: 110, updateWhenIdle: true }).addTo(map);
  L.control.zoom({ position: "bottomright" }).addTo(map);

  // Above the zoom buttons: back to the whole port. Wide screens show the words "Whole port"
  // next to the icon (#82); phones show the icon only (style.css), with the same spoken name.
  var HomeControl = L.Control.extend({
    options: { position: "bottomright" },
    onAdd: function () {
      var button = L.DomUtil.create("button", "btn chart-home");
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
  // The shapes come as text (see tools/build_basemap.py): every point lies on a grid of
  // 0.0001 degrees and is written as the step from the point before, each step in 5-bit
  // groups as letters (the "encoded polyline" scheme of web maps). A shape's first point is
  // the step from the first point of the shape before it. About three times smaller than
  // plain numbers (#104). Because every point is on the grid, the slow part of the conversion
  // (the Mercator formula for latitude) is worked out once per grid row and then looked up.
  function numbers(text) {
    var out = [], value = 0, shift = 0;
    for (var i = 0; i < text.length; i++) {
      var c = text.charCodeAt(i) - 63;
      value |= (c & 0x1f) << shift;
      if (c & 0x20) {
        shift += 5;
        continue;
      }
      out.push(value & 1 ? ~(value >> 1) : value >> 1);
      value = 0;
      shift = 0;
    }
    return out;
  }
  var grid = basemap.grid;
  var rowY = new Float64Array(Math.round((bbox[2] - bbox[0]) * grid) + 2);
  for (var row = 0; row < rowY.length; row++) rowY[row] = toWorld(bbox[0] + row / grid, 0).y;
  var columnX0 = toWorld(0, bbox[1]).x, columnStep = 256 / 360 / grid;
  function shapes(texts) {
    var startX = 0, startY = 0;
    return texts.map(function (text) {
      var steps = numbers(text), pts = new Float64Array(steps.length);
      for (var i = 0, x = startX, y = startY; i < steps.length; i += 2) {
        x += steps[i];
        y += steps[i + 1];
        if (i === 0) {
          startX = x;
          startY = y;
        }
        pts[i] = columnX0 + x * columnStep;
        pts[i + 1] = rowY[y];
      }
      return withBox(pts);
    });
  }

  var landRings = shapes(basemap.land); // outer edges and holes alike: filled "evenodd"
  var lines = {};
  ["minor", "major", "rail", "jetty"].forEach(function (kind) { lines[kind] = shapes(basemap.detail[kind]); });
  var tanks = [];
  var tankNumbers = numbers(basemap.detail.tanks); // per tank: step from the tank before, radius in metres
  for (var t = 0, tx = 0, ty = 0; t < tankNumbers.length; t += 3) {
    tx += tankNumbers[t];
    ty += tankNumbers[t + 1];
    tanks.push({ x: columnX0 + tx * columnStep, y: rowY[ty], r: tankNumbers[t + 2] });
  }
  var worldPerMetre = 256 / (2 * Math.PI * 6378137 * Math.cos((sheet.getCenter().lat * Math.PI) / 180));

  var WATER_MARGIN = 0.25; // worked out for the view plus this much of its size on each side

  // ---------- The water and its lines ----------
  // Each line follows the shore at a fixed distance, from a map of distances to the land
  // (static/water.js). That takes a second or more for a laptop-sized chart, so a background
  // worker does it (#111): it gets the land once, then one picture per zoom level for the view
  // plus a margin, reused while the chart is moved. If the worker can't start (or fails), the
  // chart shows plain water: the lines are decoration.
  // The picture is a layer of its own, under the basemap's canvas: a <canvas> handed the finished
  // picture (no drawing on the page's thread), placed and scaled with a CSS transform. Until a new
  // picture arrives the previous one is shown scaled, and when it arrives nothing else is
  // repainted: repainting the whole basemap for it froze the page on a computer without a
  // graphics chip (measured, #111).
  var water = null; // the picture shown: { zoom, x, y, w, h (world pixels at that zoom) }
  var waterJob = null; // the picture being worked out
  map.createPane("water").style.zIndex = 240; // just under the basemap (250)
  var waterEl = L.DomUtil.create("canvas", "chart-water leaflet-zoom-animated", map.getPane("water"));
  var waterShow = null; // hands a picture to waterEl: "bitmaprenderer", or 2D where there is none
  var waterWorker = null;
  try {
    waterWorker = new Worker(folder + "water.js");
    waterWorker.onmessage = takeWater;
    waterWorker.onerror = function () { waterWorker = null; waterJob = null; };
    waterWorker.postMessage({ land: landRings });
  } catch (e) {
    waterWorker = null; // the chart works without the lines
  }

  // A colour token as red, green, blue (0-255), through the canvas's own colour parser.
  var colourCtx = document.createElement("canvas").getContext("2d");
  function rgb(colour) {
    colourCtx.fillStyle = "#000";
    colourCtx.fillStyle = colour;
    var hex = /^#([0-9a-f]{6})$/i.exec(colourCtx.fillStyle);
    if (hex) return [0, 2, 4].map(function (i) { return parseInt(hex[1].substr(i, 2), 16); });
    return colourCtx.fillStyle.match(/[\d.]+/g).slice(0, 3).map(Number);
  }

  // Ask the worker for the picture of this view (world pixels at this zoom) plus the margin.
  // One picture at a time: when it arrives the chart is painted again, and asks again then if
  // it has moved on meanwhile.
  function wantWater(zoom, s, view, colours) {
    if (!waterWorker || waterJob) return;
    var mx = Math.ceil((view.maxX - view.minX) * WATER_MARGIN), my = Math.ceil((view.maxY - view.minY) * WATER_MARGIN);
    var x0 = Math.floor(view.minX) - mx, y0 = Math.floor(view.minY) - my;
    waterJob = { zoom: zoom, s: s, x: x0, y: y0, w: Math.ceil(view.maxX) + mx - x0, h: Math.ceil(view.maxY) + my - y0,
      worldPerMetre: worldPerMetre, sea: rgb(colours.water), line: rgb(colours.waterLine) };
    waterWorker.postMessage(waterJob);
  }

  // A picture from the worker: handed to the water layer as it is (an ImageBitmap, made off the
  // page's thread), or copied in where the browser has no "bitmaprenderer". Then placed, and asked
  // for again if the chart has moved on meanwhile.
  function takeWater(event) {
    var done = event.data, image = new ImageData(done.pixels, done.w, done.h);
    function show(picture) {
      waterEl.width = done.w;
      waterEl.height = done.h;
      waterEl.style.width = done.w + "px";
      waterEl.style.height = done.h + "px";
      if (picture) waterShow.transferFromImageBitmap(picture);
      else waterShow.putImageData(image, 0, 0);
      water = { zoom: done.zoom, x: done.x, y: done.y, w: done.w, h: done.h };
      waterJob = null;
      placeWater(map.getZoom(), map.getPixelOrigin());
      checkWater();
    }
    if (!waterShow) waterShow = (window.createImageBitmap && waterEl.getContext("bitmaprenderer")) || waterEl.getContext("2d");
    if (waterShow.transferFromImageBitmap) createImageBitmap(image).then(show, function () { waterJob = null; });
    else show(null);
  }

  // The picture on the chart at `zoom`, for a view whose top left is `origin` (world pixels at that
  // zoom: Leaflet's pixel origin). Moved and scaled by the browser, like Leaflet's own layers.
  function placeWater(zoom, origin) {
    if (!water) return;
    var k = map.getZoomScale(zoom, water.zoom);
    L.DomUtil.setTransform(waterEl, L.point(water.x * k - origin.x, water.y * k - origin.y), k);
  }
  // A zoom by button, double-click or wheel is animated: the picture moves and scales with the
  // chart, towards the view Leaflet is zooming to (worked out as Leaflet does, from public parts).
  map.on("zoomanim", function (event) {
    var pane = L.DomUtil.getPosition(map.getPane("mapPane")) || L.point(0, 0);
    placeWater(event.zoom, map.project(event.center, event.zoom).subtract(map.getSize().divideBy(2)).add(pane).round());
  });
  // Flying and pinching move the view frame by frame; a reset at once.
  map.on("zoom viewreset zoomend", function () { placeWater(map.getZoom(), map.getPixelOrigin()); });

  // The view in world pixels at the current zoom, with the basemap canvas's margin.
  function viewBox() {
    var origin = map.getPixelOrigin(), size = map.getSize(), pad = size.multiplyBy(base.options.padding);
    var min = map.containerPointToLayerPoint(pad.multiplyBy(-1)), max = map.containerPointToLayerPoint(size.add(pad));
    return { minX: min.x + origin.x, minY: min.y + origin.y, maxX: max.x + origin.x, maxY: max.y + origin.y };
  }
  // A new picture is asked for only for a new zoom, or when the view has left the picture.
  function checkWater() {
    var zoom = map.getZoom(), view = viewBox();
    var inside = water && water.zoom === zoom && view.minX >= water.x && view.minY >= water.y &&
      view.maxX <= water.x + water.w && view.maxY <= water.y + water.h;
    if (!inside) wantWater(zoom, map.getZoomScale(zoom, 0), view, chartColours());
  }

  // Outline of a set of shapes at scale s: only shapes that reach into `box` (world pixels at
  // that zoom), skipping points closer than `tolerance` pixels to the last one drawn. Drawn
  // shifted by `shift`, so the canvas gets small numbers: it stores paths with about seven
  // digits, and world pixels run into the millions at the closest zoom.
  function outline(shapes, s, box, tolerance, close, shift) {
    var path = new Path2D();
    shapes.forEach(function (shape) {
      if (shape.maxX * s < box.minX || shape.minX * s > box.maxX || shape.maxY * s < box.minY || shape.minY * s > box.maxY) return;
      var pts = shape.pts, n = pts.length;
      var lx = pts[0] * s - shift.x, ly = pts[1] * s - shift.y;
      path.moveTo(lx, ly);
      for (var i = 2; i < n; i += 2) {
        var px = pts[i] * s - shift.x, py = pts[i + 1] * s - shift.y;
        if (i < n - 2 && Math.abs(px - lx) + Math.abs(py - ly) < tolerance) continue;
        path.lineTo(px, py);
        lx = px;
        ly = py;
      }
      if (close) path.closePath();
    });
    return path;
  }

  // The colours, read from the stylesheet once (the site has one colour scheme). Reading them on
  // every repaint made the browser check the page's styles each time (#104).
  var colourCache = null;
  function chartColours() {
    return colourCache || (colourCache = {
      water: token("--water"), waterLine: token("--water-line"), land: token("--land"), coast: token("--coast"),
      road: token("--road"), rail: token("--rail"), tank: token("--tank"), shadow: token("--land-shadow"),
    });
  }

  function paint(ctx) {
    var zoom = map.getZoom();
    var s = map.getZoomScale(zoom, 0);
    var origin = map.getPixelOrigin();
    var size = map.getSize();
    var pad = size.multiplyBy(base.options.padding);
    var min = map.containerPointToLayerPoint(pad.multiplyBy(-1));
    var max = map.containerPointToLayerPoint(size.add(pad));
    var perMetre = worldPerMetre * s; // screen pixels per metre
    var colours = chartColours();
    // The canvas in world pixels at this zoom (= the chart's coordinates plus the pixel origin).
    var view = { minX: min.x + origin.x, minY: min.y + origin.y, maxX: max.x + origin.x, maxY: max.y + origin.y };

    // The water and its lines are a layer of their own, under this canvas ("The water and its
    // lines", above); this canvas draws the land on a clear background.
    checkWater();

    ctx.save();
    ctx.lineJoin = "round";
    ctx.lineCap = "round";

    // Land, lifted off the water by a shadow (a dark copy shifted down, much cheaper
    // than a blurred shadow), and a fine coastline. Flat, like a drawn chart: the random grain
    // that used to lie over the land looked like a photo (#102).
    var near = { minX: view.minX - 3, minY: view.minY - 3, maxX: view.maxX + 3, maxY: view.maxY + 3 };
    var land = outline(landRings, s, near, 0.75, true, origin);
    ctx.fillStyle = colours.shadow;
    ctx.translate(0, 2.5);
    ctx.fill(land, "evenodd");
    ctx.translate(0, -2.5);
    ctx.fillStyle = colours.land;
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
      ctx.stroke(outline(lines[kind], s, near, 0.75, false, origin));
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
      html += '<button type="button" class="btn pop-news sev-' + ship.news_severity + '" data-action="show-item" data-rank="' +
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
      // A drag that starts on a marker moves the chart, like anywhere else on it (#111); only a
      // double-click on a number is kept from zooming the chart. A click still picks the item.
      L.DomEvent.on(marker.getElement(), "dblclick", L.DomEvent.stopPropagation);
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
  // Measured once more when the fonts the markers use have arrived, not after every font (#104).
  if (document.fonts) document.fonts.ready.then(function () { showCallouts(true); });

  // The High marker pings three times (style.css); after that, rebuilt markers stay still.
  setTimeout(function () { el.classList.add("ping-done"); }, 3 * 2600);

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

  // ---------- Wheel and touchpad ----------
  // Ctrl + wheel, and a touchpad pinch (which the browser sends as Ctrl + wheel), zoom the chart
  // around the cursor through Leaflet's own wheel zoom, which also keeps the browser from
  // zooming the whole page. A plain wheel or two-finger scroll scrolls the page, as anywhere
  // else, and shows a short hint (#111). The gate sits on the chart's frame and runs first
  // (capture), so Leaflet never sees a plain wheel; it never cancels one.
  var hint = document.getElementById("chart-hint"), hintTimer = 0;
  var zoomKey = /Mac|iPhone|iPad/.test(navigator.platform || "") ? "⌘" : "Ctrl";
  var keyNames = document.querySelectorAll("[data-zoom-key]");
  for (var n = 0; n < keyNames.length; n++) keyNames[n].textContent = zoomKey;

  function showHint() {
    if (!hint) return;
    hint.classList.add("is-shown");
    clearTimeout(hintTimer);
    hintTimer = setTimeout(function () { hint.classList.remove("is-shown"); }, 1500);
  }
  el.parentNode.addEventListener("wheel", function (event) {
    if (event.ctrlKey || event.metaKey) return; // Leaflet zooms
    if (!el.contains(event.target)) return; // the ship filter and the focus box keep their own
    event.stopPropagation();
    if (event.deltaY) showHint();
  }, { capture: true, passive: true });

  // ---------- One finger on the chart ----------
  // One finger moves the chart (P1, #111). But a mostly vertical swipe scrolls the page whenever
  // the chart can't move that way (at its smallest zoom on a phone it can't move north or south
  // at all), so the page never gets stuck on the chart. Who takes a swipe is decided once it has
  // moved SWIPE_DECIDE pixels (pins.js swipeTaker); until then Leaflet doesn't see the moves.
  // A swipe that goes to the page never reaches Leaflet; a second finger leaves it to the pinch.
  var SWIPE_DECIDE = 8;
  var swipe = null, glide = 0;

  // How far the chart can still move to show more of the north and of the south, in pixels.
  function chartRoom() {
    var bounds = map.options.maxBounds, size = map.getSize();
    return {
      north: -map.latLngToContainerPoint([bounds.getNorth(), bounds.getWest()]).y,
      south: map.latLngToContainerPoint([bounds.getSouth(), bounds.getWest()]).y - size.y,
    };
  }
  el.addEventListener("touchstart", function (event) {
    cancelAnimationFrame(glide);
    swipe = null;
    if (event.touches.length !== 1 || event.target.closest(".leaflet-control, .leaflet-popup")) return;
    var touch = event.touches[0];
    swipe = { x: touch.clientX, y: touch.clientY, lastY: touch.clientY, lastT: event.timeStamp, speed: 0, taker: null, room: chartRoom() };
  }, { capture: true, passive: true });
  window.addEventListener("touchmove", function (event) {
    if (!swipe) return;
    if (event.touches.length !== 1) {
      swipe = null; // a second finger: Leaflet's pinch
      return;
    }
    var touch = event.touches[0];
    if (!swipe.taker) {
      swipe.taker = pinGeometry.swipeTaker(touch.clientX - swipe.x, touch.clientY - swipe.y, swipe.room, SWIPE_DECIDE);
      if (swipe.taker === "map") {
        swipe = null; // Leaflet moves the chart from where the finger started
        return;
      }
      if (!swipe.taker) {
        event.stopPropagation(); // too short to tell: the chart waits
        return;
      }
    }
    event.stopPropagation(); // the page's swipe: Leaflet doesn't see it
    var step = touch.clientY - swipe.lastY, time = Math.max(1, event.timeStamp - swipe.lastT);
    window.scrollBy(0, -step);
    swipe.speed = 0.8 * (step / time) + 0.2 * swipe.speed; // pixels per millisecond, smoothed
    swipe.lastY = touch.clientY;
    swipe.lastT = event.timeStamp;
  }, { capture: true, passive: true });
  // Leaflet still sees the end of every touch: it ends its own (unmoved) drag there.
  window.addEventListener("touchend", function () {
    if (!swipe || swipe.taker !== "page") {
      swipe = null;
      return;
    }
    // A flick glides on and slows down, as the page itself would; not with reduced motion.
    var speed = swipe.speed, last = performance.now();
    swipe = null;
    if (reduceMotion || Math.abs(speed) < 0.1) return;
    glide = requestAnimationFrame(function step(now) {
      var dt = now - last;
      last = now;
      window.scrollBy(0, -speed * dt);
      speed *= Math.pow(0.995, dt);
      if (Math.abs(speed) > 0.02) glide = requestAnimationFrame(step);
    });
  }, { capture: true, passive: true });

  // ---------- Wiring ----------
  document.addEventListener("click", function (event) {
    // A drag that started on a number and ended on it is a drag, not a pick (#111).
    if (event.target.closest(".leaflet-marker-pane") && map.dragging.moved()) return;
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

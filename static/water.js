/* Haven Daily: the lines in the water (#104), worked out in a background worker (#111).
   Each line follows the shore at a fixed distance. They come from a map of distances: the land
   is filled in as a mask, then every pixel of water gets its exact distance to the nearest land
   pixel (a Euclidean distance transform: two quick passes, one down the columns and one along
   the rows). A pixel is part of a line where that distance is 25, 50, 100... metres. The lines
   are decoration, not depths.

   This takes a second or more for a laptop-sized chart, so it runs in a worker: map.js starts
   one from this file, sends it the land once, then asks for one picture per zoom level (the
   view plus a margin). The page keeps responding meanwhile; map.js shows the previous picture,
   scaled, until the new one arrives (before #111 the page froze 1.3-1.8 s after every zoom step).

   Pure JavaScript, no page, canvas or Leaflet, so tests/test_water.py runs it in Node.
   It loads nothing (hard rule 14). */
(function (root) {
  "use strict";

  var COAST_LINE_GAP = 6; // minimum pixels between two lines in the water
  var COAST_LINE_REACH = 120; // how far from the shore the lines go, in pixels
  var COAST_LINE_WIDTH = 0.8;
  var TOLERANCE = 0.75; // points closer than this (pixels) to the last one used are skipped

  // Lines every 25, 50, 100, 200... metres: the closest spacing still COAST_LINE_GAP apart.
  // Zooming in by one step halves the spacing, so the lines already drawn stay where they are.
  function lineSpacing(perMetre) {
    var metres = 25;
    while (metres * perMetre < COAST_LINE_GAP) metres *= 2;
    var gap = metres * perMetre;
    return { metres: metres, gap: gap, count: Math.floor(COAST_LINE_REACH / gap) };
  }

  // The land as a mask over `box` (world pixels at scale s; 1 = land): a pixel is land when its
  // centre lies inside, counted "evenodd" so holes stay water, as the canvas fills it. Rings
  // are { pts (world pixels at zoom 0, x and y in turn), minX, minY, maxX, maxY }.
  function landMask(rings, s, box, tolerance) {
    var w = box.maxX - box.minX, h = box.maxY - box.minY, rows = new Array(h);
    for (var r = 0; r < h; r++) rows[r] = [];
    for (var k = 0; k < rings.length; k++) {
      var ring = rings[k];
      if (ring.maxX * s < box.minX || ring.minX * s > box.maxX || ring.maxY * s < box.minY || ring.minY * s > box.maxY) continue;
      var pts = ring.pts, n = pts.length;
      var fx = pts[0] * s - box.minX, fy = pts[1] * s - box.minY, lx = fx, ly = fy;
      for (var i = 2; i <= n; i += 2) {
        var px, py;
        if (i < n) {
          px = pts[i] * s - box.minX;
          py = pts[i + 1] * s - box.minY;
          if (i < n - 2 && Math.abs(px - lx) + Math.abs(py - ly) < tolerance) continue;
        } else {
          px = fx; // back to the first point: the ring is closed
          py = fy;
        }
        crossings(rows, h, lx, ly, px, py);
        lx = px;
        ly = py;
      }
    }
    var mask = new Uint8Array(w * h);
    for (var row = 0; row < h; row++) {
      var xs = rows[row];
      if (xs.length < 2) continue;
      xs.sort(function (a, b) { return a - b; });
      for (var j = 0; j + 1 < xs.length; j += 2) {
        var from = Math.max(0, Math.ceil(xs[j] - 0.5)), to = Math.min(w, Math.ceil(xs[j + 1] - 0.5));
        if (to > from) mask.fill(1, row * w + from, row * w + to);
      }
    }
    return mask;
  }
  // Where one edge crosses the middle of each pixel row (the top end counts, the bottom one not,
  // so a corner shared by two edges is counted once).
  function crossings(rows, h, x0, y0, x1, y1) {
    if (y0 === y1) return;
    var top = Math.min(y0, y1), bottom = Math.max(y0, y1), slope = (x1 - x0) / (y1 - y0);
    var first = Math.max(0, Math.ceil(top - 0.5)), last = Math.min(h - 1, Math.ceil(bottom - 0.5) - 1);
    for (var r = first; r <= last; r++) rows[r].push(x0 + (r + 0.5 - y0) * slope);
  }

  // Squared distance to the nearest zero along one row or column (Felzenszwalb and
  // Huttenlocher's lower envelope of parabolas). f: input, d: output, v and z: work space.
  function distances1d(f, n, d, v, z) {
    var k = 0;
    v[0] = 0;
    z[0] = -Infinity;
    z[1] = Infinity;
    for (var q = 1; q < n; q++) {
      var s = (f[q] + q * q - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k]);
      while (s <= z[k]) {
        k--;
        s = (f[q] + q * q - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k]);
      }
      k++;
      v[k] = q;
      z[k] = s;
      z[k + 1] = Infinity;
    }
    k = 0;
    for (var p = 0; p < n; p++) {
      while (z[k + 1] < p) k++;
      d[p] = (p - v[k]) * (p - v[k]) + f[v[k]];
    }
  }
  // cells: 0 on land, a huge number on water; afterwards each cell's squared distance (pixels).
  function distanceMap(cells, w, h) {
    var n = Math.max(w, h), f = new Float64Array(n), d = new Float64Array(n), v = new Int32Array(n), z = new Float64Array(n + 1);
    var x, y;
    for (x = 0; x < w; x++) {
      for (y = 0; y < h; y++) f[y] = cells[y * w + x];
      distances1d(f, h, d, v, z);
      for (y = 0; y < h; y++) cells[y * w + x] = d[y];
    }
    for (y = 0; y < h; y++) {
      for (x = 0; x < w; x++) f[x] = cells[y * w + x];
      distances1d(f, w, d, v, z);
      for (x = 0; x < w; x++) cells[y * w + x] = d[x];
    }
  }

  // The water picture for a box of world pixels at one zoom. job: { id, zoom, s (scale of that
  // zoom), x, y (top left), w, h, worldPerMetre, sea and line ([red, green, blue]) }.
  // Returns the job's place and size with the pixels (red, green, blue, alpha per pixel).
  function waterPicture(job, rings) {
    var w = job.w, h = job.h, spacing = lineSpacing(job.worldPerMetre * job.s);
    var gap = spacing.gap, count = spacing.count;
    // Land up to the furthest line outside the box counts too.
    var edge = Math.ceil(count * gap) + 2, mw = w + 2 * edge, mh = h + 2 * edge;
    var mask = landMask(rings, job.s, { minX: job.x - edge, minY: job.y - edge, maxX: job.x + w + edge, maxY: job.y + h + edge }, TOLERANCE);
    var cells = new Float32Array(mw * mh);
    for (var i = 0; i < cells.length; i++) cells[i] = mask[i] ? 0 : 1e20;
    distanceMap(cells, mw, mh);

    var out = new Uint8ClampedArray(w * h * 4), sea = job.sea, line = job.line;
    // How strong each line is: strongest near the shore, fading outwards.
    var strength = [0];
    for (var k = 1; k <= count; k++) strength.push(0.06 + 0.5 * Math.pow(1 - (k - 1) / count, 1.8));
    var half = COAST_LINE_WIDTH / 2;
    for (var py = 0; py < h; py++) {
      for (var px = 0, o = 4 * py * w, c = (py + edge) * mw + edge; px < w; px++, o += 4, c++) {
        // Distance from the shore: to the nearest land pixel's centre, less half a pixel.
        var dist = Math.sqrt(cells[c]) - 0.5, nearest = Math.round(dist / gap), a = 0;
        if (nearest >= 1 && nearest <= count) {
          // How much of this pixel the 0.8 px line covers, times the line's strength.
          var centre = nearest * gap;
          a = Math.max(0, Math.min(dist + 0.5, centre + half) - Math.max(dist - 0.5, centre - half)) * strength[nearest];
        }
        out[o] = sea[0] + (line[0] - sea[0]) * a;
        out[o + 1] = sea[1] + (line[1] - sea[1]) * a;
        out[o + 2] = sea[2] + (line[2] - sea[2]) * a;
        out[o + 3] = 255;
      }
    }
    return { id: job.id, zoom: job.zoom, x: job.x, y: job.y, w: w, h: h, pixels: out };
  }

  root.HavenWater = { lineSpacing: lineSpacing, landMask: landMask, distanceMap: distanceMap, waterPicture: waterPicture };

  // In a worker: the land comes once, then each message asks for one picture. The pixels are
  // handed over, not copied.
  if (typeof WorkerGlobalScope !== "undefined" && root instanceof WorkerGlobalScope) {
    var land = [];
    root.onmessage = function (event) {
      var message = event.data;
      if (message.land) {
        land = message.land;
        return;
      }
      var picture = waterPicture(message, land);
      root.postMessage(picture, [picture.pixels.buffer]);
    };
  }
})(typeof self !== "undefined" ? self : globalThis);

/* Haven Daily: shared by every page. Loaded in <head>.

   1. Marks the page as having JavaScript, so controls that need it (class "needs-js") are
      shown only when they will work.
   2. The header bar (#102): visible when the page loads; slides away while you scroll down, and
      comes back when you scroll up, move the cursor to the top of the screen (not over the chart,
      #111), or tab into it.
      The same on a phone (touch scrolling) and a laptop. Nothing is stored: no cookies, no
      browser storage. Without JavaScript the bar simply scrolls away with the page (style.css). */
document.documentElement.classList.add("js");

document.addEventListener("DOMContentLoaded", function () {
  var bar = document.querySelector(".topbar");
  if (!bar) return;

  var NEAR_TOP = 48;  // px from the top of the window: the cursor there brings the bar back
  var MIN_MOVE = 6;   // px of scrolling before the bar reacts, so a jittery scroll doesn't flicker
  var height = bar.offsetHeight;
  var last = window.scrollY;
  var hidden = false;

  function hide(yes) {
    if (yes === hidden) return;
    hidden = yes;
    bar.classList.toggle("is-hidden", yes);
  }

  window.addEventListener("scroll", function () {
    var y = window.scrollY;
    bar.classList.toggle("is-stuck", y > 0);
    if (y <= height) {
      hide(false);                                         // at the top of the page: always shown
    } else if (y > last + MIN_MOVE) {
      hide(!bar.contains(document.activeElement));         // going down, unless you are in the bar
    } else if (y < last - MIN_MOVE) {
      hide(false);                                         // going up
    } else {
      return;                                              // a small move: wait for more
    }
    last = y;
  }, { passive: true });

  // Not while the cursor is over the chart: there the top of the window is the chart's own top
  // edge, with the ship filter (owner, 21 Nov 2026, #111).
  document.addEventListener("mousemove", function (event) {
    if (hidden && event.clientY <= NEAR_TOP && !(event.target.closest && event.target.closest(".chart"))) hide(false);
  }, { passive: true });

  bar.addEventListener("focusin", function () { hide(false); });

  window.addEventListener("resize", function () { height = bar.offsetHeight; }, { passive: true });
});

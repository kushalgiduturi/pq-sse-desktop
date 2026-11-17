/* PQ-SSE Desktop website: the small script. Everything on the site works without it.
   - theme toggle, remembered in localStorage (wrapped: private windows may refuse storage);
     without a choice the system setting decides (CSS prefers-color-scheme)
   - the mobile menu button
   - the pointer light on the page panel and the sliding pill of segmented controls
     (from Hastra assets/js/spatial-fx.js; skipped with reduced motion and coarse pointers)
   - copy buttons for hashes and commands, with a short toast
   No analytics, no cookies, no requests to other sites. */
(function () {
  'use strict';
  var root = document.documentElement;
  root.classList.add('js');

  // ── theme ───────────────────────────────────────────────────────────────
  var KEY = 'pqsse-theme';
  function stored() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function store(v) { try { localStorage.setItem(KEY, v); } catch (e) { /* storage refused: the choice lasts for this page */ } }
  function current() {
    var t = root.getAttribute('data-theme');
    if (t) return t;
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }
  var saved = stored();
  if (saved === 'light' || saved === 'dark') root.setAttribute('data-theme', saved);

  function label(btn) {
    var next = current() === 'dark' ? 'light' : 'dark';
    btn.setAttribute('aria-label', btn.getAttribute('data-label-' + next));
    btn.setAttribute('title', btn.getAttribute('data-label-' + next));
    btn.setAttribute('data-shows', current());
  }

  function ready(fn) { if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn); else fn(); }

  ready(function () {
    document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
      btn.hidden = false;
      label(btn);
      btn.addEventListener('click', function () {
        var next = current() === 'dark' ? 'light' : 'dark';
        root.setAttribute('data-theme', next);
        store(next);
        document.querySelectorAll('[data-theme-toggle]').forEach(label);
        placeAll();
      });
    });

    // ── mobile menu ─────────────────────────────────────────────────────────
    var bar = document.querySelector('.sp-bar');
    var menu = document.querySelector('.sp-menu-toggle');
    if (bar && menu) {
      menu.addEventListener('click', function () {
        var open = bar.classList.toggle('is-open');
        menu.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && bar.classList.contains('is-open')) { bar.classList.remove('is-open'); menu.setAttribute('aria-expanded', 'false'); menu.focus(); }
      });
    }

    // ── copy buttons ────────────────────────────────────────────────────────
    var toast = document.querySelector('.sp-toast');
    var timer = 0;
    function say(text) {
      if (!toast) return;
      toast.querySelector('span').textContent = text;
      toast.classList.add('is-shown');
      clearTimeout(timer);
      timer = setTimeout(function () { toast.classList.remove('is-shown'); }, 2400);
    }
    document.querySelectorAll('[data-copy]').forEach(function (btn) {
      btn.hidden = false;
      btn.addEventListener('click', function () {
        var text = btn.getAttribute('data-copy');
        var done = function () { say(btn.getAttribute('data-copied') || 'Copied'); };
        if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done, function () { say(btn.getAttribute('data-copy-failed') || 'Select the text and copy it'); });
        else say(btn.getAttribute('data-copy-failed') || 'Select the text and copy it');
      });
    });

    watch();
  });

  // ── segmented control pill ───────────────────────────────────────────────
  function place(group) {
    var b = group.querySelector(':scope > [aria-pressed="true"], :scope > [aria-current="true"]');
    if (!b) { group.style.setProperty('--sp-ind-w', '0px'); return; }
    group.style.setProperty('--sp-ind-w', b.offsetWidth + 'px');
    group.style.setProperty('--sp-ind-x', b.offsetLeft + 'px');
  }
  function placeAll() { document.querySelectorAll('.sp-seg').forEach(place); }
  function watch() {
    var mo = new MutationObserver(function (records) {
      records.forEach(function (r) { var g = r.target.parentElement; if (g && g.matches('.sp-seg')) place(g); });
    });
    document.querySelectorAll('.sp-seg').forEach(function (g) {
      mo.observe(g, { subtree: true, attributes: true, attributeFilter: ['aria-pressed', 'aria-current'] });
    });
    placeAll();
    window.addEventListener('resize', placeAll, { passive: true });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(placeAll);
  }
  window.PQSSE = { placeAll: placeAll };

  // ── pointer light on the page panel ──────────────────────────────────────
  var still = window.matchMedia('(prefers-reduced-motion: reduce), (pointer: coarse)');
  var raf = 0, last = null;
  document.addEventListener('pointermove', function (e) {
    if (still.matches || (e.pointerType && e.pointerType !== 'mouse' && e.pointerType !== 'pen')) return;
    last = e;
    if (!raf) raf = requestAnimationFrame(function () {
      raf = 0;
      var g = last.target.closest && last.target.closest('.sp-panel.sp-glass');
      if (!g) return;
      var r = g.getBoundingClientRect();
      g.style.setProperty('--sp-mx', (last.clientX - r.left).toFixed(0) + 'px');
      g.style.setProperty('--sp-my', (last.clientY - r.top).toFixed(0) + 'px');
    });
  }, { passive: true });
})();

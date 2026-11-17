/* Verify a download: computes the SHA-256 of a file the visitor picks, in this browser, with the
   Web Crypto API, and compares it (or a pasted checksum) with the published checksums, which are
   in the page itself. The file is read locally and never uploaded; nothing is sent anywhere. */
(function () {
  'use strict';
  var box = document.getElementById('verify');
  if (!box) return;
  document.documentElement.classList.add('js-verify');
  var known = JSON.parse(box.getAttribute('data-hashes') || '{}');   // sha256 -> file name
  var version = box.getAttribute('data-version');
  var out = document.getElementById('vf-result');
  var file = document.getElementById('vf-file');
  var hash = document.getElementById('vf-hash');
  var btn = document.getElementById('vf-check');

  function msg(key, values) {
    var text = box.getAttribute('data-msg-' + key) || '';
    Object.keys(values || {}).forEach(function (k) { text = text.split('{' + k + '}').join(values[k]); });
    return text;
  }
  function show(kind, text) {
    out.className = 'sp-alert sp-alert--' + kind;
    out.textContent = text;
  }
  function compare(sha, name) {
    var match = known[sha];
    if (!match) { show('bad', msg('nomatch', { version: version })); return; }
    if (name && name !== match) show('ok', msg('match-name', { file: match, version: version, name: name }));
    else show('ok', msg('match', { file: match, version: version }));
  }

  btn.addEventListener('click', function () {
    var v = (hash.value || '').trim().toLowerCase().replace(/\s+/g, '');
    if (!/^[0-9a-f]{64}$/.test(v)) { hash.setAttribute('aria-invalid', 'true'); show('bad', msg('bad')); return; }
    hash.removeAttribute('aria-invalid');
    compare(v, null);
  });
  hash.addEventListener('keydown', function (e) { if (e.key === 'Enter') btn.click(); });

  file.addEventListener('change', function () {
    var f = file.files && file.files[0];
    if (!f) return;
    if (!(window.crypto && crypto.subtle && window.isSecureContext)) { show('warn', msg('nocrypto')); return; }
    show('info', msg('computing', { name: f.name }));
    f.arrayBuffer().then(function (buf) { return crypto.subtle.digest('SHA-256', buf); }).then(function (digest) {
      var hex = Array.prototype.map.call(new Uint8Array(digest), function (b) { return ('0' + b.toString(16)).slice(-2); }).join('');
      hash.value = hex;
      compare(hex, f.name);
    }, function () { show('warn', msg('nocrypto')); });
  });
})();

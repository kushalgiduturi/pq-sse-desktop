/* Applies the remembered theme before the page is drawn (no flash). Storage may be refused. */
(function () {
  try {
    var t = localStorage.getItem('pqsse-theme');
    if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
  } catch (e) { /* no stored choice: the system setting decides */ }
})();

/* Install guide: the print button (the guide also prints well from the browser menu). */
(function () {
  'use strict';
  document.querySelectorAll('[data-print]').forEach(function (b) {
    b.hidden = false;
    b.addEventListener('click', function () { window.print(); });
  });
})();

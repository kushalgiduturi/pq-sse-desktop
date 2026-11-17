/* Download page: says whether this looks like Windows. The recommended file and every link
   are already in the page; this only changes one sentence. Nothing is sent anywhere. */
(function () {
  'use strict';
  var p = document.querySelector('[data-detect]');
  if (!p) return;
  var ua = navigator.userAgentData;
  var platform = (ua && ua.platform) || navigator.platform || '';
  var windows = /win/i.test(platform) || /Windows NT/.test(navigator.userAgent);
  p.textContent = p.getAttribute(windows ? 'data-windows' : 'data-other');
})();

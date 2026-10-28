/* TEMPORARY: component check for Batch 3A. Replaced in Phase 9. */
(function () {
  'use strict';

  var meBox = document.getElementById('demo-me');
  var stateBox = document.getElementById('demo-states');
  if (!meBox || !stateBox) { return; }

  function loadMe() {
    SDRN.renderState(meBox, { type: 'loading', title: 'Loading your account\u2026' });
    SDRN.api.get('/api/me').then(function (me) {
      meBox.textContent = '';
      var list = document.createElement('dl');
      list.className = 'detail-list';
      [['Name', me.full_name], ['Email', me.email], ['Role', SDRN.labels.role[me.role] || me.role]].forEach(function (pair) {
        var dt = document.createElement('dt');
        dt.textContent = pair[0];
        var dd = document.createElement('dd');
        dd.textContent = pair[1];
        list.appendChild(dt);
        list.appendChild(dd);
      });
      meBox.appendChild(list);
    }).catch(function (err) {
      if (err && err.handled) { return; }
      SDRN.renderState(meBox, {
        type: 'error',
        title: 'Could not load your account',
        message: err.message,
        actionLabel: 'Try again',
        onAction: loadMe
      });
    });
  }

  document.getElementById('demo-toast-success').addEventListener('click', function () {
    SDRN.toast('This is a success message.', 'success');
  });
  document.getElementById('demo-toast-error').addEventListener('click', function () {
    SDRN.toast('This is an error message. It stays longer.', 'error');
  });

  document.getElementById('demo-confirm').addEventListener('click', function () {
    SDRN.confirm({
      title: 'Delete this record?',
      message: 'This cannot be undone. Press Escape or Cancel to keep it.',
      confirmText: 'Delete',
      danger: true
    }).then(function (confirmed) {
      SDRN.toast(confirmed ? 'You confirmed.' : 'You cancelled.', confirmed ? 'success' : 'info');
    });
  });

  document.getElementById('demo-loading').addEventListener('click', function (event) {
    var button = event.currentTarget;
    SDRN.setLoading(button, true, 'Saving\u2026');
    setTimeout(function () { SDRN.setLoading(button, false); }, 2000);
  });

  document.querySelectorAll('[data-demo-state]').forEach(function (button) {
    button.addEventListener('click', function () {
      var type = button.getAttribute('data-demo-state');
      SDRN.renderState(stateBox, {
        type: type,
        title: type === 'loading' ? 'Loading records\u2026' : type === 'empty' ? 'No records yet' : 'Could not load records',
        message: type === 'loading' ? '' : type === 'empty' ? 'When records exist they will appear here.' : 'Check your connection and try again.',
        actionLabel: type === 'error' ? 'Try again' : '',
        onAction: function () { SDRN.toast('Retry clicked.', 'info'); }
      });
    });
  });

  document.getElementById('demo-reload').addEventListener('click', loadMe);

  SDRN.renderState(stateBox, { type: 'empty', title: 'Pick a state above', message: 'Loading, empty and error states share one look.' });
  loadMe();
})();

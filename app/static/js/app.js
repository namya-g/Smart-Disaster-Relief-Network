/* SDRN shared UI helpers. Loaded on every page (deferred). */
(function () {
  'use strict';

  var SDRN = (window.SDRN = window.SDRN || {});

  /* ---- Shared vocabulary: must match the database/API values ------------ */
  SDRN.labels = {
    status: { pending: 'Pending', approved: 'Approved', rejected: 'Rejected', assigned: 'Assigned', in_progress: 'In progress', resolved: 'Resolved', cancelled: 'Cancelled' },
    category: { medical: 'Medical assistance', food: 'Food', water: 'Water', shelter: 'Shelter', rescue: 'Rescue', other: 'Other' },
    priority: { low: 'Low', medium: 'Medium', high: 'High', critical: 'Critical' },
    resourceCategory: { medical_supplies: 'Medical supplies', food: 'Food', water: 'Water', blankets: 'Blankets', equipment: 'Equipment', other: 'Other' },
    resourceStatus: { available: 'Available', low: 'Low stock', unavailable: 'Unavailable' },
    shelterStatus: { open: 'Open', full: 'Full', temporarily_closed: 'Temporarily closed' },
    role: { citizen: 'Citizen', volunteer: 'Volunteer', administrator: 'Administrator' }
  };

  SDRN.tones = {
    status: { pending: 'warning', approved: 'primary', rejected: 'danger', assigned: 'info', in_progress: 'info', resolved: 'success', cancelled: 'neutral' },
    priority: { low: 'neutral', medium: 'info', high: 'warning', critical: 'critical' },
    resourceStatus: { available: 'success', low: 'warning', unavailable: 'danger' },
    shelterStatus: { open: 'success', full: 'warning', temporarily_closed: 'neutral' }
  };

  /* ---- Small utilities ---------------------------------------------------- */
  SDRN.escapeHtml = function (value) {
    return String(value === null || value === undefined ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  };

  /* kind: 'status' | 'priority' | 'resourceStatus' | 'shelterStatus' */
  SDRN.badge = function (kind, value) {
    var label = (SDRN.labels[kind] && SDRN.labels[kind][value]) || value;
    var tone = (SDRN.tones[kind] && SDRN.tones[kind][value]) || 'neutral';
    return '<span class="badge badge--' + tone + '"><span class="badge__dot" aria-hidden="true"></span>' +
      SDRN.escapeHtml(label) + '</span>';
  };

  SDRN.formatDate = function (iso) {
    if (!iso) { return '-'; }
    var date = new Date(iso);
    if (isNaN(date.getTime())) { return '-'; }
    return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
  };

  SDRN.debounce = function (fn, wait) {
    var timer = null;
    return function () {
      var args = arguments, self = this;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(self, args); }, wait);
    };
  };

  var ICON_PATHS = {
    success: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    error: '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    warning: '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    info: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
    close: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    empty: '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>'
  };

  function svg(name, size) {
    return '<svg class="icon" width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ' +
      'aria-hidden="true" focusable="false">' + ICON_PATHS[name] + '</svg>';
  }

  /* ---- Toasts ------------------------------------------------------------- */
  /* SDRN.toast(message, 'success' | 'error' | 'warning' | 'info', {duration: ms}) */
  SDRN.toast = function (message, type, options) {
    var region = document.getElementById('toast-region');
    if (!region) { return null; }
    type = (type === 'success' || type === 'error' || type === 'warning') ? type : 'info';
    options = options || {};
    var duration = options.duration !== undefined
      ? options.duration
      : (type === 'error' || type === 'warning' ? 10000 : 6000);

    var toast = document.createElement('div');
    toast.className = 'toast toast--' + type;
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');

    var iconEl = document.createElement('span');
    iconEl.className = 'toast__icon';
    iconEl.innerHTML = svg(type, 20);

    var text = document.createElement('p');
    text.className = 'toast__message';
    text.textContent = message;

    var close = document.createElement('button');
    close.type = 'button';
    close.className = 'toast__close';
    close.setAttribute('aria-label', 'Dismiss notification');
    close.innerHTML = svg('close', 16);

    toast.appendChild(iconEl);
    toast.appendChild(text);
    toast.appendChild(close);

    var timer = null;
    function remove() {
      clearTimeout(timer);
      if (toast.parentNode) { toast.parentNode.removeChild(toast); }
    }
    function start() {
      clearTimeout(timer);
      if (duration > 0) { timer = setTimeout(remove, duration); }
    }
    function pause() { clearTimeout(timer); }

    close.addEventListener('click', remove);
    toast.addEventListener('mouseenter', pause);
    toast.addEventListener('mouseleave', start);
    toast.addEventListener('focusin', pause);
    toast.addEventListener('focusout', start);

    while (region.children.length >= 4) { region.removeChild(region.firstChild); }
    region.appendChild(toast);
    start();
    return { dismiss: remove };
  };

  /* ---- Confirm dialog ------------------------------------------------------ */
  /* SDRN.confirm({title, message, confirmText, cancelText, danger}) -> Promise<boolean> */
  var dialogCounter = 0;
  SDRN.confirm = function (options) {
    options = options || {};
    var title = options.title || 'Are you sure?';
    var message = options.message || '';
    var confirmText = options.confirmText || 'Confirm';
    var cancelText = options.cancelText || 'Cancel';

    return new Promise(function (resolve) {
      if (typeof HTMLDialogElement === 'undefined') {
        resolve(window.confirm(title + (message ? '\n\n' + message : '')));
        return;
      }
      var previouslyFocused = document.activeElement;
      var id = 'confirm-dialog-' + (++dialogCounter);
      var result = false;

      var dialog = document.createElement('dialog');
      dialog.className = 'dialog';
      dialog.setAttribute('aria-labelledby', id + '-title');
      dialog.setAttribute('aria-describedby', id + '-body');
      dialog.innerHTML =
        '<form method="dialog" class="dialog__content">' +
        '<h2 class="dialog__title" id="' + id + '-title">' + SDRN.escapeHtml(title) + '</h2>' +
        '<p class="dialog__body" id="' + id + '-body">' + SDRN.escapeHtml(message) + '</p>' +
        '<div class="dialog__actions">' +
        '<button type="submit" value="cancel" class="btn btn--secondary">' + SDRN.escapeHtml(cancelText) + '</button>' +
        '<button type="submit" value="confirm" class="btn ' + (options.danger ? 'btn--danger' : 'btn--primary') + '">' +
        SDRN.escapeHtml(confirmText) + '</button>' +
        '</div></form>';
      document.body.appendChild(dialog);

      var cancelBtn = dialog.querySelector('button[value="cancel"]');
      dialog.querySelector('button[value="confirm"]').addEventListener('click', function () { result = true; });
      dialog.addEventListener('click', function (event) {
        if (event.target === dialog) { dialog.close(); }  /* click on backdrop = cancel */
      });
      dialog.addEventListener('close', function () {
        dialog.parentNode && dialog.parentNode.removeChild(dialog);
        if (previouslyFocused && previouslyFocused.focus) { previouslyFocused.focus(); }
        resolve(result);
      });
      dialog.showModal();
      cancelBtn.focus();  /* safest default for destructive actions */
    });
  };

  /* ---- Loading buttons ---------------------------------------------------- */
  SDRN.setLoading = function (button, loading, text) {
    if (!button) { return; }
    if (loading) {
      if (button.dataset.originalHtml === undefined) { button.dataset.originalHtml = button.innerHTML; }
      button.textContent = text || 'Working\u2026';
      button.disabled = true;
      button.classList.add('is-loading');
      button.setAttribute('aria-busy', 'true');
    } else {
      if (button.dataset.originalHtml !== undefined) {
        button.innerHTML = button.dataset.originalHtml;
        delete button.dataset.originalHtml;
      }
      button.disabled = false;
      button.classList.remove('is-loading');
      button.removeAttribute('aria-busy');
    }
  };

  /* ---- Form errors --------------------------------------------------------- */
  SDRN.clearFormErrors = function (form) {
    form.querySelectorAll('[data-error-for]').forEach(function (el) { el.textContent = ''; el.hidden = true; });
    form.querySelectorAll('[aria-invalid="true"]').forEach(function (el) { el.removeAttribute('aria-invalid'); });
    var formError = form.querySelector('[data-form-error]');
    if (formError) { formError.textContent = ''; formError.hidden = true; }
  };

  /* fields: {fieldName: 'message'}; message: optional form-level text.
     Returns true if a form-level error element was available to show it. */
  SDRN.showFormErrors = function (form, fields, message) {
    SDRN.clearFormErrors(form);
    var firstInvalid = null;
    Object.keys(fields || {}).forEach(function (name) {
      var holder = form.querySelector('[data-error-for="' + name + '"]');
      var input = form.elements[name];
      if (holder) { holder.textContent = fields[name]; holder.hidden = false; }
      if (input && input.setAttribute) {
        input.setAttribute('aria-invalid', 'true');
        if (!firstInvalid) { firstInvalid = input; }
      }
    });
    var shown = false;
    var formError = form.querySelector('[data-form-error]');
    if (message && formError) {
      formError.textContent = message;
      formError.hidden = false;
      shown = true;
    }
    if (firstInvalid) { firstInvalid.focus(); }
    return shown;
  };

  /* ---- Loading / empty / error states ------------------------------------- */
  /* SDRN.renderState(container, {type: 'loading'|'empty'|'error', title, message, actionLabel, onAction}) */
  SDRN.renderState = function (container, state) {
    var type = state.type || 'empty';
    container.textContent = '';

    var box = document.createElement('div');
    box.className = 'state state--' + type;
    box.setAttribute('role', type === 'error' ? 'alert' : 'status');

    var iconWrap = document.createElement('div');
    iconWrap.className = 'state__icon';
    if (type === 'loading') {
      var spinner = document.createElement('div');
      spinner.className = 'spinner';
      iconWrap.appendChild(spinner);
    } else {
      iconWrap.innerHTML = svg(type === 'error' ? 'error' : 'empty', 40);
    }
    box.appendChild(iconWrap);

    var title = document.createElement('p');
    title.className = 'state__title';
    title.textContent = state.title || (type === 'loading' ? 'Loading\u2026' : type === 'error' ? 'Something went wrong' : 'Nothing here yet');
    box.appendChild(title);

    if (state.message) {
      var text = document.createElement('p');
      text.className = 'state__text';
      text.textContent = state.message;
      box.appendChild(text);
    }
    if (state.actionLabel && typeof state.onAction === 'function') {
      var actions = document.createElement('div');
      actions.className = 'state__actions';
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn--secondary';
      button.textContent = state.actionLabel;
      button.addEventListener('click', state.onAction);
      actions.appendChild(button);
      box.appendChild(actions);
    }
    container.appendChild(box);
  };

  /* ---- Collapsibles: sidebar drawer, user dropdown, public nav ------------- */
  function togglesFor(target) {
    return document.querySelectorAll('[data-collapse-toggle="' + target.id + '"]');
  }

  function setOpen(target, open, restoreFocus) {
    var kind = target.getAttribute('data-collapsible');
    target.classList.toggle('is-open', open);
    togglesFor(target).forEach(function (btn) { btn.setAttribute('aria-expanded', open ? 'true' : 'false'); });
    if (kind === 'drawer') {
      document.body.classList.toggle('no-scroll', open);
      if (open) {
        var first = target.querySelector('a, button');
        if (first) { first.focus(); }
      }
    }
    if (!open && restoreFocus) {
      var toggle = togglesFor(target)[0];
      if (toggle && toggle.offsetParent !== null) { toggle.focus(); }
    }
  }

  function openCollapsibles() {
    return document.querySelectorAll('[data-collapsible].is-open');
  }

  document.addEventListener('click', function (event) {
    var toggle = event.target.closest('[data-collapse-toggle]');
    if (toggle) {
      var target = document.getElementById(toggle.getAttribute('data-collapse-toggle'));
      if (target) { setOpen(target, !target.classList.contains('is-open')); }
      return;
    }
    var dismiss = event.target.closest('[data-collapse-dismiss]');
    if (dismiss) {
      var dismissTarget = document.getElementById(dismiss.getAttribute('data-collapse-dismiss'));
      if (dismissTarget) { setOpen(dismissTarget, false, true); }
      return;
    }
    /* Selecting a link inside the public nav panel closes it (same-page anchors). */
    var panelLink = event.target.closest('[data-collapsible="panel"] a');
    if (panelLink) { setOpen(panelLink.closest('[data-collapsible="panel"]'), false); }

    /* Click outside an open dropdown closes it. */
    openCollapsibles().forEach(function (el) {
      if (el.getAttribute('data-collapsible') === 'dropdown' && !el.contains(event.target)) {
        setOpen(el, false);
      }
    });
  });

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') { return; }
    openCollapsibles().forEach(function (el) { setOpen(el, false, true); });
  });

  document.querySelectorAll('[data-collapsible="dropdown"]').forEach(function (menu) {
    var wrapper = menu.closest('.dropdown') || menu;
    wrapper.addEventListener('focusout', function (event) {
      if (event.relatedTarget && !wrapper.contains(event.relatedTarget)) { setOpen(menu, false); }
    });
  });

  if (window.matchMedia) {
    var desktop = window.matchMedia('(min-width: 1024px)');
    var onChange = function (event) {
      if (!event.matches) { return; }
      var drawer = document.getElementById('sidebar');
      if (drawer && drawer.classList.contains('is-open')) { setOpen(drawer, false); }
    };
    if (desktop.addEventListener) { desktop.addEventListener('change', onChange); }
  }

  /* ---- Password show/hide --------------------------------------------------- */
  document.addEventListener('click', function (event) {
    var button = event.target.closest('[data-password-toggle]');
    if (!button) { return; }
    var input = document.getElementById(button.getAttribute('aria-controls'));
    if (!input) { return; }
    var show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    button.setAttribute('aria-pressed', show ? 'true' : 'false');
  });

  /* ---- Prevent double submit on plain forms (login, register) ---------------- */
  /* Add data-loading-form to a <form>; optionally data-loading-text on its submit button. */
  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (!form.matches || !form.matches('form[data-loading-form]') || event.defaultPrevented) { return; }
    if (form.dataset.submitted === 'true') { event.preventDefault(); return; }
    form.dataset.submitted = 'true';
    var button = form.querySelector('button[type="submit"]');
    SDRN.setLoading(button, true, button && button.dataset.loadingText);
  });

  window.addEventListener('pageshow', function (event) {
    if (!event.persisted) { return; }  /* page restored from back/forward cache */
    document.querySelectorAll('form[data-loading-form]').forEach(function (form) {
      delete form.dataset.submitted;
      SDRN.setLoading(form.querySelector('button[type="submit"]'), false);
    });
  });
})();

/* SDRN API client. Usage:
     const data = await SDRN.api.get('/api/requests', { query: { status: 'pending' } });
     await SDRN.api.post('/api/requests', { title: '...' });
   Failures throw SDRN.api.ApiError. Show them with SDRN.reportError(err, form). */
(function () {
  'use strict';

  var SDRN = (window.SDRN = window.SDRN || {});

  class ApiError extends Error {
    constructor(message, details) {
      super(message);
      details = details || {};
      this.name = 'ApiError';
      this.status = details.status || 0;
      this.code = details.code || 'unknown_error';
      this.fields = details.fields || null;
      this.network = !!details.network;
      this.handled = false;  /* true when a redirect to login is already under way */
    }
  }

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  function defaultMessage(status) {
    if (status === 401) { return 'Please log in to continue.'; }
    if (status === 403) { return 'You do not have permission to do that.'; }
    if (status === 404) { return 'That record could not be found.'; }
    if (status === 409) { return 'That conflicts with existing data.'; }
    if (status >= 500) { return 'Something went wrong on the server. Please try again.'; }
    return 'The request could not be completed.';
  }

  function defaultCode(status) {
    if (status === 401) { return 'unauthenticated'; }
    if (status === 403) { return 'forbidden'; }
    if (status === 404) { return 'not_found'; }
    if (status === 409) { return 'conflict'; }
    if (status >= 500) { return 'server_error'; }
    return 'request_failed';
  }

  function buildUrl(url, query) {
    if (!query) { return url; }
    var params = new URLSearchParams();
    Object.keys(query).forEach(function (key) {
      var value = query[key];
      if (value !== undefined && value !== null && value !== '') { params.append(key, value); }
    });
    var qs = params.toString();
    if (!qs) { return url; }
    return url + (url.indexOf('?') === -1 ? '?' : '&') + qs;
  }

  function redirectToLogin() {
    if (window.location.pathname.indexOf('/login') === 0) { return; }
    var next = window.location.pathname + window.location.search;
    window.location.assign('/login?expired=1&next=' + encodeURIComponent(next));
  }

  async function request(method, url, options) {
    options = options || {};
    var headers = { 'Accept': 'application/json' };
    var init = { method: method, headers: headers, credentials: 'same-origin' };

    if (options.body !== undefined) {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(options.body);
    }
    if (method !== 'GET' && method !== 'HEAD') { headers['X-CSRFToken'] = csrfToken(); }

    var controller = new AbortController();
    var callerSignal = options.signal;
    if (callerSignal) {
      if (callerSignal.aborted) { controller.abort(); }
      else { callerSignal.addEventListener('abort', function () { controller.abort(); }); }
    }
    init.signal = controller.signal;
    var timer = setTimeout(function () { controller.abort(); }, options.timeout || 20000);

    var response;
    try {
      response = await fetch(buildUrl(url, options.query), init);
    } catch (err) {
      if (err && err.name === 'AbortError') {
        if (callerSignal && callerSignal.aborted) { throw err; }  /* cancelled on purpose */
        throw new ApiError('The server took too long to respond. Please try again.', { code: 'timeout', network: true });
      }
      throw new ApiError('Could not reach the server. Check your connection and try again.', { code: 'network_error', network: true });
    } finally {
      clearTimeout(timer);
    }

    var text = await response.text();
    var payload = null;
    if (text) {
      try { payload = JSON.parse(text); }
      catch (parseError) {
        if (response.ok) {
          throw new ApiError('The server sent a response that could not be read.', { status: response.status, code: 'bad_response' });
        }
      }
    }

    if (response.ok) {
      if (payload && typeof payload === 'object' && 'data' in payload) { return payload.data; }
      return payload;
    }

    var info = (payload && payload.error) || {};
    var apiError = new ApiError(info.message || defaultMessage(response.status), {
      status: response.status,
      code: info.code || defaultCode(response.status),
      fields: info.fields || null
    });
    if (response.status === 401 && options.redirectOnAuthError !== false) {
      apiError.handled = true;
      redirectToLogin();
    }
    throw apiError;
  }

  SDRN.api = {
    ApiError: ApiError,
    get: function (url, options) { return request('GET', url, options); },
    post: function (url, body, options) {
      return request('POST', url, Object.assign({}, options, { body: body === undefined ? {} : body }));
    },
    patch: function (url, body, options) {
      return request('PATCH', url, Object.assign({}, options, { body: body === undefined ? {} : body }));
    },
    delete: function (url, options) { return request('DELETE', url, options); }
  };

  /* Show any failure consistently: field errors on a form, otherwise a toast. */
  SDRN.reportError = function (err, form) {
    if (err && (err.handled || err.name === 'AbortError')) { return; }
    if (err instanceof ApiError) {
      if (err.fields && form && SDRN.showFormErrors) {
        var message = err.code === 'validation_error' ? 'Please correct the highlighted fields.' : err.message;
        var shown = SDRN.showFormErrors(form, err.fields, message);
        if (!shown) { SDRN.toast(message, 'error'); }
        return;
      }
      SDRN.toast(err.message, 'error');
      return;
    }
    if (window.console) { console.error(err); }
    SDRN.toast('Something unexpected went wrong. Please try again.', 'error');
  };
})();

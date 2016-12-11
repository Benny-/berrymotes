/**
 * 404 (Not Found) Handler
 *
 * Usage:
 * return res.notFound();
 * return res.notFound(err);
 * return res.notFound(err, 'some/specific/notfound/view');
 *
 * e.g.:
 * ```
 * return res.notFound();
 * ```
 *
 * First argument can be a string or a Error object.
 *
 * NOTE:
 * If a request doesn't match any explicit routes (i.e. `config/routes.js`)
 * or route blueprints (i.e. "shadow routes", Sails will call `res.notFound()`
 * automatically.
 */

module.exports = function notFound (err, options) {

  // Get access to `req`, `res`, & `sails`
  var req = this.req;
  var res = this.res;
  var sails = req._sails;

  // Set status code
  res.status(404);

  // Log error to console
  if (err !== undefined) {
    sails.log.verbose('Sending 404 ("Not Found") response: \n', err);
  }
  else sails.log.verbose('Sending 404 ("Not Found") response');

  // The locals used in the view or returned as json.
  var locals = {
    reason: undefined,
    stack: undefined,
  }
  
  if(typeof err == 'string')
  {
      locals.reason = err
  }
  else if (err instanceof Error)
  {
      locals.reason = err.message
  }
  
  // Only include stack in response if application environment
  // is not set to 'production'.  In production, we shouldn't
  // send back any identifying information about errors.
  if (sails.config.environment !== 'production') {
    if (err instanceof Error) {
        locals.stack = err.stack
    }
  }

  // If the user-agent wants JSON, always respond with JSON
  if (req.wantsJSON) {
    return res.jsonx(locals);
  }

  // If second argument is a string, we take that to mean it refers to a view.
  // If it was omitted, use an empty object (`{}`)
  options = (typeof options === 'string') ? { view: options } : options || {};

  // If a view was provided in options, serve it.
  // Otherwise try to guess an appropriate view, or if that doesn't
  // work, just send JSON.
  if (options.view) {
    return res.view(options.view, locals);
  }

  // If no second argument provided, try to serve the default view,
  // but fall back to sending JSON(P) if any errors occur.
  else return res.view('404', locals, function (err, html) {

    // If a view error occured, fall back to JSON(P).
    if (err) {
      //
      // Additionally:
      // • If the view was missing, ignore the error but provide a verbose log.
      if (err.code === 'E_VIEW_FAILED') {
        sails.log.verbose('res.notFound() :: Could not locate view for error page (sending JSON instead).  Details: ', err);
      }
      // Otherwise, if this was a more serious error, log to the console with the details.
      else {
        sails.log.warn('res.notFound() :: When attempting to render error page view, an error occured (sending JSON instead).  Details: ', err);
      }
      return res.jsonx(locals);
    }

    return res.send(html);
  });

};


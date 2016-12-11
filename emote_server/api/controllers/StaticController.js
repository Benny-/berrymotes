/**
 * StaticController
 *
 * @description :: This controller only exist so res.locals.user is set by a policy so we can show the user he/she is logged in.
 * @help        :: See http://links.sailsjs.org/docs/controllers
 */

module.exports = {
	homepage: function (req,res) {
	    res.ok()
	},
	
	api: function (req,res) {
	    res.ok()
	},
};


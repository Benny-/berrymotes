module.exports = function(req, res, next){
  res.forbidden('Access to this page is denied for everyone.');
}


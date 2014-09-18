module.exports = function(req, res, next){
  res.forbidden('You are not permitted to perform this action.');
}


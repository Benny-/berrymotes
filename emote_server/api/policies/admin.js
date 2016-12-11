module.exports = function(req, res, next){
  if (req.user && req.user.role == 1){
    return next();
  }else{
    res.forbidden('You must be a administrator to view this page.');
  }
}


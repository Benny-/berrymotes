module.exports = function(req, res, next){
  if (req.isAuthenticated()){
    return next();
  }else{
    res.forbidden('You must be logged in to view this page.');
  }
}


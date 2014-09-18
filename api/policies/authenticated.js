module.exports = function(req, res, next){
  if (req.isAuthenticated()){
    return next();
  }else{
    res.forbidden('You are not permitted to perform this action.');
  }
}


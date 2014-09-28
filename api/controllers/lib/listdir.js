var path = require('path')

var fsp = require('fs-promise')
var Q = require('q')

module.exports = function(dir) {
  var results = {
      dirs: [],
      files: [],
  }
  
  return fsp.readdir(dir)
  .then(function(files) {
      
      return Q.all(files.map(function(file) {
          return fsp.stat(path.join(dir, file))
          .then(function(stat) {
              stat.file = file
              return stat
          })
      }))
      .then(function(stats) {
          stats.forEach(function(stat) {
              if (stat.isFile()) {
                  results.files.push(stat.file)
              }
              else if (stat.isDirectory()) {
                  results.dirs.push(stat.file)
              }
          })
          return results
      })
  })
}

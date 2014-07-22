/**
 * EmoteController
 *
 * @description :: Server-side logic for managing emotes
 * @help        :: See http://links.sailsjs.org/docs/controllers
 */

var fs = require('fs')
var path = require('path')

var createEmoteFromJson = function(external_emote) {
  return Emote.create({
    canonical_name: external_emote.canonical,
  })
}

module.exports = {

  bulk_upload: function (req,res) {
    
    if(req.is('multipart/form-data')) {
      req.file('json_emote_file').upload(function (err, files) {
        if (err)
          return res.serverError(err);
        
        fs.readFile( path.join('.tmp', 'uploads', files[0].filename), { encoding : 'utf-8', flag: 'r' }, function(err, data) {
          
          if(err) {
            res.writeHead(500, {'content-type': 'text'});
            res.end(err.message)
            return
          }
          
          var external_emotes = JSON.parse(data)
          
          external_emotes.map( function(external_emote) {
             createEmoteFromJson(external_emote).then().done(); //I don't know what I am doing.
          })
          
          res.json({
            message: files.length + ' file(s) uploaded successfully!',
            files: files
          });
        });
      });
    }
    else
    {
      res.writeHead(200, {'content-type': 'text/html'});
      res.end(
      '<form action="/emote/bulk_upload" enctype="multipart/form-data" method="post">'+
      '<input type="file" name="json_emote_file" multiple="multiple"><br>'+
      '<input type="submit" value="Upload">'+
      '</form>'
      )
    }
  },
};


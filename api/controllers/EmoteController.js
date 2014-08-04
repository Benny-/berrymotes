/**
 * EmoteController
 *
 * @description :: Server-side logic for managing emotes
 * @help        :: See http://links.sailsjs.org/docs/controllers
 */

var fs = require('fs')
var path = require('path')
var Q = require('q')

// Puts a emote into the database, and returns it in a promise.
var createEmoteFromJson = function(external_emote) {

    var css = {}; // TODO: Fill this field

    return Emote.findOrCreate(
        {
            where: {
                canonical_name: external_emote.canonical,
            }
        },
        {
            canonical_name: external_emote.canonical,
            height: external_emote.height,
            width: external_emote.width,
            "hover-width": external_emote["hover-width"],
            "hover-height": external_emote["hover-height"],
            img_animation: external_emote.img_animation,
            single_image_extension: external_emote.single_image_extension,
            single_hover_image_extension: external_emote.single_hover_image_extension,
            src: external_emote.src,
            css: css,
        }
    )
    // TODO: Update emote if it already exists.
    .then( function(emote) {
        if(external_emote.tags && external_emote.tags.length > 1)
        {
            var tags_promises = external_emote.tags.map( function(external_tag) {
                var promise = Tag.findOrCreate(
                    {
                        where: {
                            name: external_tag,
                        }
                    },
                    {
                        name: external_tag,
                    }
                )
                .then( function(tag) {
                    tag.emotes.add(emote.id) // TODO: Conditionally add so we don't needlessly update the modify date on the tag.
                    return tag.save()
                })
                return promise;
            })
            
            var names_promises = external_emote.names.map( function(external_name) {
                // Note: We don't use findOrCreate here so it fails if it already exist. We shall not override any existing names.
                return Name.create(
                    {
                        name: external_name,
                        emote: emote.id,
                    }
                )
            })
            
            return Q.allSettled( [].concat(tags_promises, names_promises) ) // I don't really care if setting the tags or names succeed.
            .then(function(results) {return emote} ) // So we don't check the resulting promises here.
            .then(function(result) { console.log("Processed emote: " + emote.id ); return result})
        }
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

                var result = Q();
                external_emotes.map( function(external_emote) {
                    // We process the emotes in some order so the database adapter does not get overloaded.
                    // Processing everything at the same time causes disruption in other services this web server provides.
                    result = result.then( function() { return createEmoteFromJson(external_emote) } )
                })
                result.catch(function(err) {
                    console.warn("catch","Something bad happened: " + err)
                })
                .done( function() {
                    console.log("Done", arguments)
                });

                res.json({
                    message: files.length + ' file(s) uploaded successfully. Processing will happen in the background now and might takes a few minutes.',
                    files: files
                });
            });
        });
    }
    else
    {
      res.writeHead(200, {'content-type': 'text/html'});
      res.end(
      '<p>This form expects a json file from the reddit_emote_scraper program</p>'+
      '<form action="/emote/bulk_upload" enctype="multipart/form-data" method="post">'+
      '<input type="file" name="json_emote_file" multiple="multiple"><br>'+
      '<input type="submit" value="Upload">'+
      '</form>'
      )
    }
  },
};


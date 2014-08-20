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

    var css = {};

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

            fs.readFile( files[0].fd, { encoding : 'utf-8', flag: 'r' }, function(err, data) {
              
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
                .done();

                res.json({
                    message: files.length + ' file(s) uploaded successfully. Processing will happen in the background now and might takes a few minutes.',
                    files: files
                });
            });
        });
    }
    else
    {
      return res.view();
    }
  },
  
  submit: function (req,res) {
    if(req.is('multipart/form-data')) {
        req.file('emoticon_images').upload(function (err, files) {
            if (err)
                return res.serverError(err);
            
            emote_data = {}
            
            canonical_name = req.body.canonical_name
            names = req.body.names
            css_user = req.body.css
            tags = req.body.tags
            src = req.body.src
            
            emote_data.canonical_name = canonical_name
            emote_data.src = src
            
            var removeEmptyStrings = function(array_with_strings) {
                return array_with_strings.filter(function(s){return s.trim() != ""})
            }
            
            if (tags) {
                if(!Array.isArray(names))
                    names = [names]
                names = removeEmptyStrings(names)
            }
            
            if (css_user) {
                css = {}
                if(!Array.isArray(css_user))
                    css_user = [css_user]
                css_user = removeEmptyStrings(css_user)
                
                var i = css_user.length;
                while (i--) {
                    // We serialize the single css lines into json here
                    // "some_css_property: 100px"
                    // Becomes:
                    // {"some_css_property":100px}
                    css_arr = css_user[i].split(":",2).map(function(s){return s.trim()})
                    css[css_arr[0]] = css_arr[1]
                }
                emote_data.css = css
            }
            
            if (tags) {
                if(!Array.isArray(tags))
                    tags = [tags]
                tags = removeEmptyStrings(tags)
            }
            
            Emote.create(emote_data)
            .then( function(emote) {
                // TODO: Add tags.
                // TODO: Add names.
                return emote
            })
            .then( function(emote) {
                res.json( {msg:"Successfully added emote",emote:emote})
            })
            .catch(function(err) {
                res.serverError('Something went wrong. ' + err);
            })
            .done()
            
            emoticon_image = files[0]
            emoticon_image_hover = files[1] // emoticon_image_hover is allowed to be undefined
            // TODO: Move files somewhere.
        });
    }
    else
    {
        return res.view();
    }
  },
};


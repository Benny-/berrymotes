/**
 * EmoteController
 *
 * @description :: Server-side logic for managing emotes
 * @help        :: See http://links.sailsjs.org/docs/controllers
 */

var fs = require('fs')
var fsp_extra = require('fs-promise')
var path = require('path')
var Q = require('q')

var createEmote = function(emote_unsafe, update) {
    
}

// Puts a emote into the database, and returns it in a promise.
var createEmoteFromJson = function(external_emote) {
    var css = {}

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

var submitEmote = function(emote_unsafe, files, update) {
    var emote_dict = {}
    
    var canonical_name = emote_unsafe.canonical_name
    var names = emote_unsafe.names
    var css_user = emote_unsafe.css
    var tags = emote_unsafe.tags
    var src = emote_unsafe.src
    
    canonical_name = canonical_name.trim()
    emote_dict.canonical_name = canonical_name
    if(src)
        src = src.trim()
        emote_dict.src = src
    
    var removeEmptyStrings = function(array_with_strings) {
        return array_with_strings.filter(function(s){return s.trim() != ""})
    }
    
    if (tags) {
        if(!Array.isArray(names))
            names = [names]
        names = removeEmptyStrings(names)
    }
    
    // Remove duplicates
    names = names.filter(function(item, pos, self) {
        return self.indexOf(item) == pos;
    })
    
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
        emote_dict.css = css
    }
    
    if (tags) {
        if(!Array.isArray(tags))
            tags = [tags]
        tags = removeEmptyStrings(tags)
    }
    
    var database_promise = undefined
    if (update)
    {
        database_promise = Emote.findOne(
                {
                    where: {
                        canonical_name: external_emote.canonical,
                    }
                })
    }
    else
    {
        database_promise = Emote.create(emote_dict)
    }
    
    var emoticon_image = files[0]
    var emoticon_image_hover = files[1] // emoticon_image_hover is allowed to be undefined
    
    var emoticon_image_path = path.join.apply(path, ["emoticons", "uploaded"].concat(canonical_name.split('/')))
    var emoticon_image_hover_path = emoticon_image_path + '_hover'
    
    var file_promise = fsp_extra.move(emoticon_image.fd, emoticon_image_path)
    if (emoticon_image_hover)
        file_promise = Q.all( file_promise, fsp_extra.move(emoticon_image_hover.fd, emoticon_image_hover_path) )
    
    return Q.all( [database_promise, file_promise] )
            .then( function(arr_results){ return arr_results[0]} )
}

module.exports = {

  bulk_upload: function(req, res) {
    
    if(req.is('multipart/form-data')) {
        req.file('json_emote_file').upload(function (err, files) {
            if (err)
                return res.serverError(err);

            fs.readFile( files[0].fd, { encoding : 'utf-8', flag: 'r' }, function(err, data) {
              
                if(err) {
                    res.serverError(err);
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
      res.view();
    }
  },
  
  submit: function (req,res) {
    if(req.is('multipart/form-data')) {
        req.file('emoticon_images').upload(function (err, files) {
            if (err)
                return res.serverError(err);
            
            submitEmote(req.body, files)
            .then( function(emote) {
                    res.json({
                        msg:"Successfully added emote",
                        emote:emote
                    })
                })
            .catch( function(err) {
                res.serverError(err);
            })
            .done()
        });
    }
    else
    {
      res.view();
    }
  },
  
  edit: function (req,res) {
    if(req.is('multipart/form-data')) {
        req.file('emoticon_images').upload(function (err, files) {
            if (err)
                return res.serverError(err);
            
            submitEmote(req.body, files, true)
            .then( function(emote) {
                    res.json({
                        msg:"Successfully added emote",
                        emote:emote
                    })
                })
            .catch( function(err) {
                res.serverError(err);
            })
            .done()
        });
    }
    else
    {
        var id = req.query.id
        
        if (!id) {
            res.status(400);
            res.view('emote/error', {error:"You must supply a valid id. A canonical name or a numeric id."} );
            return
        }
        
        var promise = undefined
        if (isNaN(+id)) {
            // id is a canonical name.
            promise = Emote.findOne(
            {
                where: {
                    canonical_name: id,
                }
            })
        }
        else {
            // id is a numeric id.
            id = Math.floor(+id)
            promise = Emote.findOne(
            {
                where: {
                    id: id,
                }
            })
        }
        promise.then( function(emote) {
            if (emote === undefined)
                throw new Error("Could not find a emote with id: "+id)
            return emote
        })
        .then(function(emote) {
            if (!emote)
                throw new Error("Could not locate emote")
            res.view( {emote:emote} );
        })
        .catch(function(err) {
            res.status(400);
            res.view('emote/error', {error:err} );
        })
        .done()
    }
  }
}


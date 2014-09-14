/**
 * EmoteController
 *
 * @description :: Server-side logic for managing emotes
 * @help        :: See http://links.sailsjs.org/docs/controllers
 */

var fs = require('fs')
var fsp_extra = require('fs-promise')
var path = require('path')
var image_size = require('image-size')
var Q = require('q')

Q.longStackSupport = true;

// https://stackoverflow.com/revisions/728395/2
// This clone function enough for me.
function clone(obj) {
    if(obj == null || typeof(obj) != 'object')
        return obj;    
    var temp = new obj.constructor(); 
    for(var key in obj)
        temp[key] = clone(obj[key]);    
    return temp;
}

/*
// This function converts something like this:
    [
        {
            "name": "foo",
            "macaroni": true,
        }
        {
            "name": "bar",
            "macaroni": false,
        }
    ]
// into
    [
        "name": "foo",
        "name": "bar",
    ]
*/
var array_name_picker = function(arr)
{
    return arr.map( function(element) {
        return element.name
    })
}

// This function updates the record in the database.
// It does not do any file operations.
var create_emote = function(emote_dict) {
    emote_update_values = clone(emote_dict)
    delete emote_update_values.canonical_name
    delete emote_update_values.names
    delete emote_update_values.tags
    
    return Emote.create(emote_dict)
    .then( function(emote) {
        var tags_promises = emote_dict.tags.map( function(tag) {
            var promise = Tag.findOrCreate(
                {
                    where: {
                        name: tag,
                    }
                },
                {
                    name: tag,
                }
            )
            .then( function(tag) {
                tag.emotes.add(emote.id)
                return tag.save()
            })
            return promise;
        })
        
        var names_promises = emote_dict.names.map( function(name) {
            // Note: We don't use findOrCreate here so it fails if it already exist. We shall not override any existing names.
            return Name.create(
                {
                    name: name,
                    emote: emote.id,
                }
            )
        })
        
        return Q.allSettled( [].concat(tags_promises, names_promises) ) // I don't really care if setting the tags or names succeed.
        .then(function(results) {return emote} )
    })
}

// This function updates the record in the database.
// It does not do any file operations.
var update_emote = function(emote_dict) {
    emote_update_values = clone(emote_dict)
    delete emote_update_values.canonical_name
    delete emote_update_values.names
    delete emote_update_values.tags
    return Emote.findOne({
            where: {
                canonical_name: emote_dict.canonical_name,
            }
        })
    .then( function(emote) {
        if(!emote)
            throw new Error("Emote not found")
        return emote
    })
    .then( function(emote) {
        return Emote.update({
                where: {
                    canonical_name: emote_dict.canonical_name,
                }
            },
            emote_update_values)
        .then(function(results) {
            updated_emote = results[0]
            
            // I kinda need the populated fields, but Emote.update()
            // Does not support chaining .populate()
            // So we must launch a new query
            return Emote.findOne({
                    where: {
                        canonical_name: emote_dict.canonical_name,
                    }
                })
            .populate('names')
            .populate('tags')
        })
    })
    .then( function(emote) {
        var old_tags = array_name_picker(emote.tags)
        var old_tags_dict = {}
        old_tags.forEach(function(value, index, arr) {
            old_tags_dict[value] = true
        })
        var tags_promises = emote_dict.tags.map( function(tag) {
            if(!old_tags_dict[tag])
            {
                var promise = Tag.findOrCreate(
                    {
                        where: {
                            name: tag,
                        }
                    },
                    {
                        name: tag,
                    }
                )
                .then( function(tag) {
                    tag.emotes.add(emote.id)
                    return tag.save()
                })
                return promise;
            }
            // TODO: Add code for removing tags
        })
        
        var old_names = array_name_picker(emote.names)
        var old_names_dict = {}
        old_names.forEach(function(value, index, arr) {
            old_names_dict[value] = true
        })
        var names_promises = emote_dict.names.map( function(name) {
            // Note: We don't use findOrCreate here so it fails if it already exist. We shall not override any existing names.
            if(!old_names_dict[name]) {
                return Name.create(
                    {
                        name: name,
                        emote: emote.id,
                    }
                )
            }
            // TODO: Add code for removing names
        })
        
        return Q.allSettled( [].concat(tags_promises, names_promises) ) // I don't really care if setting the tags or names succeed.
        .then(function(results) {return emote} )                        // So we don't check the resulting promises here.
        .then(function() {
            return Emote.findOne({
                    where: {
                        canonical_name: emote_dict.canonical_name,
                    }
                })
            .populate('names')
            .populate('tags')
        })
    })
}

var move_image = function(from, to, overwrite) {
    var file_promise = Q()
    if(overwrite) {
        file_promise = file_promise.then ( function() {
            sails.log.debug("Removing " + to);
            return fsp_extra.remove(to)
        }, function(err) {
            sails.log.error("Remove failed, but I don't care: " + err);
        })
    }
    file_promise = file_promise.then ( function() {
        return fsp_extra.move(from, to)
    })
    return file_promise
}

var submit_emote = function(emote_unsafe, files, update) {
    var emote_dict = {}
    
    var canonical_name = emote_unsafe.canonical_name
    var names = emote_unsafe.names
    var css_user = emote_unsafe.css
    var tags = emote_unsafe.tags
    var src = emote_unsafe.src
    
    canonical_name = canonical_name.trim() // More checking is required on canonical_name.
    emote_dict.canonical_name = canonical_name
    if(src)
        src = src.trim()
        emote_dict.src = src
    
    var removeEmptyStrings = function(array_with_strings) {
        return array_with_strings.filter(function(s){return s.trim() != ""})
    }
    
    if (!names)
        names = []
    
    if (!update)
        names.push(canonical_name)
    
    if(!Array.isArray(names))
        names = [names]
    names = removeEmptyStrings(names)
    
    // Remove duplicates
    names = names.filter(function(item, pos, self) {
        return self.indexOf(item) == pos;
    })
    
    if (!tags)
        tags = []
    
    if(!Array.isArray(tags))
        tags = [tags]
    tags = removeEmptyStrings(tags)
    
    emote_dict.names = names
    emote_dict.tags = tags
    
    if (css_user) {
        var css = {}
        if(!Array.isArray(css_user))
            css_user = [css_user]
        css_user = removeEmptyStrings(css_user)
        
        var i = css_user.length;
        while (i--) {
            // We serialize the single css lines into json here
            // "some_css_property: 100px"
            // Becomes:
            // {"some_css_property":"100px"}
            css_arr = css_user[i].split(":",2).map(function(s){return s.trim()})
            css[css_arr[0]] = css_arr[1]
        }
        emote_dict.css = css
    }
    
    var emoticon_image = files[0] // emoticon_image is allowed to be undefined if 'update' is false
    var emoticon_image_hover = files[1] // emoticon_image_hover is allowed to be undefined
    
    var emoticon_image_path = path.join.apply(path, ["emoticons", "uploaded"].concat(canonical_name.split('/')))
    var emoticon_image_hover_path = emoticon_image_path + '_hover'
    
    var file_promise = undefined
    var base_image_promise = undefined
    var hover_image_promise = undefined
    
    if(!emoticon_image && !update)
    {
        return Q.reject(new Error("A emoticon must have a base image"))
    }
    
    if (emoticon_image) {
        base_image_promise = Q.nfcall(image_size, emoticon_image.fd)
        .then( function(dimensions) {
            emote_dict.width = dimensions.width
            emote_dict.height = dimensions.height
        })
        .then( function() { move_image(emoticon_image.fd, emoticon_image_path, update) })
    }
    else {
        base_image_promise = Q("Base image file unchanged");
    }
    
    if (emoticon_image_hover) {
        hover_image_promise = Q.nfcall(image_size, emoticon_image_hover.fd)
        .then( function(dimensions) {
            emote_dict["hover-width"] = dimensions.width
            emote_dict["hover-height"] = dimensions.height
        })
        .then( function() { move_image(emoticon_image_hover.fd, emoticon_image_hover_path, update) })
    }
    else {
        hover_image_promise = Q("Hover image file unchanged");
    }
    
    file_promise = Q.all( [base_image_promise, hover_image_promise] )
    
    return file_promise.then( function() {
        var database_promise = undefined
        if (update) {
            database_promise = update_emote(emote_dict)
        }
        else {
            database_promise = create_emote(emote_dict)
        }
        
        return database_promise
    })
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
                    result = result.then( function() {
                        var css = {}
                        
                        emote_dict = {
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
                        
                        return create_emote(emote_dict)
                        .then(
                            function(emote) { console.log("Created new emote: " + emote.id + " " + external_emote.canonical ); return emote},
                            function() { return update_emote(emote_dict)
                                                .then(function(emote) { console.log("Updated emote: " + emote.id + " " + external_emote.canonical ); return emote })
                                        }
                        )
                    } )
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
            
            submit_emote(req.body, files)
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
            
            submit_emote(req.body, files, true)
            .then( function(emote) {
                    res.json({
                        msg:"Successfully edited emote",
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
        promise = promise
        .populate('names')
        .populate('tags')
        
        promise.then( function(emote) {
            if (emote === undefined)
                throw new Error("Could not find a emote with id: "+id)
            return emote
        })
        .then(function(emote) {
            res.view( {emote:emote} )
        })
        .catch(function(err) {
            res.status(400);
            res.view('emote/error', {error:err} );
        })
        .done()
    }
  }
}


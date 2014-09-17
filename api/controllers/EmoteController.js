/**
 * EmoteController
 *
 * @description :: Server-side logic for managing emotes
 * @help        :: See http://links.sailsjs.org/docs/controllers
 */

var fs = require('fs')
var fsp_extra = require('fs-promise')
var rmrf = require('rimraf-glob')
var path = require('path')
var image_size = require('image-size')
var Q = require('q')

Q.longStackSupport = true;

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
var create_emote = function(canonical_name, emote_dict, names, tags) {
    emote_dict.canonical_name = canonical_name
    return Emote.create(emote_dict)
    .then( function(emote) {
        
        var names_promises = names.map( function(name) {
            // Note: We don't use findOrCreate here so it fails if it already exist. We shall not override any existing names.
            return Name.create(
                {
                    name: name,
                    emote: emote.id,
                }
            )
        })
        
        var tags_promises = tags.map( function(tag) {
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
        
        return Q.allSettled( [].concat(names_promises, tags_promises) ) // I don't really care if setting the tags or names succeed.
        .then(function(results) {return emote} )
    })
}

// This function updates the record in the database.
// It does not do any file operations.
var update_emote = function(canonical_name, emote_dict, names, tags) {
    return Emote.findOne({
            where: {
                canonical_name: canonical_name,
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
                    canonical_name: canonical_name,
                }
            },
            emote_dict)
        .then(function(results) {
            updated_emote = results[0]
            
            // I kinda need the populated fields, but Emote.update()
            // Does not support chaining .populate()
            // So we must launch a new query
            return Emote.findOne({
                    where: {
                        canonical_name: canonical_name,
                    }
                })
            .populate('names')
            .populate('tags')
        })
    })
    .then( function(emote) {
        
        var new_names_dict = {}
        names.forEach(function(value, index, arr) {
            new_names_dict[value] = true
        })
        
        var old_names = array_name_picker(emote.names)
        var old_names_dict = {}
        old_names.forEach(function(value, index, arr) {
            old_names_dict[value] = true
            
            if (!new_names_dict[value]) {
                emote.names.remove(value)
            }
        })
        
        var names_promises = names.map( function(name) {
            // Note: We don't use findOrCreate here so it fails if it already exist. We shall not override any existing names.
            if(!old_names_dict[name]) {
                return Name.findOrCreate(
                    {
                        where: {
                            name: name,
                        }
                    },
                    {
                        name: name,
                    }
                )
                .then( function(name) {
                    if(!name.emote)
                        emote.names.add(name)
                })
            }
        })
        
        var new_tags_dict = {}
        tags.forEach(function(value, index, arr) {
            new_tags_dict[value] = true
        })
        
        var old_tags = array_name_picker(emote.tags)
        var old_tags_dict = {}
        old_tags.forEach(function(value, index, arr) {
            old_tags_dict[value] = true
            
            if (!new_tags_dict[value]) {
                emote.tags.remove(value)
            }
        })
        var tags_promises = tags.map( function(tag) {
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
                    emote.tags.add(tag)
                })
                return promise;
            }
        })
        
        return Q.allSettled( [].concat(names_promises, tags_promises) ) // I don't really care if setting the tags or names succeed.
        .then(function(results) {return emote.save()} )                        // So we don't check the resulting promises here.
        .then(function() {
            return Emote.findOne({
                    where: {
                        canonical_name: canonical_name,
                    }
                })
            .populate('names')
            .populate('tags')
        })
    })
}

var submit_emote = function(emote_unsafe, files, update) {
    var emote_dict = {}
    
    var canonical_name = emote_unsafe.canonical_name
    var names = emote_unsafe.names
    var css_user = emote_unsafe.css
    var tags = emote_unsafe.tags
    var src = emote_unsafe.src
    
    canonical_name = canonical_name.trim() // More checking is required on canonical_name.
    if(src)
        src = src.trim()
        emote_dict.src = src
    
    var removeEmptyStrings = function(array_with_strings) {
        return array_with_strings.filter(function(s){return (""+s).trim() != ""})
    }
    
    if (!names)
        names = []
    
    if(!Array.isArray(names))
        names = [names]
    names = removeEmptyStrings(names)
    
    if (!update)
        names.push(canonical_name)
    
    // Remove duplicates
    names = names.filter(function(item, pos, self) {
        return self.indexOf(item) == pos;
    })
    
    if(!Array.isArray(tags))
        tags = [tags]
    tags = removeEmptyStrings(tags)
    
    if (!tags)
        tags = []
    
    // Remove duplicates
    tags = tags.filter(function(item, pos, self) {
        return self.indexOf(item) == pos;
    })
    
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
            emote_dict.single_image_extension = dimensions.type
            return dimensions.type
        })
        .then( function(type) {
            var promise = Q()
            if(update) {
                promise = promise.then(function() {
                    Q.nfcall(rmrf, emoticon_image_path + '.*')
                })
            }
            return promise.then(function() {
                return fsp_extra.move(emoticon_image.fd, emoticon_image_path+'.'+type)
            })
        })
    }
    else {
        base_image_promise = Q("Base image file unchanged");
    }
    
    if (emoticon_image_hover) {
        hover_image_promise = Q.nfcall(image_size, emoticon_image_hover.fd)
        .then( function(dimensions) {
            emote_dict["hover-width"] = dimensions.width
            emote_dict["hover-height"] = dimensions.height
            emote_dict.single_hover_image_extension = dimensions.type
            return dimensions.type
        })
        .then( function(type) {
            var promise = Q()
            if(update) {
                promise = promise.then(function() {
                    Q.nfcall(rmrf, emoticon_image_hover_path + '.*')
                })
            }
            return promise.then(function() {
                return fsp_extra.move(emoticon_image_hover.fd, emoticon_image_hover_path+'.'+type)
            })
        })
    }
    else {
        hover_image_promise = Q("Hover image file unchanged");
    }
    
    file_promise = Q.all( [base_image_promise, hover_image_promise] )
    
    return file_promise.then( function() {
        var database_promise = undefined
        if (update) {
            database_promise = update_emote(canonical_name, emote_dict, names, tags)
        }
        else {
            database_promise = create_emote(canonical_name, emote_dict, names, tags)
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
                        var canonical_name = external_emote.canonical
                        var names = external_emote.names
                        var tags = external_emote.tags
                        
                        if(!names)
                            names = []
                        
                        if(!tags)
                            tags = []
                        
                        emote_dict = {
                            height: external_emote.height,
                            width: external_emote.width,
                            "hover-width": external_emote["hover-width"],
                            "hover-height": external_emote["hover-height"],
                            img_animation: external_emote.img_animation,
                            single_image_extension: external_emote.single_image_extension,
                            single_hover_image_extension: external_emote.single_hover_image_extension,
                            src: external_emote.sr,
                            css: css,
                        }
                        
                        return Emote.findOne({
                                where: {
                                    canonical_name: canonical_name,
                                }
                            })
                        .then(function(emote) {
                            if(emote) {
                                sails.log.debug("Bulk import: Updating old emote: " + emote.id + " " + canonical_name )
                                // Consider re-using the 'emote' variable by passing in into the update_emote() function somehow.
                                return update_emote(canonical_name, emote_dict, names, tags)
                            }
                            else {
                                return create_emote(canonical_name, emote_dict, names, tags)
                                .then( function(emote) {
                                    sails.log.debug("Bulk import: Created new emote: " + emote.id + " " + canonical_name )
                                })
                            }
                        })
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
                    res.view( {emote:emote} )
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
                    canonical_name: id.trim(),
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
  },
  
  legacy_export: function (req,res) {
    Emote.find()
    .populate('names')
    .populate('tags')
    .then(function(emotes) {
        emotes = emotes.map(function(emote) {
            var image_server_prefix = 'http://localhost:1337/'
            
            var obj = {
                canonical: emote.canonical_name,
                "background-image": image_server_prefix + emote.canonical_name,
                width: +emote.width,
                height: +emote.height,
                img_animation: emote.img_animation,
                single_image_extension: emote.single_image_extension,
                sr: emote.src,
                names: array_name_picker(emote.names),
                tags: array_name_picker(emote.tags),
            }
            
            // TODO: Tuck on css to the object.
            
            if (emote['hover-width']) {
                obj["hover-background-position"] = image_server_prefix + emote.canonical_name + '_hover'
                obj['single_hover_image_extension'] = emote.single_hover_image_extension
                obj['hover-width'] = +emote['hover-width']
                obj['hover-height'] = +emote['hover-height']
            }
            
            return obj
        })
        res.json(emotes)
    })
    .catch(function(err) {
        res.status(500);
        res.view('emote/error', {error:err} );
    })
    .done()
  },
}


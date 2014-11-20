/**
 * EmoteController
 *
 * @description :: Server-side logic for managing emotes
 * @help        :: See http://links.sailsjs.org/docs/controllers
 */

var path = require('path')

var fsp = require('fs-promise')
var fsp_extra = require('fs-promise')
var rmrf = require('rimraf-glob')
var image_size = require('image-size')
var Promise = require("bluebird")

var image_sizeAsync = Promise.promisify(image_size)
var rmrfAsync = Promise.promisify(rmrf)

var validate_canonical_name = require('./lib/validate_canonical_name')
var listdir = require('./lib/listdir')

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
        
        return Promise.settle( [].concat(names_promises, tags_promises) ) // I don't really care if setting the tags or names succeed.
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
        if (!emote)
            throw new Error("Could not find a emote with canonical_name: "+canonical_name)
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
            var updated_emote = results[0]
            
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
        
        var old_names_dict = {}
        emote.names.forEach(function(old_name, index, arr) {
            var value = old_name.name
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
        
        var old_tags_dict = {}
        emote.tags.forEach(function(old_tag, index, arr) {
            var value = old_tag.name
            old_tags_dict[value] = true
            
            if (!new_tags_dict[value]) {
                emote.tags.remove(old_tag.id)
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
        
        return Promise.settle( [].concat(names_promises, tags_promises) ) // I don't really care if setting the tags or names succeed.
        .then(function(results) {return emote.save()} )                        // So we don't check the resulting promises here.
    })
}

// The promise returned from submit_emote() will resolve with the updated/created
// emote object. But the associations will not be populated.
// The user argument is optional.
var submit_emote = function(emote_unsafe, emoticon_image, emoticon_hover_image, update, user) {
    var emote_dict = {}
    
    var canonical_name = validate_canonical_name(emote_unsafe.canonical_name)
    var names = emote_unsafe.names
    var css_user = emote_unsafe.css
    var tags = emote_unsafe.tags
    var src = emote_unsafe.src
    var alt_text = emote_unsafe.alt_text
    var remove_hover = emote_unsafe.remove_hover
    
    if(alt_text)
        alt_text = alt_text.trim()
    else
        alt_text = null
    emote_dict.alt_text = alt_text
    
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
        var css_arr = undefined
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
    
    if(user)
    {
        if(update)
        {
            emote_dict.updated_by = user.id
        }
        else
        {
            emote_dict.created_by = user.id
        }
    }
    
    if(remove_hover && emoticon_hover_image) {
        throw new Error("You are trying to remove a hover AND are trying to replace it. Do one or the other, not both.")
    }
    
    if(remove_hover)
    {
        // The hover image does not need to be removed.
        // It may actually cause trouble for clients who still try to fetch
        // the old hover image.
        
        emote_dict["has_hover"] = false
        emote_dict["hover_width"] = null
        emote_dict["hover_height"] = null
        emote_dict.single_hover_image_extension = null
    }
    
    var emoticon_image_path = path.join.apply(path, ["emoticons", "uploaded"].concat(canonical_name.split('/')))
    var emoticon_hover_image_path = emoticon_image_path + '_hover'
    
    var file_promise = undefined
    var base_image_promise = undefined
    var hover_image_promise = undefined
    
    if(!emoticon_image && !update)
    {
        return Promise.reject(new Error("A emoticon must have a base image"))
    }
    
    if (emoticon_image) {
        base_image_promise = image_sizeAsync(emoticon_image.fd)
        .then( function(dimensions) {
            if( sails.config.emote_server.allowed_extensions.join(' ').toLowerCase().indexOf(dimensions.type.toLowerCase()) == -1 )
            {
                throw new Error(dimensions.type + "is not a allowed file type")
            }
            
            emote_dict.width = +dimensions.width
            if(isNaN(emote_dict.width))
                emote_dict.width = null
            emote_dict.height = +dimensions.height
            if(isNaN(emote_dict.height))
                emote_dict.height = null
            emote_dict.single_image_extension = dimensions.type
            return dimensions.type
        })
        .then( function(type) {
            var promise = Promise.resolve()
            if(update) {
                promise = promise.then(function() {
                    return rmrfAsync(emoticon_image_path + '.*')
                })
            }
            return promise.then(function() {
                return fsp_extra.move(emoticon_image.fd, emoticon_image_path+'.'+type)
            })
        })
    }
    else {
        base_image_promise = Promise.resolve("Base image file unchanged");
    }
    
    if (emoticon_hover_image) {
        hover_image_promise = image_sizeAsync(emoticon_hover_image.fd)
        .then( function(dimensions) {
            if( sails.config.emote_server.allowed_extensions.join(' ').toLowerCase().indexOf(dimensions.type.toLowerCase()) == -1 )
            {
                throw new Error(dimensions.type + "is not a allowed file type")
            }
            
            emote_dict["has_hover"] = true
            emote_dict["hover_width"] = +dimensions.width
            if(isNaN(emote_dict["hover_width"]))
                emote_dict["hover_width"] = null
            emote_dict["hover_height"] = +dimensions.height
            if(isNaN(emote_dict["hover_height"]))
                emote_dict["hover_height"] = null
            emote_dict.single_hover_image_extension = dimensions.type
            return dimensions.type
        })
        .then( function(type) {
            var promise = Promise.resolve()
            if(update) {
                promise = promise.then(function() {
                    return rmrfAsync(emoticon_hover_image_path + '.*')
                })
            }
            return promise.then(function() {
                return fsp_extra.move(emoticon_hover_image.fd, emoticon_hover_image_path+'.'+type)
            })
        })
    }
    else {
        hover_image_promise = Promise.resolve("Hover image file unchanged");
    }
    
    file_promise = Promise.all( [base_image_promise, hover_image_promise] )
    
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

// Wrapped in a promise candy
// submit_emote() can throw exceptions.
// But we like to handle them in promise rejection handler instead of try/catch
// So we do this!
var wrapped_submit_emote = function(emote_unsafe, emoticon_image, emoticon_hover_image, update, user) {
    return Promise.resolve()
    .then(function () {
        return submit_emote(emote_unsafe, emoticon_image, emoticon_hover_image, update, user)
    })
}

var upload_promise = function(req, field_name) {
    
    return new Promise(function (resolve, reject) {
        req.file(field_name).upload(function (err, files) {
            if (err) {
                reject(new Error(err))
            } else {
                resolve(files)
            }
        })
    });
}

// id can me a canonical name or a database specific numeric id.
var queryEmoteById = function(id) {
    var query;
    if (isNaN(+id)) {
        // id is a canonical name.
        query = Emote.findOne({
            where: {
                canonical_name: id.trim(),
            }
        })
    }
    else {
        // id is a numeric id.
        id = Math.floor(+id)
        query = Emote.findOne({
            where: {
                id: id,
            }
        })
    }
    return query;
}

var allowed_to_edit = function(user, canonical_name) {
    var allowed = false
    
    var startsWith = function(str, substr) {
        return str.indexOf(substr) == 0;
    }
    
    user.emote_subdirs.forEach(function(dir){
        if(startsWith(canonical_name, dir))
            allowed = true
    })
    return allowed
}
            
module.exports = {

  bulk_upload: function(req, res) {
    
    if(req.is('multipart/form-data')) {
        
        upload_promise(req, 'json_emote_file')
        .then(function(files) {
            var file_path;
            if(files.length == 0) {
                file_path = path.join("reddit_emote_scraper", "output", "emotes_metadata.min.json")
            }
            else {
                file_path = files[0].fd
            }
            return fsp.readFile( file_path, { encoding : 'utf-8', flag: 'r' })
        })
        .then(function(text) {
            var external_emotes = JSON.parse(text)
            return external_emotes
        })
        .then(function(external_emotes) {
            res.json({
                    msg:"Processing " + external_emotes.length + " emotes in background"
            })
            return external_emotes
        }, function(err) {
            res.status(500)
            res.view('emote/error', {error:err} )
        })
        .then(function(external_emotes) {
            sails.log.debug("Bulk import: Processing " + external_emotes.length + " emotes")
            
            var result = Promise.resolve()
            var created = 0
            var updated = 0
            external_emotes.forEach( function(external_emote) {
                // We process the emotes in some order so the database adapter does not get overloaded.
                // Processing everything at the same time causes disruption in other services this web server provides.
                result = result.then( function() {
                    var css = null
                    var canonical_name = external_emote.canonical
                    var names = external_emote.names
                    var tags = external_emote.tags
                    
                    if(!names)
                        names = []
                    
                    if(!tags)
                        tags = []
                    
                    var single_image_extension = 'png'
                    if(external_emote.single_image_extension)
                        single_image_extension = external_emote.single_image_extension
                    
                    var has_hover = false
                    if(external_emote["has_hover"])
                        has_hover = true
                    
                    var single_hover_image_extension = null
                    if(has_hover) {
                        if(external_emote.single_hover_image_extension)
                            single_hover_image_extension = external_emote.single_hover_image_extension
                        else
                            single_hover_image_extension = 'png'
                    }
                    
                    var emote_dict = {
                        height: external_emote.height,
                        width: external_emote.width,
                        has_hover: has_hover,
                        hover_width: external_emote["hover-width"],
                        hover_height: external_emote["hover-height"],
                        img_animation: external_emote.img_animation,
                        single_image_extension: single_image_extension,
                        single_hover_image_extension: single_hover_image_extension,
                        src: 'https://www.reddit.com/r/'+external_emote.sr+'/',
                        css: css,
                    }
                    
                    return [canonical_name, emote_dict, names, tags]
                })
                .spread( function(canonical_name, emote_dict, names, tags) {
                    
                    // First the image files are copied from the reddit_emote_scraper image
                    // directory to a the server's image directory.
                    // Then we update/create the emote in the database.
                    
                    var emoticon_image_path_original = path.join.apply(path, ["reddit_emote_scraper", "output"].concat(canonical_name.split('/')))
                    var emoticon_image_path = path.join.apply(path, ["emoticons", "uploaded"].concat(canonical_name.split('/')))
                    
                    return rmrfAsync(emoticon_image_path + '.*')
                    .then(function() {
                        return fsp_extra.copy(  emoticon_image_path_original+'.'+emote_dict.single_image_extension,
                                                emoticon_image_path+'.'+emote_dict.single_image_extension)
                    })
                    .then(function() {
                        
                        if(emote_dict.has_hover)
                        {
                           var emoticon_hover_image_path_original = path.join.apply(path, ["reddit_emote_scraper", "output"].concat((canonical_name+'_hover').split('/')))
                           var emoticon_hover_image_path = path.join.apply(path, ["emoticons", "uploaded"].concat((canonical_name+'_hover').split('/')))

                            return rmrfAsync(emoticon_hover_image_path + '.*')
                            .then(function() {
                                return fsp_extra.copy(  emoticon_hover_image_path_original+'.'+emote_dict.single_hover_image_extension,
                                                        emoticon_hover_image_path+'.'+emote_dict.single_hover_image_extension)
                            })
                        }
                    })
                    .then(function(){
                        return Emote.findOne({
                            where: {
                                canonical_name: canonical_name,
                            }
                        })
                    })
                    .then(function(emote) {
                        if(emote) {
                            updated++
                            sails.log.debug("Bulk import: Updating old emote: " + emote.id + " " + canonical_name )
                            // Consider re-using the 'emote' variable by passing in into the update_emote() function somehow.
                            return update_emote(canonical_name, emote_dict, names, tags)
                        }
                        else {
                            created++
                            return create_emote(canonical_name, emote_dict, names, tags)
                            .then( function(emote) {
                                sails.log.debug("Bulk import: Created new emote: " + emote.id + " " + canonical_name )
                            })
                        }
                    })
                })
            })
            return result.then(function(){
                        return {
                            processed:external_emotes.length,
                            created:created,
                            updated:updated,
                        }
                    })
        })
        .then(function(stats) {
            sails.log.debug("Bulk import: Done -> ", stats)
        })
        .catch(function(err) {
            sails.log.error("Bulk import: Error -> ", err)
        })
        .done()
    }
    else
    {
      res.view();
    }
  },
  
  submit: function (req,res) {
    if(req.is('multipart/form-data')) {
        
        try {
            var canonical_name = validate_canonical_name(req.body.canonical_name)
            if (!allowed_to_edit(req.user, canonical_name))
            {
                res.status(403);
                res.view('emote/error', {error:"You do not have permission to submit emotes in this directory, check your privilege"} )
                return
            }
        }
        catch(err) {
            res.status(400);
            res.view('emote/error', {error:err} );
            return
        }
        
        Promise.all([
            upload_promise(req, 'emoticon_image'),
            upload_promise(req, 'emoticon_hover_image'),
        ])
        .then(function(results) {
            var emoticon_image = results[0][0]
            var emoticon_hover_image = results[1][0]
            
            return wrapped_submit_emote(req.body,
                                        emoticon_image,
                                        emoticon_hover_image,
                                        false,
                                        req.user)
        })
        .then( function(emote) {
            res.redirect('emote/edit?id='+emote.canonical_name)
        })
        .catch( function(err) {
            res.serverError(err)
        })
        .done()
    }
    else
    {
      res.view();
    }
  },
  
  // Yes, we use the filesystem hierachy to store data.
  // Reason: The canonical names are like a hierachy and the filesystem is a hierachy.
  // Special care should be taken ignore files not related to emoticons using
  // blacklists and/or whitelists.
  ls: function (req,res) {
    var req_relative_loc_unsafe = req.query.loc
    var req_relative_loc = ""

    var dirs = [
        "emoticons/uploaded".replace("/",path.sep),
        "emoticons/processed".replace("/",path.sep),
    ]

    if (req_relative_loc_unsafe) {
        req_relative_loc = req_relative_loc_unsafe.trim().replace(".", "").replace("\\","")
        req_relative_loc = req_relative_loc.replace(/\/+$/, ""); // Remove trailing slashes
        req_relative_loc = req_relative_loc.replace(/^\/+/, ""); // Remove starting slashes
        req_relative_loc = req_relative_loc + '/'
    }
      
    var canonical_names = []
    var canonical_name_present = {}

    var combined_dirs = []
    var combined_dir_present = {}

    Promise.all( dirs.map( function(dir) {

        return listdir(path.join(dir, req_relative_loc.replace("/",path.sep)))
        .then(function(results) {
            results.files.forEach(function(file) {
                var ext = path.extname(file)
                var basename = path.basename(file, ext)

                if (file.toLowerCase().indexOf('_hover') === -1) {
                    if ( ext !== "" &&
                        sails.config.emote_server.allowed_extensions.join(' ').toLowerCase().indexOf(ext.toLowerCase()) !== -1) {
                        if(!canonical_name_present[req_relative_loc + basename]) {
                            canonical_name_present[req_relative_loc + basename] = true
                            canonical_names.push(req_relative_loc + basename)
                        }
                    }
                }
            })

            results.dirs.forEach(function(dir) {

                if (dir.toLowerCase().indexOf('_exploded') === -1) {
                    if(!combined_dir_present[req_relative_loc + dir]) {
                        combined_dir_present[req_relative_loc + dir] = true
                        combined_dirs.push(req_relative_loc + dir)
                    }
                }

            })
        }, function(err) {
            // Emoticons are stored in multiple directories.
            // 
            // Some emoticons do not exist in emoticons/processed.
            // So we get ENOENT errors here. But they still exist in
            // emoticons/uploaded. So we will swallow the execptions here.
            // 
            // sails.log.debug("Ignoring list directory error", err)
        })
    }))
    .then(function() {
        var locals = {
            canonical_names:canonical_names,
            dirs:combined_dirs,
        }

        if (req.wantsJSON) {
            res.json(locals)
        } else {
            res.view(locals)
        }
    })
    .done()
  },
  
  view: function (req,res) {
        var id = req.query.id
        
        if (!id) {
            res.status(400);
            res.view('emote/error', {error:"You must supply a valid id. A canonical name or a numeric id."} );
            return
        }
        
        queryEmoteById(id)
        .populate('names')
        .populate('tags')
        .then( function(emote) {
            if (emote === undefined)
                throw new Error("Could not find a emote with id: "+id)
            return emote
        })
        .then(function(emote) {
            res.view( {emote:emote} )
        })
        .catch(function(err) {
            res.status(400)
            res.view('emote/error', {error:err} )
        })
        .done()
  },
  
  edit: function (req,res) {
    if(req.is('multipart/form-data')) {
        
        try {
            var canonical_name = validate_canonical_name(req.body.canonical_name)
            if (!allowed_to_edit(req.user, canonical_name))
            {
                res.status(403);
                res.view('emote/error', {error:"You do not have permission to edit this emote"} )
                return
            }
        }
        catch(err) {
            res.status(400);
            res.view('emote/error', {error:err} );
            return
        }
        
        Promise.all([
            upload_promise(req, 'emoticon_image'),
            upload_promise(req, 'emoticon_hover_image'),
        ])
        .then(function(results) {
            var emoticon_image = results[0][0]
            var emoticon_hover_image = results[1][0]
            
            return wrapped_submit_emote(req.body,
                            emoticon_image,
                            emoticon_hover_image,
                            true,
                            req.user)
        })
        .then(function(emote) {
            return Emote.findOne({
                where: {
                    canonical_name: emote.canonical_name,
                }
            })
            .populate('names')
            .populate('tags')
        })
        .then( function(emote) {
            res.view( {emote:emote, allowed_to_edit:true} )
        })
        .catch( function(err) {
            res.serverError(err);
        })
        .done()
    }
    else
    {
        var id = req.query.id
        
        if (!id) {
            res.status(400);
            res.view('emote/error', {error:"You must supply a valid id. A canonical name or a numeric id."} )
            return
        }
        
        queryEmoteById(id)
        .populate('names')
        .populate('tags')
        .then( function(emote) {
            if (!emote)
                throw new Error("Could not find a emote with id: "+id)
            return emote
        })
        .then(function(emote) {
            res.view( {emote:emote, allowed_to_edit:allowed_to_edit(req.user, emote.canonical_name)} )
        })
        .catch(function(err) {
            res.status(400)
            res.view('emote/error', {error:err} )
        })
        .done()
    }
  },
}


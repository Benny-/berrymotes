
module.exports = {
    emote_server: {
        
        // This can be used if the images are hosted somewhere else (CDN).
        // TODO: Make a api so clients can know this value.
        image_url_prefix: '/emote/img/uploaded/',
        
        // Putting a extension in allowed_extensions does not magically make it work.
        // Some processing is done on input files, the dimensions are extracted.
        // A extension can't be used if the dimension extraction module can't extract
        // a dimension.
        // https://github.com/netroy/image-size is used to extract dimensions.
        allowed_extensions: ['gif', 'jpg', 'jpeg', 'png', 'tiff', 'webp', 'svg'],
        
        // Newly created users can create emotes with the following prefixes:
        default_whitelist_emote_subdirs: ['mls/volatile/'],
    },
}

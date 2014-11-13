
module.exports = {
    emote_server: {
        image_url_prefix: 'http://localhost:1337/',
        // Putting a extension in allowed_extensions does not magically make it work.
        // Some processing is done on input files, the dimensions are extracted.
        // A extension can't be used if the dimension extraction module can't extract
        // a dimension.
        // https://github.com/netroy/image-size is used to extract dimensions.
        allowed_extensions: ['.gif', '.jpg', '.jpeg', '.png', '.tiff', '.webp', '.svg'],
    },
}

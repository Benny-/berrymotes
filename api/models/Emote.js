/**
* Emote.js
*
* @description :: TODO: You might write a short summary of how this model works and what it represents here.
* @docs        :: http://sailsjs.org/#!documentation/models
*/

module.exports = {

    attributes: {
        
        canonical_name: {
            type: 'STRING',
            unique: true,
            notNull: true,
            required: true,
        },
        
        // Can be 'png', 'gif', 'svg', ect..
        single_image_extension: {
            type: 'STRING',
            notNull: true,
            required: true,
        },
        // True if the base image is a animation.
        // This attribute is not reliable
        img_animation: {
            type: 'BOOLEAN',
            defaultsTo: false,
            notNull: true,
        },
        // The width/width for the base image in pixels.
        // Special case if single_image_extension == 'svg':
        // The width/height will be null if the svg does not have a pixel size.
        width: {
            type: 'INTEGER',
            required: true,
        },
        height: {
            type: 'INTEGER',
            required: true,
        },
        // The optional width/width for the base image in length units.
        // This can be a absolute or a relative length unit.
        // https://developer.mozilla.org/en-US/docs/Web/CSS/length#Units
        display_width: {
            type: 'STRING',
            size: 8,
            maxLength: 8,
            alphanumeric: true,
        },
        display_height: {
            type: 'STRING',
            size: 8,
            maxLength: 8,
            alphanumeric: true,
        },
        
        // All hover attributes must be ignored if has_hover is set to false.
        has_hover: {
            type: 'BOOLEAN',
            defaultsTo: false,
            notNull: true,
        },
        single_hover_image_extension: 'STRING',
        // True if the hover image is a animation.
        // This attribute is not reliable
        hover_animation: {
            type: 'BOOLEAN',
            defaultsTo: false,
            notNull: true,
        },
        // The height/width for the optional hover image in pixels.
        // Special case if single_hover_image_extension == 'svg':
        // The width/height will be null if the svg does not have a pixel size.
        hover_width: {
            type: 'INTEGER',
        },
        hover_height: {
            type: 'INTEGER',
        },
        // The optional width/width for the hover image in length units.
        // This can be a absolute or a relative length unit.
        // https://developer.mozilla.org/en-US/docs/Web/CSS/length#Units
        hover_display_width: {
            type: 'STRING',
            size: 8,
            maxLength: 8,
            alphanumeric: true,
        },
        hover_display_height: {
            type: 'STRING',
            size: 8,
            maxLength: 8,
            alphanumeric: true,
        },
        
        // The origin of this emote. Is always a hyperlink.
        src: {
            type:  'STRING',
            url: {},
        },
        alt_text: 'STRING',
        
        created_by: {
            model: 'User',
        },
        
        updated_by: {
            model: 'User',
        },
        
        css: {
            type: 'JSON',
        },
        
        tags: {
            collection: 'tag',
            via: 'emotes',
            index: true,
            dominant: true,
        },
        
        names: {
            collection: 'name',
            via: 'emote',
        },
    }
};


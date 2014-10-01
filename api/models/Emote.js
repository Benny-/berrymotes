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
        
        width: {
            type: 'INT',
            notNull: true,
            required: true,
        },
        height: {
            type: 'INT',
            notNull: true,
            required: true,
        },
        "has_hover": {
            type: 'BOOLEAN',
            defaultsTo: false,
            notNull: true,
        },
        "hover-width": 'INT',
        "hover-height": 'INT',
        img_animation: {
            type: 'BOOLEAN',
            defaultsTo: false,
            notNull: true,
        },
        hover_animation: {
            type: 'BOOLEAN',
            defaultsTo: false,
            notNull: true,
        },
        single_image_extension: {
            type: 'STRING',
            notNull: true,
            required: true,
        },
        single_hover_image_extension: 'STRING',
        src: 'STRING',
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


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
            required: true,
        },
        
        width: {
            type: 'INT',
            required: true,
        },
        height: {
            type: 'INT',
            required: true,
        },
        "hover-width": 'INT',
        "hover-height": 'INT',
        img_animation: 'BOOLEAN',
        hover_animation: 'BOOLEAN',
        single_image_extension: 'STRING',
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
            dominant: true,
        },
        
        names: {
            collection: 'name',
            via: 'emote',
        },
    }
};


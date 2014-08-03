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
            index: true,
            unique: true,
        },
        
        width: 'INT',
        height: 'INT',
        "hover-width": 'INT',
        "hover-height": 'INT',
        img_animation: 'BOOLEAN',
        hover_animation: 'BOOLEAN',
        single_image_extension: 'STRING',
        single_hover_image_extension: 'STRING',
        src: 'STRING',
        
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


/**
* Emote.js
*
* @description :: TODO: You might write a short summary of how this model works and what it represents here.
* @docs        :: http://sailsjs.org/#!documentation/models
*/

module.exports = {

  attributes: {

    width_px: 'INT',
    height_px: 'INT',
    animated: 'BOOLEAN',
    file_type: 'STRING',
    creation_date: 'DATETIME',
    updated_date: 'DATETIME',
    canonical_name: {
        type: 'STRING',
        unique: true,
    },

    css: {
      collection: 'css',
      via: 'emote',
    },

    tags: {
      collection: 'tag',
      via: 'emote',
      dominant: true,
    },

  }
};


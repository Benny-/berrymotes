/**
* User.js
*
* @description :: TODO: You might write a short summary of how this model works and what it represents here.
* @docs        :: http://sailsjs.org/#!documentation/models
*/

module.exports = {

  schema: true,

  attributes: {
        username: {
            type: 'STRING',
            unique: true,
            notNull: true,
            required: true,
        },
        email: {
            type: 'STRING',
            unique: true,
            notNull: true,
            required: true,
        },
        role: {
            type: 'INTEGER',
            defaultsTo: 0, // Zero is a newly registered user. '1' is site admin.
            notNull: true,
            required: true,
        },
        // A whitelist of directories.
        // A user may only edit/submit in these directories.
        emote_subdirs: {
            type: 'JSON',
            defaultsTo: sails.config.emote_server.default_whitelist_emote_subdirs,
            notNull: true,
            array: true,
        },
        passports : {
            collection: 'Passport',
            via: 'user'
        },
  },
};


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
            required: true,
        },
        email: {
            type: 'STRING',
            unique: true,
            required: true,
        },
        role: {
            type: 'INT',
            defaultsTo: 0, // Zero is for a newly registered user. '1' is for site admin.
            required: true,
        },
        passports : {
            collection: 'Passport',
            via: 'user'
        },
  },
};


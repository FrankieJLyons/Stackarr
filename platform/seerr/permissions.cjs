// Stackarr's Seerr 3.5.0 security backport. Apache-2.0; upstream Seerr is MIT.
'use strict';
const ADMIN = 2, MANAGE_USERS = 8;
const has = (user, permission) => !!user && ((user.permissions & ADMIN) !== 0 || (user.permissions & permission) === permission);
const canEdit = (actor, target) => !!actor && !!target &&
  (actor.id === 1 || actor.id === target.id || (target.id !== 1 && !has(target, ADMIN) &&
    (has(actor, ADMIN) || (target.permissions & ~actor.permissions) === 0)));
const canChange = (actor, target, permissions) =>
  Number.isSafeInteger(permissions) && permissions >= 0 && permissions <= 0x7fffffff &&
  has(actor, MANAGE_USERS) && !!target && target.id !== 1 && actor.id !== target.id &&
  canEdit(actor, target) && (actor.id === 1 ||
    (!(permissions & ADMIN) && (has(actor, ADMIN) || (permissions & ~actor.permissions) === 0)));

// All reads, authorization checks and writes share one transaction. In particular,
// a mixed batch fails before saving any user. Reload the actor for live revocation.
async function change(actorId, ids, permissions, username) {
  const source = require('../datasource').default;
  const { User } = require('../entity/User');
  const { In } = require('typeorm');
  const fail = (status) => { throw { status, message: status === 404 ? 'User not found.' : 'User permission change denied.' }; };
  if (!Array.isArray(ids) || !ids.length || ids.some(id => !Number.isSafeInteger(id) || id <= 0)) fail(400);
  ids = [...new Set(ids)];
  return source.transaction(async manager => {
    const repository = manager.getRepository(User);
    const actor = await repository.findOne({ where: { id: actorId } });
    if (!has(actor, MANAGE_USERS)) fail(403);
    const users = await repository.find({ where: { id: In(ids) } });
    if (users.length !== ids.length) fail(404);
    if (users.some(user => !canChange(actor, user, permissions))) fail(403);
    for (const user of users) {
      user.permissions = permissions;
      if (username !== undefined) user.username = username;
    }
    return repository.save(users);
  });
}
module.exports = { canEdit, canChange, change };

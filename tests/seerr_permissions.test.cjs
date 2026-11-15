'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { canEdit, canChange } = require('../platform/seerr/permissions.cjs');
const owner = { id: 1, permissions: 2 };
const admin = { id: 2, permissions: 2 };
const manager = { id: 3, permissions: 40 };
const guest = { id: 4, permissions: 32 };
for (const target of [owner, admin, manager]) {
  test('manager cannot change protected target ' + target.id, () => {
    for (const permissions of [0, 2, 8, 32, 40, 0x7fffffff]) assert.equal(canChange(manager, target, permissions), false);
  });
}
test('delegation cannot add capabilities the manager lacks', () => {
  for (const permissions of [2, 4, 16, 34, 36, 0x4000]) assert.equal(canChange(manager, guest, permissions), false);
  for (const permissions of [0, 8, 32, 40]) assert.equal(canChange(manager, guest, permissions), true);
});
test('owner can manage others including existing admins, but cannot demote self', () => {
  assert.equal(canChange(owner, admin, 32), true);
  assert.equal(canChange(owner, guest, 2), true);
  assert.equal(canChange(owner, owner, 0), false);
});
test('nonowner admin cannot demote peer, grant admin or edit own permissions', () => {
  assert.equal(canChange(admin, { id: 5, permissions: 2 }, 32), false);
  assert.equal(canChange(admin, guest, 2), false);
  assert.equal(canChange(admin, guest, 16384), true);
  assert.equal(canChange(admin, admin, 32), false);
});
test('profile ownership is independent of changing own role', () => {
  assert.equal(canEdit(manager, manager), true);
  assert.equal(canEdit(manager, guest), true);
  assert.equal(canEdit(manager, owner), false);
  assert.equal(canEdit(manager, admin), false);
  assert.equal(canEdit(owner, admin), true);
  assert.equal(canEdit(admin, admin), true);
});
test('more privileged nonadmin accounts cannot be taken over through profile or role edits', () => {
  for (const permissions of [4, 16, 16384, 44]) {
    const target = { id: 6, permissions };
    assert.equal(canEdit(manager, target), false);
    assert.equal(canChange(manager, target, 32), false);
    assert.equal(canEdit(owner, target), true);
    assert.equal(canEdit(admin, target), true);
  }
});
test('malformed permission values and missing identities fail closed', () => {
  for (const permissions of [-1, 1.5, '2', null, undefined, NaN, 0x80000000])
    assert.equal(canChange(owner, guest, permissions), false);
  assert.equal(canChange(undefined, guest, 32), false);
  assert.equal(canChange(owner, undefined, 32), false);
  assert.equal(canChange(guest, manager, 32), false);
});

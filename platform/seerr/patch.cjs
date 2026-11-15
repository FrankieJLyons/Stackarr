// Apply only to the exact reviewed upstream files; never guess at new releases.
'use strict';
const fs = require('node:fs'), crypto = require('node:crypto');
const path = require('node:path');
const root = process.argv[2] || '/app';
const lock = require('./upstream.lock.json');
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const files = {};
for (const [name, expected] of Object.entries(lock.files)) {
  const value = fs.readFileSync(path.join(root, 'dist', name), 'utf8');
  if (sha(value) !== expected) throw Error('Unreviewed Seerr input: ' + name);
  files[name] = value;
}
const replace = (value, start, end, replacement) => {
  const first = value.indexOf(start), last = value.indexOf(end, first + start.length);
  if (first < 0 || last < 0 || value.indexOf(start, first + 1) >= 0) throw Error('Patch boundary changed');
  return value.slice(0, first) + replacement + '\n' + value.slice(last);
};
files['routes/user/index.js'] = replace(files['routes/user/index.js'],
  "router.put('/',", "router.delete('/:id',", `
const stackarrPermissions = require('../../lib/stackarrUserPermissions');
router.put('/', (0, auth_1.isAuthenticated)(permissions_1.Permission.MANAGE_USERS), async (req, res, next) => {
  try {
    const users = await stackarrPermissions.change(req.user?.id, req.body.ids, req.body.permissions);
    return res.status(200).json(users.map(user => user.filter()));
  } catch (error) { next({ status: error.status || 500, message: 'User permission change denied.' }); }
});
router.put('/:id', (0, auth_1.isAuthenticated)(permissions_1.Permission.MANAGE_USERS), async (req, res, next) => {
  try {
    const [user] = await stackarrPermissions.change(req.user?.id, [Number(req.params.id)], req.body.permissions, req.body.username);
    return res.status(200).json(user.filter());
  } catch (error) { next({ status: error.status || 500, message: 'User permission change denied.' }); }
});`);
files['routes/user/usersettings.js'] = replace(files['routes/user/usersettings.js'],
  "userSettingsRoutes.post('/permissions',", 'exports.default = userSettingsRoutes;', `
userSettingsRoutes.post('/permissions', (0, auth_1.isAuthenticated)(permissions_1.Permission.MANAGE_USERS), async (req, res, next) => {
  try {
    const [user] = await require('../../lib/stackarrUserPermissions').change(req.user?.id, [Number(req.params.id)], req.body.permissions);
    return res.status(200).json({ permissions: user.permissions });
  } catch (error) { next({ status: error.status || 500, message: 'User permission change denied.' }); }
});`);
// Protect email, password, notifications and push subscription mutations too.
let profile = files['utils/profileMiddleware.js'];
const marker = 'const authMiddleware = (req, res, next) => {';
if (profile.split(marker).length !== 2) throw Error('Profile middleware changed');
profile = profile.replace(marker, 'const authMiddleware = async (req, res, next) => {');
const finish = '        next();\n    };\n    return authMiddleware;';
if (profile.split(finish).length !== 2) throw Error('Profile middleware boundary changed');
profile = profile.replace(finish, `
        if (!['GET', 'HEAD', 'OPTIONS'].includes(req.method)) {
          try {
            const target = await require('../datasource').getRepository(require('../entity/User').User).findOne({ where: { id: Number(req.params.id) } });
            if (!target) return next({ status: 404, message: 'User not found.' });
            if (!require('../lib/stackarrUserPermissions').canEdit(req.user, target))
              return next({ status: 403, message: 'User account change denied.' });
          } catch { return next({ status: 500, message: 'User account change denied.' }); }
        }
        next();
    };
    return authMiddleware;`);
files['utils/profileMiddleware.js'] = profile;
const receipt = { base: lock.base, version: lock.version, before: lock.files, after: {} };
const sources = require('./setup-patch.cjs')(root, files);
receipt.sourcesBefore = lock.sources;
for (const [name, value] of Object.entries(sources)) {
  fs.writeFileSync(path.join(root, name), value);
  receipt.after[name] = sha(value);
}
for (const [name, value] of Object.entries(files)) {
  fs.writeFileSync(path.join(root, 'dist', name), value);
  receipt.after[name] = sha(value);
}
const helper = fs.readFileSync(path.join(__dirname, 'permissions.cjs'));
fs.writeFileSync(path.join(root, 'dist/lib/stackarrUserPermissions.js'), helper);
receipt.after['lib/stackarrUserPermissions.js'] = sha(helper);
const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
if (pkg.version !== '3.5.0') throw Error('Upstream version changed');
pkg.version = lock.version;
fs.writeFileSync(path.join(root, 'package.json'), JSON.stringify(pkg, null, 2) + '\n');
fs.writeFileSync(path.join(__dirname, 'receipt.json'), JSON.stringify(receipt, null, 2) + '\n');

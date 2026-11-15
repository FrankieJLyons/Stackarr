const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function fixture(storage = null) {
  const nodes = Object.fromEntries(['setup-selected-folder', 'setup-selected-folder-path',
    'setup-selected-folder-path-details', 'setup-folder'].map(id => [id, {textContent: '', value: '', hidden: true}]));
  const context = vm.createContext({
    setupStorage: storage,
    setupDeployment: {folder_picker: true, folder_browser: true},
    escape: value => String(value).replace(/[&<>"']/g, character =>
      ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character])),
    select: (label, id, selected) => `<select id="${id}" aria-label="${label}" data-selected="${selected}"></select>`,
    document: {getElementById: id => nodes[id]},
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../stackarr/static/setup_choices.js'), 'utf8'), context);
  const controls = vm.runInContext('({setupFolderLabel, setupMediaFolder, setupLibraryChoices, updateSetupFolderDisplay})', context);
  return {nodes, controls};
}

test('folder labels support drives, shares, root folders and trailing separators', () => {
  const {controls} = fixture();
  for (const [folder, label] of [
    ['C:\\Users\\Owner\\Media', 'Media'], ['D:\\Media\\', 'Media'], ['C:\\', 'C: drive'],
    ['\\\\nas\\share\\Movies\\', 'Movies'], ['\\\\nas\\share\\', 'share'],
    ['/mnt/media/', 'media'], ['/', 'Root folder'], ['', 'Choose your media folder'],
  ]) assert.equal(controls.setupFolderLabel(folder), label, folder);
});

test('a selected path stays exact and escaped while its long parents are collapsed', () => {
  const {controls} = fixture();
  const folder = 'C:\\An extremely long parent & shared drive\\Family "media" <movies>';
  const html = controls.setupMediaFolder({data_root: folder});
  assert.match(html, /id="setup-selected-folder">Family &quot;media&quot; &lt;movies&gt;<\/strong>/);
  assert.match(html, /<details class="setup-folder-details" id="setup-selected-folder-path-details"><summary>See folder location<\/summary>/);
  assert.ok(html.includes('id="setup-selected-folder-path">C:\\An extremely long parent &amp; shared drive\\Family &quot;media&quot; &lt;movies&gt;</p>'));
  assert.ok(html.includes('id="setup-folder" value="C:\\An extremely long parent &amp; shared drive\\Family &quot;media&quot; &lt;movies&gt;"'));
  assert.ok(!html.includes('<movies>'));
  assert.ok(!html.includes('setup-selected-folder-path-details" open'));
});

test('a folder selection updates the compact and exact labels without changing its saved value', () => {
  const {nodes, controls} = fixture();
  nodes['setup-folder'].value = 'unchanged draft path';
  const selected = '\\\\nas\\Media & Movies\\';
  controls.updateSetupFolderDisplay(selected);
  assert.equal(nodes['setup-selected-folder'].textContent, 'Media & Movies');
  assert.equal(nodes['setup-selected-folder-path'].textContent, selected);
  assert.equal(nodes['setup-selected-folder-path-details'].hidden, false);
  assert.equal(nodes['setup-folder'].value, 'unchanged draft path');
  controls.updateSetupFolderDisplay('');
  assert.equal(nodes['setup-selected-folder'].textContent, 'Choose your media folder');
  assert.equal(nodes['setup-selected-folder-path-details'].hidden, true);
});

test('movie and TV locations are collapsed and their quality choices remain independent', () => {
  const {controls} = fixture({folders: [
    {app: '/data/media/movies', host: 'D:\\Existing library\\Movies'},
    {app: '/data/media/tv', host: '\\\\nas\\TV Archive'},
  ]});
  const html = controls.setupLibraryChoices({apps: ['radarr', 'sonarr'], data_root: 'C:\\Media', choices: {
    radarr: {mode: 'install', quality_profile: 'Ultra-HD'},
    sonarr: {mode: 'install', quality_profile: 'SD'},
  }});
  assert.match(html, /<summary>See Movies folder location<\/summary><p class="setup-library-path">D:\\Existing library\\Movies/);
  assert.match(html, /<summary>See TV folder location<\/summary><p class="setup-library-path">\\\\nas\\TV Archive/);
  assert.match(html, /id="setup-quality-radarr" aria-label="Movies request quality" data-selected="Ultra-HD"/);
  assert.match(html, /id="setup-quality-sonarr" aria-label="TV request quality" data-selected="other"/);
  assert.match(html, /id="setup-quality-other-sonarr" aria-label="TV other quality" data-selected="SD"/);
  assert.ok(!html.includes('<details class="setup-folder-details" open'));
});

test('empty folders do not invent locations and connected libraries retain existing quality settings', () => {
  const {controls} = fixture();
  const empty = controls.setupMediaFolder({data_root: ''});
  assert.match(empty, /id="setup-selected-folder-path-details" hidden/);
  const html = controls.setupLibraryChoices({apps: ['plex', 'sonarr'], choices: {
    plex: {mode: 'install'}, sonarr: {mode: 'connect', quality_profile: 'Ultra-HD'},
  }});
  assert.match(html, /Choose a media folder above/);
  assert.ok(!html.includes('id="setup-quality-sonarr"'));
  assert.ok(!html.includes('C:\\'));
});

'use strict';
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const lock = require('./upstream.lock.json');
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const once = (text, before, after) => {
  if (text.split(before).length !== 2) throw Error('Seerr setup patch boundary changed');
  return text.replace(before, after);
};

module.exports = function setupPatch(root, files) {
  const sources = {};
  for (const [name, expected] of Object.entries(lock.sources)) {
    const data = fs.readFileSync(path.join(root, name), 'utf8');
    if (sha(data) !== expected) throw Error('Unreviewed Seerr setup input: ' + name);
    sources[name] = data;
  }
  files['api/plexapi.js'] = once(files['api/plexapi.js'],
    'return response.MediaContainer.Directory;',
    `const container = response.MediaContainer;
        if (!container || typeof container !== 'object') throw new Error('Invalid Plex library response');
        if (container.Directory === undefined && container.size === 0) return [];
        if (!Array.isArray(container.Directory)) throw new Error('Invalid Plex library list');
        return container.Directory;`);
  sources['src/utils/plex.ts'] = fs.readFileSync(path.join(__dirname, 'plex-login.ts'), 'utf8');
  sources['src/pages/login/plex/loading.tsx'] = fs.readFileSync(path.join(__dirname, 'plex-callback.tsx'), 'utf8');
  sources['src/hooks/usePlexLogin.ts'] = once(sources['src/hooks/usePlexLogin.ts'],
    'setTimeout(() => getPlexLogin(), 1500);', 'getPlexLogin();');
  sources['src/hooks/usePlexLogin.ts'] = once(sources['src/hooks/usePlexLogin.ts'],
    'const [loading, setLoading] = useState(false);',
    "const [loading, setLoading] = useState(false);\n  const [error, setError] = useState('');");
  sources['src/hooks/usePlexLogin.ts'] = once(sources['src/hooks/usePlexLogin.ts'],
    'setLoading(true);', "setLoading(true);\n    setError('');");
  sources['src/hooks/usePlexLogin.ts'] = once(sources['src/hooks/usePlexLogin.ts'],
    'if (onError) {', "setError('Plex sign-in could not start. Check your connection and try again.');\n      if (onError) {");
  sources['src/hooks/usePlexLogin.ts'] = once(sources['src/hooks/usePlexLogin.ts'],
    'return { loading, login };', 'return { loading, login, error };');
  let button = sources['src/components/Login/PlexLoginButton.tsx'];
  button = once(button, 'const { loading, login }', 'const { loading, login, error }');
  button = once(button, '  return (\n    <Button', '  return (\n    <>\n    <Button');
  button = once(button, '    </Button>\n  );', '    </Button>\n    {error && <p role="alert" className="mt-3 text-sm text-red-300">{error}</p>}\n    </>\n  );');
  sources['src/components/Login/PlexLoginButton.tsx'] = button;
  let screen = sources['src/components/Settings/SettingsPlex.tsx'];
  screen = once(screen, 'isSetupSettings?: boolean;', 'isSetupSettings?: boolean;\n  onEmptyLibrariesConfirmed?: (empty: boolean) => void;');
  screen = once(screen, '({ isSetupSettings }: SettingsPlexProps)', '({ isSetupSettings, onEmptyLibrariesConfirmed }: SettingsPlexProps)');
  screen = once(screen, 'const [isSyncing, setIsSyncing] = useState(false);',
    'const [isSyncing, setIsSyncing] = useState(false);\n  const [emptyLibraries, setEmptyLibraries] = useState(false);');
  screen = once(screen, "    try {\n      await axios.post('/api/v1/settings/plex/library/sync');",
    `    setEmptyLibraries(false);
    onEmptyLibrariesConfirmed?.(false);
    try {
      const response = await axios.post('/api/v1/settings/plex/library/sync');
      if (!Array.isArray(response.data)) throw new Error('Invalid library response');
      await revalidate();
      setEmptyLibraries(response.data.length === 0);
      onEmptyLibrariesConfirmed?.(response.data.length === 0);`);
  screen = once(screen, 'onSubmit={async (values) => {\n          let toastId:',
    'onSubmit={async (values) => {\n          setEmptyLibraries(false);\n          onEmptyLibrariesConfirmed?.(false);\n          let toastId:');
  screen = once(screen, '            syncLibraries();', '            await syncLibraries();');
  screen = once(screen, '<ul className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 sm:gap-6 lg:grid-cols-4">',
    `<div role="status" className="mt-4">
          {emptyLibraries && (
            <p>Plex is connected and has no movie or TV libraries yet. You can continue setup without libraries. To watch your files later, add a Movies or TV Shows library in Plex using /data/media/movies or /data/media/tv, then return here, sync libraries and enable them. Requests will not be marked available until a library is connected.</p>
          )}
        </div>
        <ul className="mt-6 grid grid-cols-1 gap-5 sm:grid-cols-2 sm:gap-6 lg:grid-cols-4">`);
  sources['src/components/Settings/SettingsPlex.tsx'] = screen;
  let setup = sources['src/components/Setup/index.tsx'];
  setup = once(setup, "import useSettings from '@app/hooks/useSettings';",
    "import useSettings from '@app/hooks/useSettings';\nimport { useUser } from '@app/hooks/useUser';");
  setup = once(setup, 'const intl = useIntl();', 'const intl = useIntl();\n  const { user } = useUser();');
  setup = once(setup, '      if (currentStep < 3) {',
    '      if (!user) {\n        setCurrentStep(2);\n      } else if (currentStep < 3) {');
  setup = once(setup, '    settings.currentSettings.mediaServerType,', '    user,\n    settings.currentSettings.mediaServerType,');
  setup = once(setup, 'const [isUpdating, setIsUpdating] = useState(false);',
    'const [isUpdating, setIsUpdating] = useState(false);\n  const [emptyPlexConfirmed, setEmptyPlexConfirmed] = useState(false);');
  setup = once(setup, 'disabled={!mediaServerSettingsComplete}',
    'disabled={!mediaServerSettingsComplete && !(mediaServerType === MediaServerType.PLEX && emptyPlexConfirmed && mediaServerSettings?.libraries?.length === 0)}');
  setup = once(setup, '<SettingsPlex isSetupSettings />', '<SettingsPlex isSetupSettings onEmptyLibrariesConfirmed={setEmptyPlexConfirmed} />');
  setup = once(setup, '{intl.formatMessage(messages.continue)}',
    "{mediaServerType === MediaServerType.PLEX && emptyPlexConfirmed && !mediaServerSettingsComplete ? 'Continue without libraries' : intl.formatMessage(messages.continue)}");
  sources['src/components/Setup/index.tsx'] = setup;
  return sources;
};

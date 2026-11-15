'use strict';
const helpTopics={
 setup:{title:'What happens during this setup preview?',steps:[
  'Choose only the apps you want. You do not need a complete media stack, and unselected apps stay hidden.',
  'Save & continue keeps your choices for later. The local launcher offers reviewed Docker installation. Saving a draft or downloading a plan does not install anything.',
  'Use Find selected apps on this computer for local connection hints. A responding service is not automatically adopted.',
  'For an existing app, open Settings → App connections, enable it, enter its address and credentials, then save and test the connection.'
 ]},
 storage:{title:'How should I choose a folder?',steps:[
  'Use a dedicated folder on the computer that will run the media apps. Do not choose an entire drive.',
  'The layout preview shows where movies, series and downloads will go. Apps see the shared folder as /data.',
  'The plan gives Plex read-only media access. Download and import apps need permission to write.',
  'Planning does not create folders. The installation review lists missing folders to create and new Arr library settings. Existing files stay in place; network-share access still needs testing.'
 ]},
 settings:{title:'How do I connect my apps safely?',steps:[
  'For newly installed Plex and Seerr, complete their account setup, then choose Finish connecting. Stackarr handles the connection details privately; no key or token copying is needed.',
  'Enable only the apps you use. Choose Connect to an existing app and enter the address reachable from Stackarr.',
  'If your browser uses a different address, enter it in Browser address. API keys and passwords are stored on the Stackarr server.',
  'Blank credential fields keep saved credentials. Save settings, then Test saved connections. Each app reports its own result.',
  'Preview app connections before applying them. This only offers supported add-only links; existing app entries are preserved.',
  'Seerr keeps ownership of household requests and permissions. Finish its media-server and Arr setup in Seerr first.'
 ]},
 health:{title:'What should I do when something is unavailable?',steps:[
  'Open Connection details to distinguish rejected credentials from an address, network or response problem.',
  'Check the app address and credentials in Settings → App connections, then refresh status. Other working apps remain visible.',
  'Stale rows are the last successful result, not a fresh reading. A dash means unavailable or unconfigured data, not zero activity.',
  'Recent operations shows waiting, running and completed checks. Notification delivery shows attempts and failures.',
  'Download a support bundle in Settings → Maintenance for technical help. It omits addresses, paths, media titles and credentials; review it before sharing.'
 ]},
 backups:{title:'What does restoring a backup change?',steps:[
  'Docker app backups include encrypted app databases, logins and settings. Selected apps stop briefly, then return to their previous running state.',
  'Review restore verifies the snapshot before replacing app configuration. A safety snapshot is saved first; failed extraction attempts rollback. Media and downloads stay untouched.',
  'Redacted Stackarr settings backups are separate drafts. Preview opens Settings; nothing changes until Save settings. These drafts exclude credentials and app databases.',
  'Keep the controller data directory and secrets.key to decrypt Docker backups. Copy your app-data directory and media separately to another disk; same-disk snapshots do not protect against disk failure.'
 ]},
 network:{title:'Can other people on my network use this?',steps:[
  'The preview starts on this computer only. It does not open firewall ports or expose apps to the internet.',
  'Open Start Stackarr → Home network & recovery to prepare local HTTPS. Trust its public certificate once on each device; browsers sharing that device’s trust store reuse it.',
  'Do not forward router ports to this preview. Keep the gateway running while other devices connect. Local HTTPS does not require a domain or cloud account. Retain the gateway folder and its private keys on the server.'
 ]}
};
function helpPanel(topic){const help=helpTopics[topic];return `<details class="panel"><summary>${escape(help.title)}</summary><ol>${help.steps.map(step=>`<li>${escape(step)}</li>`).join('')}</ol></details>`;}

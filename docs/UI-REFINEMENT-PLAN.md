# Control room refinement

## Scope and order

1. Make blue the default on sign-in, branding and every workspace. Add saved
   blue/red/yellow/green/orange/purple presets with light, dark and device modes.
   Replace the password checkbox with an accessible eye button.
2. Put Setup, Settings and Help in the navigation. Use Apps as the single catalog
   for supported installers. Show configured apps there as configured; never offer
   an accidental second installation. Selecting an available app opens its setup.
3. Make Setup an ordered checklist from the server's existing readiness evidence.
   Every unfinished task gets an action or an explicit prerequisite. Show only the
   task being worked on. Keep installation and connection reviews before writes.
   Plex can work alone; Sonarr/Radarr can manage existing libraries. Automatic
   downloads need a download client and sources, not necessarily a specific brand.
4. Keep overview app cards in one place, with role labels, consistent connection
   status/details and buttons that open the relevant settings. Put external
   ownership beside status, remove redundant managed labels, align action rows,
   centre the health count and add configurable operating-signal cards.
5. Put app connection preferences in Settings, actionable wiring/account tools in
   Setup, and explanatory material in Help. Keep operational results as toasts and
   a durable history table in Health, rather than overview log paragraphs.
6. Investigate Plex's rejected credential without replacing its account, token or
   settings automatically. Provide an explicit reconnect route and report what
   still requires the owner's Plex sign-in.
7. Verify the supported install/connect flow, dependency blockers, every theme,
   desktop/phone layouts, expanded results, partial failures, saved preferences
   and upgrade preservation. Build and apply a matching dashboard/controller only
   after those checks; retain app containers, settings, media and rollback data.

## Acceptance

- A new or returning user can find setup, change appearance, fix a connection and
  start a supported app setup from the visible navigation.
- Missing data remains unavailable, not zero. Health and overview use the same
  labels, timestamps and repair actions.
- No app is installed or reconfigured merely by selecting it in the catalog.
- A minimal installation does not have to enable every optional companion.
- App containers and stored credentials survive the UI upgrade unchanged.

## Implemented

- Six validated colour presets, light/dark/device modes, public appearance-only
  settings for sign-in, themed branding and the accessible password eye.
- One Apps catalog, per-app setup dialog, reviewed install/connect wizard and
  direct connection-settings navigation after connecting an existing app.
- Ordered setup tasks, prerequisite messages, focused task workspaces and Help.
- Shared connection status/details/repair controls, role-based app groups,
  aligned card actions, and app operation history in Health with toast feedback.
- Twelve selectable overview cards, including capacity read only from a verified
  owned media mount. Unavailable data stays unknown; active downloads exclude
  seeding items.
- Browser coverage includes the install review/apply boundary, the real API
  connect flow, saved palette/widget preferences, all twelve colour/mode pairs,
  blocked tasks, repair navigation, and responsive layouts.
- Plex inspection found no active server token in its own preferences. Its
  account is preserved; the owner must complete Plex sign-in before reconnecting.

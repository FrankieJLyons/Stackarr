'use strict';
function browserAppUrl(key){const app=state.config.integrations[key],port=app?.port||state.catalog?.[key]?.port;return state.network?.mode==='home-network'?(state.network.app_links?.[key]||''):(app?.browser_url||app?.url||(port?`http://localhost:${port}`:''));}
function appLink(url){return url?`<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">Open app ↗</a>`:'<span class="hint">Home-network link not configured</span>';}

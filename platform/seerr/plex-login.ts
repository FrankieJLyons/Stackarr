import axios from 'axios';

// Keep only the short-lived PIN receipt in this tab. Account tokens never go in
// URLs or browser storage. Plex validates the PIN; Seerr validates the account.
const storageKey = 'stackarr.plex-signin.v1';
const lifetime = 15 * 60 * 1000;
interface PendingLogin {
  id: number;
  client: string;
  expires: number;
  returnPath: '/setup' | '/login';
}

class PlexOAuth {
  public preparePopup(): void {
    // Retain the hook contract; navigation uses this tab, including in webviews.
  }

  public async login(client: string): Promise<string> {
    if (!client) throw new Error('Plex is not ready. Reload this page and try again.');
    sessionStorage.removeItem(storageKey);
    const response = await axios.post('https://plex.tv/api/v2/pins?strong=true', undefined, {
      headers: this.headers(client), timeout: 15000,
    });
    const { id, code } = response.data;
    if (!Number.isSafeInteger(id) || id <= 0 || typeof code !== 'string' || !code) {
      throw new Error('Plex could not start sign-in. Please try again.');
    }
    const pending: PendingLogin = {
      id, client, expires: Date.now() + lifetime,
      returnPath: window.location.pathname === '/setup' ? '/setup' : '/login',
    };
    sessionStorage.setItem(storageKey, JSON.stringify(pending));
    const params = new URLSearchParams({
      clientID: client, code,
      'context[device][product]': 'Seerr',
      forwardUrl: `${window.location.origin}/login/plex/loading`,
    });
    window.location.assign(`https://app.plex.tv/auth/#!?${params}`);
    // The callback page owns completion after navigation.
    return new Promise<string>(() => {});
  }

  public async resume(signal: AbortSignal): Promise<string> {
    const pending = this.pending();
    if (!pending) throw new Error('This sign-in has expired. Return to Seerr and try again.');
    while (!signal.aborted && Date.now() < pending.expires) {
      const response = await axios.get(`https://plex.tv/api/v2/pins/${pending.id}`, {
        headers: this.headers(pending.client), timeout: 15000, signal,
      });
      if (typeof response.data?.authToken === 'string' && response.data.authToken) {
        return response.data.authToken;
      }
      const expiresAt = Date.parse(response.data?.expiresAt);
      if (Number.isFinite(expiresAt) && Date.now() >= expiresAt) break;
      await new Promise<void>((resolve) => {
        const finish = () => { clearTimeout(timer); signal.removeEventListener('abort', finish); resolve(); };
        const timer = setTimeout(finish, 1000);
        signal.addEventListener('abort', finish, { once: true });
      });
    }
    throw new Error('Plex sign-in expired or was cancelled. Please try again.');
  }

  public returnPath(): '/setup' | '/login' {
    return this.pending()?.returnPath ?? '/login';
  }

  public clear(): void { sessionStorage.removeItem(storageKey); }

  private pending(): PendingLogin | undefined {
    try {
      const value = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
      if (value && Number.isSafeInteger(value.id) && value.id > 0 &&
          typeof value.client === 'string' && value.client.length > 0 && value.client.length <= 512 &&
          Number.isFinite(value.expires) && value.expires > Date.now() && value.expires <= Date.now() + lifetime &&
          ['/setup', '/login'].includes(value.returnPath)) return value;
    } catch { /* Missing, corrupt or unavailable tab storage cannot authorize login. */ }
    return undefined;
  }

  private headers(client: string): Record<string, string> {
    return { Accept: 'application/json', 'X-Plex-Product': 'Seerr',
      'X-Plex-Client-Identifier': client, 'X-Plex-Version': 'Plex OAuth' };
  }
}

export default PlexOAuth;

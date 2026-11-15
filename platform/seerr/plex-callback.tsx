import Button from '@app/components/Common/Button';
import PlexOAuth from '@app/utils/plex';
import axios from 'axios';
import { useEffect, useState } from 'react';

const PlexLoading = () => {
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    const oauth = new PlexOAuth();
    const returnPath = oauth.returnPath();
    const complete = async () => {
      try {
        const authToken = await oauth.resume(controller.signal);
        if (controller.signal.aborted) return;
        await axios.post('/api/v1/auth/plex', { authToken }, { signal: controller.signal, timeout: 30000 });
        await axios.get('/api/v1/auth/me', { signal: controller.signal, timeout: 15000 });
        if (controller.signal.aborted) return;
        oauth.clear();
        window.location.replace(returnPath);
      } catch {
        if (!controller.signal.aborted) {
          oauth.clear();
          setError('Sign-in could not finish. Return to Seerr and try again with the Plex account that owns this server.');
        }
      }
    };
    complete();
    return () => controller.abort();
  }, []);
  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-900 p-6 text-white">
      <div className="w-full max-w-md rounded-md bg-gray-800 p-6">
        <h1 className="mb-4 text-xl font-bold">Finishing Plex sign-in</h1>
        <p role={error ? 'alert' : 'status'} className="mb-6">
          {error || 'Waiting for Plex authorization. You will return to Seerr automatically.'}
        </p>
        <Button onClick={() => { new PlexOAuth().clear(); window.location.replace('/login'); }}>
          {error ? 'Return to Seerr' : 'Cancel sign-in'}
        </Button>
      </div>
    </main>
  );
};

export default PlexLoading;

"""Visible UI check for production account/source controls; all actions simulated."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tools.source_setup_browser_check import FIXTURE

ROOT=Path(__file__).resolve().parents[1]
journey=(ROOT/'stackarr/static/setup_journey.js').read_text(encoding='utf-8')
FOCUS=journey[journey.index('function focusSetupTarget('):journey.index('async function setupJourneyStep(')]
EXTRA=r'''
const baseApi=api;
api=async(path,method,body)=>{
 if(path.startsWith('deployments/')&&path.endsWith('/accounts/review'))return {review_token:'fixture-review-'.repeat(2),notice:'Prepare Movies and TV in the selected media folder, connect requests with the existing Plex sign-in, and connect the new download apps. Existing accounts and libraries are preserved.',libraries:[{name:'Movies',state:'create'},{name:'TV Shows',state:'create'}]};
 if(path==='accounts/apply'){sharing=1;return {state:'connected',message:'Movies, TV and your requests account are connected. Continue to your content source, then find a title in Home.'};}
 if(path==='refresh')return {};
 return baseApi(path,method,body);
};
const load=async()=>{};
const on=(id,fn)=>{const button=document.getElementById(id);if(button)button.onclick=async()=>{button.disabled=true;try{await fn();}catch(e){announce(e.message);}finally{button.disabled=false;}};};
state.config.integrations.plex.browser_url='/plex-sign-in';
state.config.integrations.seerr={enabled:true};state.credentials.push('seerr');
const install={id:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',apps:['plex','seerr','radarr','sonarr','prowlarr','qbittorrent']};
const links=()=>[{app:'plex',url:'/plex-sign-in'},{app:'seerr',url:'/requests-sign-in'}];
render=()=>{
 state.dirty=state.appDirty=state.indexerDirty=false;
 root.innerHTML='<p class="banner">DESIGN CHECK Â· Sign-in, account and source actions here are simulated. No Plex account, media or installation is changed.</p><h1>Letâ€™s get ready for movie night.</h1>'+(state.accountResult?accountSetupResult()+indexerPanel():accountSetupSteps([install],links));
 bindAccountSetup();if(state.accountResult)bindSetupExtras();
 root.querySelectorAll('input,select').forEach(input=>{if(input.dataset.setupControl!=='navigation')input.addEventListener('input',()=>{state.dirty=state.indexerDirty=true;});});
};
render();
'''


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def do_GET(self):
        if self.path.startswith('/static/'):
            target=ROOT/'stackarr'/self.path.lstrip('/')
            if target.is_file() and target.suffix in ('.css','.js','.svg','.png'):
                data=target.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type','text/css' if target.suffix=='.css' else 'application/javascript' if target.suffix=='.js' else 'image/svg+xml' if target.suffix=='.svg' else 'image/png')
                self.end_headers()
                self.wfile.write(data)
                return
        if self.path in ('/plex-sign-in','/requests-sign-in'):
            body='<h1>Sign-in demonstration</h1><p>No real account is connected here. Return to the setup tab to continue the design check.</p>'
        else:
            body='<main id="root" class="content"></main><div id="announcer" role="status"></div><script>'+FIXTURE+'</script><script src="/static/setup_extras.js"></script><script>'+FOCUS+'</script><script src="/static/setup_accounts.js"></script><script>'+EXTRA+'</script>'
        data=('<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Stackarr setup design check</title><link rel="stylesheet" href="/static/theme.css"><link rel="stylesheet" href="/static/app.css"><link rel="stylesheet" href="/static/home.css"></head><body>'+body+'</body></html>').encode()
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(data)


if __name__=='__main__':
    ThreadingHTTPServer(('127.0.0.4',29360),Handler).serve_forever()

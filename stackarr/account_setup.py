"""Reviewed Plex libraries and initial Seerr setup for receipt-owned installations.

The user signs into Plex itself. Its existing token is read privately from the
exact owned container; no browser token entry, server claim or main discovery.
"""
import asyncio
import hashlib
import json
import re
from urllib.parse import urlsplit

import httpx

from .adapters import require_write
from .deployment_check import load_receipt
from .finish_setup import read_settings
from .integrations import IntegrationError, bounded_response
from .store import Conflict

LIBRARIES = (
    {'name':'Movies','type':'movie','agent':'tv.plex.agents.movie','scanner':'Plex Movie','location':'/data/media/movies'},
    {'name':'TV Shows','type':'show','agent':'tv.plex.agents.series','scanner':'Plex TV Series','location':'/data/media/tv'},
)


class AccountSetupError(ValueError):
    pass


def signature(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def wiring_scope(store, ports, credentials=None, local_targets=None):
    """Only automatically wire endpoints and credentials still bound to this install."""
    revision, config = store.config()
    allowed = set()
    for key, port in ports.items():
        app = config.integrations[key]
        base = f'http://127.0.0.1:{port}' if local_targets is not None else f'http://host.docker.internal:{port}'
        peer = f'http://{key}:{local_targets[key]}' if local_targets is not None else base
        if (app.enabled and app.url == base and app.peer_url == peer
                and (credentials is None or store.secret(key) == credentials.get(key))):
            allowed.add(key)
    return revision, allowed


async def call(client, method, base, path, *, headers=None, body=None, params=None):
    try:
        response, content = await bounded_response(client,method,base+path,headers=headers,
            **({'json':body} if body is not None else {}), **({'params':params} if params else {}))
        response.raise_for_status()
        return json.loads(content) if content else {}
    except (httpx.HTTPError, ValueError, IntegrationError):
        raise AccountSetupError('Account setup could not finish. Check your Plex sign-in and the installed apps, then review this step again. Saved settings stay in place.') from None


async def plex(client, base, token):
    headers={'Accept':'application/json','X-Plex-Token':token}
    identity=await call(client,'GET',base,'/identity',headers=headers)
    info=identity.get('MediaContainer')
    if not isinstance(info,dict) or info.get('claimed') not in (True,1) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}',str(info.get('machineIdentifier',''))):
        raise AccountSetupError('Sign in to Plex and finish its server setup first. You can skip adding libraries there; Stackarr will prepare Movies and TV in the next step.')
    response=await call(client,'GET',base,'/library/sections',headers=headers)
    container=response.get('MediaContainer')
    if not isinstance(container,dict):
        raise AccountSetupError('Plex libraries could not be checked. Try this step again.')
    sections=container.get('Directory',[] if container.get('size')==0 else None)
    if not isinstance(sections,list) or any(not isinstance(row,dict) for row in sections):
        raise AccountSetupError('Plex libraries could not be checked. Try this step again.')
    libraries=[]
    for row in sections:
        locations=row.get('Location',[])
        if not isinstance(locations,list) or any(not isinstance(location,dict) for location in locations):
            raise AccountSetupError('Plex returned unexpected library folders. Check its libraries before continuing.')
        for location in locations:
            if not isinstance(location.get('path'),str) or not re.fullmatch(r'[0-9]{1,18}',str(row.get('key',''))):
                raise AccountSetupError('Plex returned unexpected library folders. Check its libraries before continuing.')
            libraries.append({'id':str(row['key']),'type':row.get('type'),'path':location['path']})
    return info['machineIdentifier'], sorted(libraries,key=lambda row:(row['id'],row['path']))


class Accounts:
    def __init__(self, deployments, transport=None):
        self.deployments,self.store,self.transport=deployments,deployments.store,transport

    @staticmethod
    def scan_key(identity, machine, path):
        return signature({'installation':identity,'machine':machine,'path':path})

    def scan_pending(self, identity, machine, path):
        with self.store.db() as db:
            row=db.execute("SELECT event FROM audit WHERE app=? AND event IN (?,?) ORDER BY id DESC LIMIT 1",
                (self.scan_key(identity,machine,path),'account-setup.initial-scan-pending','account-setup.initial-scan-started')).fetchone()
        return bool(row and row[0]=='account-setup.initial-scan-pending')

    async def review(self, identity):
        payload=await asyncio.to_thread(load_receipt,self.deployments,identity)
        if 'plex' not in payload['apps'] or self.deployments.context()!=payload['context']:
            raise AccountSetupError('Choose a Plex installation created by Stackarr on this computer.')
        revision,config=self.store.config()
        raw=await asyncio.to_thread(read_settings,self.deployments,identity,payload,'plex',config.integrations['plex'])
        if '<!DOCTYPE' in raw or '<!ENTITY' in raw:
            raise AccountSetupError('Plex settings could not be checked safely.')
        import xml.etree.ElementTree as ET
        try:
            preferences=ET.fromstring(raw).attrib
        except ET.ParseError:
            raise AccountSetupError('Wait for Plex to start, then try this step again.') from None
        token=preferences.get('PlexOnlineToken','')
        if not isinstance(token,str) or not re.fullmatch(r'[\x21-\x7e]{8,512}',token):
            raise AccountSetupError('Open Plex below and sign in first. Return here when its server setup is finished. No token or API key needs copying.')
        base=config.integrations['plex'].url
        peer=urlsplit(config.integrations['plex'].peer_url or base)
        if peer.path.rstrip('/'):
            raise AccountSetupError('This Plex address needs advanced connection setup. Existing requests settings were preserved.')
        async with httpx.AsyncClient(transport=self.transport,trust_env=False,follow_redirects=False,timeout=8) as client:
            machine,libraries=await plex(client,base,token)
            expected=preferences.get('ProcessedMachineIdentifier')
            if not expected or expected!=machine:
                raise AccountSetupError('The Plex server identity changed. Check this installation before continuing.')
            create=[]
            for library in LIBRARIES:
                matches=[row for row in libraries if row['path']==library['location']]
                if any(row['type']!=library['type'] for row in matches):
                    raise AccountSetupError('A Plex library uses the expected folder with a different media type. Review its libraries first; existing libraries were preserved.')
                if not matches:
                    create.append(library)
            seerr=None
            if 'seerr' in payload['apps'] and config.integrations['seerr'].enabled:
                settings=json.loads(await asyncio.to_thread(read_settings,self.deployments,identity,payload,'seerr',config.integrations['seerr']))
                if not isinstance(settings,dict) or any(not isinstance(settings.get(part,{}),dict) for part in ('main','public','plex')):
                    raise AccountSetupError('Requests settings could not be checked safely. Wait for the app to start, then review again.')
                key=settings.get('main',{}).get('apiKey')
                if not isinstance(key,str) or not re.fullmatch(r'[\x21-\x7e]{8,512}',key):
                    raise AccountSetupError('Wait for the requests app to finish starting, then check this step again.')
                initialized=settings.get('public',{}).get('initialized') is True
                server_type=settings.get('main',{}).get('mediaServerType')
                # Seerr 3.5 uses NOT_CONFIGURED=4; older imports may use 0.
                fresh=type(server_type) is int and server_type in (0,4) and not initialized
                if fresh:
                    remote=settings.get('plex') or {}
                else:
                    remote=await call(client,'GET',config.integrations['seerr'].url,'/api/v1/settings/plex',headers={'X-Api-Key':key})
                    # A partially completed setup can resume, but never replace a
                    # different requests owner with the signed-in Plex account.
                    owner=await call(client,'GET',config.integrations['seerr'].url,'/api/v1/user/1',headers={'X-Api-Key':key})
                    account=await call(client,'GET','https://plex.tv','/users/account.json',headers={'Accept':'application/json','X-Plex-Token':token})
                    plex_user=account.get('user')
                    if not isinstance(plex_user,dict) or type(owner.get('plexId')) is not int or owner['plexId']!=plex_user.get('id'):
                        raise AccountSetupError('The requests app belongs to another account. Its owner and settings were preserved. Open Seerr to review its account connection.')
                if not isinstance(remote,dict) or remote.get('machineId') and remote['machineId']!=machine:
                    raise AccountSetupError('Your requests app already uses a different Plex server. Its settings were preserved. Review that connection in Seerr before continuing.')
                seerr={'base':config.integrations['seerr'].url,'key':key,'initialized':initialized,'authenticate':fresh,
                       'settings_signature':signature(settings),'plex_signature':signature(remote)}
        if revision!=self.store.config()[0]:
            raise Conflict('Settings changed. Review account setup again.')
        initialize_paths=sorted({row['location'] for row in create}|{row['location'] for row in LIBRARIES
            if self.scan_pending(identity,machine,row['location'])})
        return {'id':identity,'apps':list(payload['apps']),'revision':revision,'machine':machine,'plex_base':base,'plex_key':token,
                'initialize_paths':initialize_paths,
                'libraries':libraries,'create':create,'seerr':seerr,'action':'account-setup',
                'receipt_signature':signature(payload)}

    @staticmethod
    def public(plan):
        return {'installation':plan['id'],'action':'account-setup','title':'Prepare watching and requests',
                'libraries':[{'name':row['name'],'state':'create' if row in plan['create'] else 'keep'} for row in LIBRARIES],
                'connect_requests':plan['seerr'] is not None,'apps':plan['apps'],
                'notice':'Prepare Movies and TV in your chosen media folder and initialize new libraries with a folder scan. Connect this installation’s requests app to the same Plex server using your existing Plex sign-in. Create missing connections between the new movie, TV, source and download apps, and enable automatic library refresh. Your Plex password stays with Plex; existing connections, libraries and other servers are preserved.'}

    async def apply(self, plan):
        require_write('plex','library.create')
        current=await self.review(plan['id'])
        if current!=plan:
            raise Conflict('Account or library settings changed. Review this step again before continuing.')
        async with httpx.AsyncClient(transport=self.transport,trust_env=False,follow_redirects=False,timeout=8) as client:
            for library in plan['create']:
                # Recheck immediately before each create; retries preserve successful work.
                machine,libraries=await plex(client,plan['plex_base'],plan['plex_key'])
                if self.store.config()[0]!=plan['revision'] or machine!=plan['machine']:
                    raise Conflict('Plex server changed. Review this step again.')
                if any(row['path']==library['location'] for row in libraries):
                    continue
                self.store.audit('account-setup.initial-scan-pending',self.scan_key(plan['id'],plan['machine'],library['location']))
                await call(client,'POST',plan['plex_base'],'/library/sections',
                    headers={'Accept':'application/json','X-Plex-Token':plan['plex_key']},
                    params=library|{'language':'en-GB'})
                self.store.audit('account-setup.library-created','plex')
            machine,libraries=await plex(client,plan['plex_base'],plan['plex_key'])
            wanted=[row for row in libraries if any(row['path']==library['location'] and row['type']==library['type'] for library in LIBRARIES)]
            if machine!=plan['machine'] or {row['type'] for row in wanted}!={'movie','show'}:
                raise AccountSetupError('Plex did not confirm both library folders. Review this step again; completed libraries stay in place.')
            # Start root discovery for new or interrupted library preparation.
            # Native post-import partial scanning needs separate verification.
            for path in plan['initialize_paths']:
                require_write('plex','library.scan')
                current_machine,current_libraries=await plex(client,plan['plex_base'],plan['plex_key'])
                if self.store.config()[0]!=plan['revision'] or current_machine!=plan['machine'] or current_libraries!=libraries:
                    raise Conflict('Plex libraries changed. Review their initial scan again.')
                matching=[row for row in wanted if row['path']==path]
                if len(matching)!=1:
                    raise AccountSetupError('The new library folder is ambiguous. Review its initial scan in Plex.')
                await call(client,'GET',plan['plex_base'],'/library/sections/'+matching[0]['id']+'/refresh',
                    headers={'Accept':'application/json','X-Plex-Token':plan['plex_key']})
                self.store.audit('account-setup.initial-scan-started',self.scan_key(plan['id'],plan['machine'],path))
            if self.store.config()[0]!=plan['revision']:
                raise Conflict('Settings changed during setup. Review this step again; completed libraries are kept.')
            target=plan['seerr']
            if target:
                require_write('seerr','initial-plex-setup.configure')
                base,key=target['base'],target['key']
                headers={'X-Api-Key':key}
                if target['authenticate']:
                    owner=await call(client,'POST',base,'/api/v1/auth/plex',body={'authToken':plan['plex_key']})
                    if owner.get('id')!=1:
                        raise AccountSetupError('This requests app already has another owner. Its settings were preserved. Review its account in Seerr before continuing.')
                peer=urlsplit(self.store.config()[1].integrations['plex'].peer_url or plan['plex_base'])
                settings={'ip':peer.hostname,'port':peer.port or (443 if peer.scheme=='https' else 80),'useSsl':peer.scheme=='https'}
                if peer.path.rstrip('/'):
                    raise AccountSetupError('This Plex address needs advanced connection setup. Existing requests settings were preserved.')
                await call(client,'POST',base,'/api/v1/settings/plex',headers=headers,body=settings)
                remote=await call(client,'POST',base,'/api/v1/settings/plex/library/sync',headers=headers)
                if not isinstance(remote,list):
                    raise AccountSetupError('Library syncing did not finish. Review this step again.')
                ids={row['id'] for row in wanted}
                available={str(row.get('id')) for row in remote if isinstance(row,dict)}
                if not ids<=available:
                    raise AccountSetupError('Requests cannot see both Plex libraries yet. Review this step again.')
                for library in wanted:
                    await call(client,'PUT',base,'/api/v1/settings/plex/library/'+library['id'],headers=headers,body={'enabled':True})
                if not target['initialized']:
                    await call(client,'POST',base,'/api/v1/settings/initialize',headers=headers)
                confirmed=await call(client,'GET',base,'/api/v1/settings/plex',headers=headers)
                if confirmed.get('machineId')!=machine or not ids<={str(row.get('id')) for row in confirmed.get('libraries',[]) if row.get('enabled') is True}:
                    raise AccountSetupError('The requests library connection could not be confirmed. Review it again before requesting a title.')
                self.store.audit('account-setup.requests-connected','seerr')
        return {'state':'connected','message':('Movies, TV and your requests account are connected. Continue to your content source, then find a title in Home.' if plan['seerr'] else 'Your Movies and TV libraries are ready. Open Home to watch in Plex.')}

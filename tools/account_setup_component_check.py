"""Native Seerr account/library component acceptance with a synthetic Plex protocol.

Only native Seerr APIs are certified here. The Plex protocol, account identity,
initial sign-in and deployment receipt are explicit fixtures. No Plex server is
started or claimed; no real token or main installation data is used.
"""
import asyncio
import json
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

import httpx

from stackarr import account_setup
from stackarr.account_setup import Accounts
from stackarr.store import Store
from tools import source_flow_check as source

ROOT=Path('test-results/accounts-source-20261020/native-r3').resolve()
PROJECT='stackarr-account-component-20261020'
MACHINE='stackarr-account-protocol-fixture'
TOKEN='fixture-plex'
NATIVE_SEERR_ID=''


def native_settings():
    return json.loads(source.command(['exec',NATIVE_SEERR_ID,'head','-c','131072','/app/config/settings.json']))


def write(name,value):
    (ROOT/name).write_text(json.dumps(value,indent=2),encoding='utf-8')


class Native(httpx.AsyncBaseTransport):
    async def handle_async_request(self,request):
        if request.url.host=='plex.tv':
            return httpx.Response(200,json={'user':{'id':71}},request=request)
        assert request.url.host=='127.0.0.1' and request.url.port in (43800,43805)
        async with httpx.AsyncClient(trust_env=False,timeout=15) as client:
            result=await client.request(request.method,str(request.url),headers=dict(request.headers),content=request.content)
            assert len(result.content)<1_000_000
            return httpx.Response(result.status_code,headers=dict(result.headers),content=result.content,request=request)


def ready(key=''):
    for attempt in range(60):
        try:
            response=httpx.get('http://127.0.0.1:43805/api/v1/'+('user/1' if key else 'status'),
                               headers={'X-Api-Key':key},trust_env=False,timeout=2)
            if response.is_success:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise AssertionError('Native Seerr component did not start')


async def verify():
    store=Store(ROOT/'host-state')
    revision,config=store.config()
    for key,port in (('plex',43800),('seerr',43805)):
        config.integrations[key].enabled=True
        config.integrations[key].url=f'http://127.0.0.1:{port}'
        config.integrations[key].peer_url='http://plex:8080' if key=='plex' else 'http://seerr:5055'
    store.save(config,revision)
    host=SimpleNamespace(store=store,context=lambda:{'name':'explicit-component-fixture'})
    payload={'apps':['plex','seerr'],'context':host.context()}
    original_load,original_read=account_setup.load_receipt,account_setup.read_settings
    account_setup.load_receipt=lambda *args:payload
    def settings(*args):
        return ('<Preferences ProcessedMachineIdentifier="'+MACHINE+'" PlexOnlineToken="'+TOKEN+'"/>' if args[3]=='plex'
                else json.dumps(native_settings()))
    account_setup.read_settings=settings
    try:
        service=Accounts(host,Native())
        plan=await service.review('a'*32)
        assert len(plan['create'])==2 and not plan['seerr']['authenticate']
        write('public-review.json',service.public(plan))
        result=await service.apply(plan)
        assert result['state']=='connected'
        settings=native_settings()
        assert settings['public']['initialized'] and settings['plex']['machineId']==MACHINE
        assert len(settings['plex']['libraries'])==2 and all(row['enabled'] for row in settings['plex']['libraries'])
        # Native Seerr must preserve unrelated settings during initial connection.
        assert settings['plex']['webAppUrl']=='https://app.plex.tv/desktop'
        repeat=await service.review('a'*32)
        assert not repeat['create']
        await service.apply(repeat)
        assert len(json.loads((ROOT/'plex-state/libraries.json').read_text()))==2
        write('native-component.json',{'passed':True,'native_seerr_setup_and_library_sync':True,'empty_library_handling':True,
            'idempotent_repeat':True,'protocol_and_receipt_fixtures':True,'synthetic_existing_owner_fixture':True,
            'real_plex_authentication_or_playback_tested':False,'main_untouched':True})
    finally:
        account_setup.load_receipt,account_setup.read_settings=original_load,original_read


def main():
    global NATIVE_SEERR_ID
    ROOT.mkdir(exist_ok=True)
    assert not (ROOT/'compose-private.json').exists(),'Use a fresh component output directory'
    source.preserved()
    config=ROOT/'seerr-config'
    protocol=ROOT/'plex-state'
    config.mkdir()
    protocol.mkdir()
    (protocol/'libraries.json').write_text('[]')
    image=json.loads(Path('stackarr/bundled-images.lock.json').read_text())['seerr']['image']
    compose={'services':{
        'plex':{'image':'stackarr:one-app-20261020-r2','entrypoint':['python','/fixture.py'],
                'ports':['127.0.0.1:43800:8080'],'healthcheck':{'disable':True},'volumes':[str(Path('tools/account_plex_protocol_fixture.py').resolve()).replace('\\','/')+':/fixture.py:ro',str(protocol).replace('\\','/')+':/state']},
        'seerr':{'image':image,'ports':['127.0.0.1:43805:5055'],'volumes':['seerr-config:/app/config'],
                 'environment':{'LOG_LEVEL':'error','NEXT_TELEMETRY_DISABLED':'1'}}},'networks':{'default':{}},'volumes':{'seerr-config':{}}}
    write('compose-private.json',compose)
    base=['compose','--project-name',PROJECT,'-f',str(ROOT/'compose-private.json')]
    ids=[]
    try:
        source.command([*base,'up','-d'],timeout=120)
        ids=source.command([*base,'ps','-aq']).splitlines()
        assert len(ids)==2
        ready()
        seerr=next(row for row in json.loads(source.command(['inspect',*ids])) if row['Config']['Labels']['com.docker.compose.service']=='seerr')['Id']
        NATIVE_SEERR_ID=seerr
        source.command(['stop','--time','20',seerr])
        source.command(['cp',seerr+':/app/config/db',str(config/'db')])
        source.command(['cp',seerr+':/app/config/settings.json',str(config/'settings.json')])
        settings=json.loads((config/'settings.json').read_text())
        settings['main'].update(mediaServerType=1,mediaServerLogin=True,newPlexLogin=False,versionCheck=False)
        settings['public']['initialized']=False
        settings['plex']['webAppUrl']='https://app.plex.tv/desktop'
        (config/'settings.json').write_text(json.dumps(settings))
        with sqlite3.connect(config/'db/db.sqlite3') as db:
            assert db.execute('SELECT count(*) FROM user').fetchone()[0]==0
            db.execute('INSERT INTO user (id,email,username,password,userType,permissions,avatar,plexId,plexToken) VALUES (1,?,?,?,?,?,?,?,?)',
                ('fixture@stackarr.invalid','Synthetic component owner','disabled',1,2,'',71,TOKEN))
            db.commit()
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        source.command(['cp',str(config/'db/db.sqlite3'),seerr+':/app/config/db/db.sqlite3'])
        empty=ROOT/'empty-sqlite-sidecar'
        empty.write_bytes(b'')
        for suffix in ('-wal','-shm'):
            source.command(['cp',str(empty),seerr+':/app/config/db/db.sqlite3'+suffix])
        source.command(['cp',str(config/'settings.json'),seerr+':/app/config/settings.json'])
        source.command(['run','--rm','--network','none','--user','0','--entrypoint','chown','--volume',PROJECT+'_seerr-config:/app/config',image,'-R','1000:1000','/app/config'])
        source.command(['start',seerr])
        ready(settings['main']['apiKey'])
        asyncio.run(verify())
    finally:
        current=source.command([*base,'ps','-aq']).splitlines()
        if current:
            infos=json.loads(source.command(['inspect',*current]))
            assert all(row['Config']['Labels']['com.docker.compose.project']==PROJECT and all(m['Type']!='bind' or '/accounts-source-20261020/' in m['Source'].replace('\\','/') or m['Destination']=='/fixture.py' for m in row['Mounts']) for row in infos)
            source.command(['stop','--time','20',*current])
            source.command(['rm',*current])
        network=json.loads(source.command(['network','inspect',PROJECT+'_default']))[0]
        assert not network['Containers'] and network['Labels']['com.docker.compose.project']==PROJECT
        source.command(['network','rm',network['Id']])
        volume=json.loads(source.command(['volume','inspect',PROJECT+'_seerr-config']))[0]
        assert volume['Labels']['com.docker.compose.project']==PROJECT
        source.command(['volume','rm',volume['Name']])
        source.preserved()
        write('cleanup.json',{'passed':True,'containers_removed':len(current),'main_unchanged':True,'old_libraries_stay_deleted':True})
    print('Native Seerr library setup and recovery passed against explicit protocol/account fixtures. Containers removed; main unchanged.')


if __name__=='__main__':
    main()

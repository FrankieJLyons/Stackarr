import json
from types import SimpleNamespace

import httpx
import pytest

from stackarr import account_setup
from stackarr.account_setup import Accounts, AccountSetupError
from stackarr.store import Conflict, Store


@pytest.fixture
def setup(tmp_path, monkeypatch):
    store=Store(tmp_path/'state')
    revision,config=store.config()
    for key,port in (('plex',54800),('seerr',54801)):
        config.integrations[key].enabled=True
        config.integrations[key].url=f'http://127.0.0.1:{port}'
        config.integrations[key].peer_url=f'http://{key}:'+('32400' if key=='plex' else '5055')
    store.save(config,revision)
    payload={'apps':['plex','seerr'],'context':{'name':'fixture'},'compose':{'services':{}}}
    host=SimpleNamespace(store=store,context=lambda:{'name':'fixture'})
    state={'claimed':True,'machine':'owned-machine','libraries':[],
        'settings':{'main':{'apiKey':'synthetic-seerr-key','mediaServerType':4},'public':{'initialized':False},
                    'plex':{'machineId':'','libraries':[],'webAppUrl':'https://app.plex.tv/desktop'}},
        'owner':{'id':1,'plexId':71},'auth_id':1,'calls':[]}
    monkeypatch.setattr(account_setup,'load_receipt',lambda *args:payload)
    def settings(host,identity,payload,key,integration):
        return ('<Preferences PlexOnlineToken="fixture-plex" ProcessedMachineIdentifier="owned-machine"/>'
                if key=='plex' else json.dumps(state['settings']))
    monkeypatch.setattr(account_setup,'read_settings',settings)
    def handle(request):
        state['calls'].append(request)
        path,method=request.url.path,request.method
        if (method=='GET' and path in ('/api/v1/settings/plex','/api/v1/user/1')
                and state['settings']['main']['mediaServerType']==4):
            return httpx.Response(403,json={'error':'No first owner yet'})
        if request.url.host=='plex.tv':
            return httpx.Response(200,json={'user':{'id':71}})
        if path=='/identity':
            return httpx.Response(200,json={'MediaContainer':{'claimed':state['claimed'],'machineIdentifier':state['machine']}})
        if path=='/library/sections':
            if method=='POST':
                params=request.url.params
                state['libraries'].append({'key':str(len(state['libraries'])+1),'type':params['type'],
                    'title':params['name'],'Location':[{'path':params['location']}]})
            return httpx.Response(200,json={'MediaContainer':{'size':len(state['libraries']),**({'Directory':state['libraries']} if state['libraries'] else {})}})
        if path in ('/library/sections/1/refresh','/library/sections/2/refresh'):
            return httpx.Response(200,content=b'')
        if path=='/api/v1/auth/plex':
            assert json.loads(request.content)=={'authToken':'fixture-plex'}
            state['settings']['main']['mediaServerType']=1
            return httpx.Response(200,json={'id':state['auth_id'],'plexToken':'NEVER-PUBLIC','email':'NEVER-PUBLIC'})
        if path=='/api/v1/user/1':
            return httpx.Response(200,json=state['owner'])
        if path=='/api/v1/settings/plex':
            if method=='POST':
                state['settings']['plex'].update(json.loads(request.content),machineId=state['machine'])
            return httpx.Response(200,json=state['settings']['plex'])
        if path=='/api/v1/settings/plex/library/sync':
            enabled={row['id']:row.get('enabled') for row in state['settings']['plex']['libraries']}
            state['settings']['plex']['libraries']=[{'id':row['key'],'name':row['title'],'enabled':enabled.get(row['key'],False)} for row in state['libraries']]
            return httpx.Response(200,json=state['settings']['plex']['libraries'])
        if path.startswith('/api/v1/settings/plex/library/'):
            key=path.rsplit('/',1)[-1]
            next(row for row in state['settings']['plex']['libraries'] if row['id']==key)['enabled']=True
            return httpx.Response(200,json={})
        if path=='/api/v1/settings/initialize':
            state['settings']['public']['initialized']=True
            return httpx.Response(200,json={})
        raise AssertionError('Unexpected test request '+method+' '+path)
    service=Accounts(host,httpx.MockTransport(handle))
    return service,state


async def test_empty_library_review_is_read_only_and_public_has_no_credentials(setup):
    service,state=setup
    plan=await service.review('a'*32)
    public=service.public(plan)
    assert [row['state'] for row in public['libraries']]==['create','create']
    assert all(request.method=='GET' for request in state['calls'])
    assert not any(value in json.dumps(public) for value in ('synthetic','NEVER-PUBLIC','plex_key','seerr-key'))
    assert state['libraries']==[] and not state['settings']['public']['initialized']


async def test_one_plex_signin_prepares_libraries_and_request_account_without_copying_keys(setup):
    service,state=setup
    result=await service.apply(await service.review('a'*32))
    assert result['state']=='connected'
    assert {row['Location'][0]['path'] for row in state['libraries']}=={'/data/media/movies','/data/media/tv'}
    assert state['settings']['public']['initialized'] and all(row['enabled'] for row in state['settings']['plex']['libraries'])
    assert state['settings']['plex']['machineId']=='owned-machine'
    assert state['settings']['plex']['webAppUrl']=='https://app.plex.tv/desktop'
    assert len([r for r in state['calls'] if r.url.path=='/api/v1/auth/plex'])==1
    assert {r.url.path for r in state['calls'] if r.url.path.endswith('/refresh')}=={'/library/sections/1/refresh','/library/sections/2/refresh'}
    assert 'synthetic' not in json.dumps(result)


async def test_repeat_review_and_apply_preserve_existing_libraries_and_owner(setup):
    service,state=setup
    await service.apply(await service.review('a'*32))
    state['calls'].clear()
    review=await service.review('a'*32)
    assert not review['create']
    await service.apply(review)
    assert len(state['libraries'])==2
    assert not any(r.url.path in ('/api/v1/auth/plex','/library/sections') and r.method=='POST' for r in state['calls'])
    assert not any(r.url.path.endswith('/refresh') for r in state['calls'])


async def test_interrupted_new_library_scan_is_retained_for_review_and_retry(setup,monkeypatch):
    service,state=setup
    original=account_setup.call
    failed=False
    async def interrupt(client,method,base,path,**kwargs):
        nonlocal failed
        if path.endswith('/1/refresh') and not failed:
            failed=True
            raise AccountSetupError('Temporary scan failure')
        return await original(client,method,base,path,**kwargs)
    monkeypatch.setattr(account_setup,'call',interrupt)
    with pytest.raises(AccountSetupError,match='scan failure'):
        await service.apply(await service.review('a'*32))
    review=await service.review('a'*32)
    assert not review['create'] and len(review['initialize_paths'])==2
    await service.apply(review)
    assert not (await service.review('a'*32))['initialize_paths']
    assert len(state['libraries'])==2


@pytest.mark.parametrize('change',['identity','unclaimed','wrong-server','other-owner','revision','libraries'])
async def test_changed_setup_or_other_accounts_cannot_be_overwritten(setup,change):
    service,state=setup
    review=await service.review('a'*32)
    if change=='identity':
        state['machine']='someone-else'
    elif change=='unclaimed':
        state['claimed']=False
    elif change=='wrong-server':
        state['settings']['plex']['machineId']='someone-else'
    elif change=='other-owner':
        state['settings']['public']['initialized']=True
        state['settings']['main']['mediaServerType']=1
        state['owner']['plexId']=999
    elif change=='revision':
        revision,config=service.store.config()
        service.store.save(config,revision)
    else:
        state['libraries'].append({'key':'99','type':'show','title':'Keep me','Location':[{'path':'/other'}]})
    state['calls'].clear()
    with pytest.raises((AccountSetupError,Conflict)):
        await service.apply(review)
    assert all(r.method=='GET' for r in state['calls'])


async def test_partial_signin_resumes_same_owner_without_another_signin(setup):
    service,state=setup
    state['settings']['main']['mediaServerType']=1
    review=await service.review('a'*32)
    assert not review['seerr']['authenticate']
    await service.apply(review)
    assert state['settings']['public']['initialized']
    assert not any(r.url.path=='/api/v1/auth/plex' for r in state['calls'])


async def test_unclaimed_server_is_an_actionable_signin_step_and_is_never_claimed(setup):
    service,state=setup
    state['claimed']=False
    with pytest.raises(AccountSetupError,match='Sign in to Plex'):
        await service.review('a'*32)
    assert all(r.method=='GET' for r in state['calls'])


async def test_native_signin_must_confirm_original_request_owner_before_configuring(setup):
    service,state=setup
    state['auth_id']=2
    with pytest.raises(AccountSetupError,match='another owner'):
        await service.apply(await service.review('a'*32))
    assert not any(r.method!='GET' and r.url.path.startswith('/api/v1/settings/') for r in state['calls'])



def test_automatic_wiring_excludes_changed_addresses_peers_and_credentials(tmp_path):
    from stackarr.account_setup import wiring_scope
    store=Store(tmp_path/'bindings')
    revision,config=store.config()
    ports={'plex':54800,'seerr':54801}
    credentials={key:{'api_key':'synthetic-'+key} for key in ports}
    for key,port in ports.items():
        config.integrations[key].enabled=True
        config.integrations[key].url=config.integrations[key].peer_url=f'http://host.docker.internal:{port}'
    store.save(config,revision,credentials)
    assert wiring_scope(store,ports,credentials)[1]=={'plex','seerr'}
    revision,config=store.config()
    config.integrations['plex'].url='http://different-main.invalid'
    config.integrations['seerr'].peer_url='http://different-main.invalid'
    store.save(config,revision)
    assert wiring_scope(store,ports,credentials)[1]==set()
    revision,config=store.config()
    for key,port in ports.items():
        config.integrations[key].url=config.integrations[key].peer_url=f'http://host.docker.internal:{port}'
    store.save(config,revision,{'seerr':{'api_key':'user-changed'}})
    assert wiring_scope(store,ports,credentials)[1]=={'plex'}

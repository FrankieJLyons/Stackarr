"""Synthetic Plex library protocol; never contacts Plex or an account."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT=Path('/state')
MACHINE='stackarr-account-protocol-fixture'


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def send(self,value,status=200):
        body=json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path=urlsplit(self.path).path
        libraries=json.loads((ROOT/'libraries.json').read_text())
        if path in ('/','/identity'):
            return self.send({'MediaContainer':{'size':0,'machineIdentifier':MACHINE,'claimed':True,'friendlyName':'SIMULATED account protocol','version':'1.43.4'}})
        if path=='/library/sections':
            return self.send({'MediaContainer':{'size':len(libraries),**({'Directory':libraries} if libraries else {})}})
        return self.send({'MediaContainer':{'size':0,'Metadata':[]}})

    def do_POST(self):
        if urlsplit(self.path).path!='/library/sections':
            return self.send({},404)
        query=parse_qs(urlsplit(self.path).query)
        libraries=json.loads((ROOT/'libraries.json').read_text())
        libraries.append({'key':str(len(libraries)+1),'title':query['name'][0],'type':query['type'][0],
                          'agent':query['agent'][0],'Location':[{'path':query['location'][0]}]})
        (ROOT/'libraries.json').write_text(json.dumps(libraries))
        self.send({'MediaContainer':{'Directory':[libraries[-1]]}})


if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()

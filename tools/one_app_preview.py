"""Isolated first-run UI preview. No installation controller or media app access."""
from pathlib import Path

import uvicorn

from stackarr.server import create_app, password_hash

ROOT = Path('test-results/one-app-20261020/setup-preview').resolve()


def build():
    media = ROOT / 'media'
    media.mkdir(parents=True,exist_ok=True)
    app = create_app(ROOT / 'state',origin='http://localhost:29350',background=False,
        media_roots=[{'path':str(media),'host_path':str(media),'label':'Preview media folder'}])
    with app.state.store.db() as db:
        db.execute('INSERT OR IGNORE INTO account VALUES(1,?,?)',('22'*16,password_hash('Stackarr setup preview','22'*16)))
    return app


if __name__ == '__main__':
    uvicorn.run(build(),host='127.0.0.1',port=29350,access_log=False)

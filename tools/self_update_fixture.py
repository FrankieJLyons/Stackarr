"""Build a disposable candidate that writes its isolated DB but passes HTTP health."""

import argparse
import subprocess
from pathlib import Path

from stackarr.docker_runtime import executable

SCRIPT = '''import json,os,sqlite3
from http.server import BaseHTTPRequestHandler,HTTPServer
assert os.environ.get('STACKARR_UPDATE_CHECKING')=='1', 'Disposable candidate only'
db=sqlite3.connect('/var/lib/stackarr/stackarr.db')
raw=db.execute('SELECT data FROM settings WHERE id=1').fetchone()[0]
value=json.loads(raw); value['dashboard']['appearance']='light'
db.execute('UPDATE settings SET revision=revision+1,data=? WHERE id=1',(json.dumps(value),))
db.execute('CREATE TABLE self_update_failure_fixture (id INTEGER PRIMARY KEY,value TEXT)')
db.execute("INSERT INTO self_update_failure_fixture VALUES(1,'candidate wrote isolated data')")
db.commit(); db.close()
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(b'{"status":"ok","fixture":true}')
 def log_message(self,*args): pass
HTTPServer(('0.0.0.0',8787),Handler).serve_forever()
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--base-image", required=True)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    assert args.root.resolve().is_relative_to(Path("test-results").resolve())
    assert args.base_image.startswith("stackarr:self-update-preview-") and args.image.startswith("stackarr:self-update-failed-fixture-")
    args.root.mkdir(exist_ok=True)
    (args.root / "faulty_start.py").write_text(SCRIPT)
    (args.root / "Dockerfile").write_text("FROM " + args.base_image + '\nCOPY faulty_start.py /app/faulty_start.py\nCMD ["python","/app/faulty_start.py"]\n')
    subprocess.run([executable(), "build", "-t", args.image, str(args.root)], check=True, timeout=120)


if __name__ == "__main__":
    main()

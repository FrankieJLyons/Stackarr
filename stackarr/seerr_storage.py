"""Verify owned Seerr storage before clearing its legacy image-only warning."""

from .app_maintenance import AppMaintenance
from .deployment import DeploymentError

PROBE = """const fs=require('fs'),crypto=require('crypto');
const root='/app/config';
const dir=fs.lstatSync(root);
if(!dir.isDirectory()||dir.isSymbolicLink()||fs.realpathSync(root)!==root)throw Error('Unexpected config directory');
const name=root+'/.stackarr-storage-'+crypto.randomBytes(16).toString('hex');
const data=crypto.randomBytes(64);let fd,created=false;
try{
 fd=fs.openSync(name,'wx',0o600);created=true;
 fs.writeFileSync(fd,data);fs.fsyncSync(fd);fs.closeSync(fd);fd=undefined;
 if(!fs.readFileSync(name).equals(data))throw Error('Storage check failed');
}finally{
 if(fd!==undefined)fs.closeSync(fd);
 if(created)fs.unlinkSync(name);
}
const parent=fs.openSync(root,fs.constants.O_RDONLY|fs.constants.O_DIRECTORY);
try{fs.fsyncSync(parent);}finally{fs.closeSync(parent);}
console.log('verified');"""

CLEAR = """const fs=require('fs');
const root='/app/config',name=root+'/DOCKER';
if(!fs.lstatSync(root).isDirectory()||fs.realpathSync(root)!==root)throw Error('Unexpected config directory');
let marker;
try{marker=fs.lstatSync(name);}catch(e){if(e.code!=='ENOENT')throw e;}
if(marker){
 if(!marker.isFile()||marker.isSymbolicLink()||marker.size!==0||marker.nlink!==1)throw Error('Unexpected image marker');
 fs.unlinkSync(name);
 const parent=fs.openSync(root,fs.constants.O_RDONLY|fs.constants.O_DIRECTORY);
 try{fs.fsyncSync(parent);}finally{fs.closeSync(parent);}
}
console.log('ready');"""


def prepare(deployments, identity, payload):
    if "seerr" not in payload["apps"]:
        return
    maintenance = AppMaintenance(deployments)
    try:
        info = maintenance.container(identity, payload, "seerr")
        if not info or not info["State"].get("Running"):
            raise ValueError("Seerr is not running")
        before = maintenance.resources(identity, payload, "seerr", info)
        base = ["--context", payload["context"]["name"], "exec", info["Id"], "node", "-e"]
        if deployments._call([*base, PROBE]).strip() != "verified":
            raise ValueError("Storage probe did not verify")
        current = maintenance.container(identity, payload, "seerr")
        if (not current or current["Id"] != info["Id"] or not current["State"].get("Running")
                or maintenance.resources(identity, payload, "seerr", current) != before):
            raise ValueError("Owned storage changed")
        if deployments._call([*base, CLEAR]).strip() != "ready":
            raise ValueError("The image marker did not verify")
    except (ValueError, OSError, KeyError, IndexError, TypeError):
        raise DeploymentError("Seerr's settings storage could not be verified. Its settings are preserved. Check Docker and the owned settings volume, then resume installation.", kind="seerr-storage") from None
    deployments.store.audit("deployment.seerr-storage-verified", identity)

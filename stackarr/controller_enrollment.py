"""Host-created, file-backed enrollment for the private installation controller."""

import ipaddress
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from .controller_transport import ControllerClient

PORT = 28010
HOST = "host.docker.internal"


def _write_new(path, content):
    with path.open("xb") as file:
        file.write(content)
    os.chmod(path, 0o600)


def enroll(root):
    """Create a stable identity once; never silently replace partial enrollment."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    shared = root / "shared"
    shared.mkdir(exist_ok=True, mode=0o700)
    key_path, cert_path, private_path = shared / "rpc.key", shared / "controller.crt", root / "controller.key"
    present = [path.exists() for path in (key_path, cert_path, private_path)]
    if any(present) and not all(present):
        raise ValueError("Controller enrollment is incomplete. Repair it before starting Stackarr.")
    if not any(present):
        private = ec.generate_private_key(ec.SECP256R1())
        now = datetime.now(timezone.utc)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOST)])
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(private.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=1825))
                .add_extension(x509.SubjectAlternativeName([
                    x509.DNSName(HOST), x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]), critical=False)
                .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                .sign(private, hashes.SHA256()))
        _write_new(private_path, private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        _write_new(cert_path, cert.public_bytes(serialization.Encoding.PEM))
        _write_new(key_path, secrets.token_bytes(32))
    key = key_path.read_bytes()
    if len(key) != 32:
        raise ValueError("Controller enrollment key is invalid")
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    private = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
    if cert.public_key().public_numbers() != private.public_key().public_numbers():
        raise ValueError("Controller certificate and private key do not match")
    if cert.not_valid_after_utc <= datetime.now(timezone.utc):
        raise ValueError("Controller certificate expired; renew enrollment before starting Stackarr")
    return {"shared": shared, "key": key_path, "certificate": cert_path, "private": private_path}


def client(shared, address=None, authority=None):
    shared = Path(shared)
    address = address or f"https://{HOST}:{int(os.environ.get('STACKARR_CONTROLLER_PORT', PORT))}"
    return ControllerClient(address, (shared / "rpc.key").read_bytes(),
                            certificate=str(shared / "controller.crt"), authority=authority)

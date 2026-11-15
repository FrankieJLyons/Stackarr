import argparse
import json
import os
from pathlib import Path

from .config import Config
from .controller_transport import ControllerConnectionError
from .installer import Installer, compose_plan, preflight


def main():
    parser = argparse.ArgumentParser(description="Stackarr local administration")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    for name in ("preflight", "plan", "prepare"):
        item = sub.add_parser(name)
        item.add_argument("config", type=Path, help="Redacted configuration exported from Settings")
        if name == "prepare":
            item.add_argument("directory", type=Path)
    for name in ("apply", "stop", "rollback"):
        item = sub.add_parser(name)
        item.add_argument("directory", type=Path)
    sub.add_parser("setup-token")
    sub.add_parser("setup-link")
    enrollment = sub.add_parser("controller-enroll")
    enrollment.add_argument("directory", type=Path)
    controller = sub.add_parser("controller-serve")
    controller.add_argument("directory", type=Path)
    controller.add_argument("--host", default="127.0.0.1")
    controller.add_argument("--port", type=int, default=28010)
    probe = sub.add_parser("controller-probe")
    probe.add_argument("directory", type=Path)
    readiness = sub.add_parser("host-check")
    readiness.add_argument("config", type=Path, help="Configuration export or reviewed wizard plan")
    args = parser.parse_args()
    try:
        if args.command == "serve":
            import uvicorn

            from .server import create_app

            uvicorn.run(create_app(), host=args.host, port=args.port, proxy_headers=False, access_log=False)
        elif args.command == "setup-link":
            from .config import validate_url
            from .setup_handoff import issue
            from .store import Store

            root = Path(os.environ.get("STACKARR_DATA", ".runtime"))
            if not (root / "stackarr.db").is_file():
                raise ValueError("Start Stackarr before opening setup.")
            print(issue(Store(root), validate_url(os.environ.get("STACKARR_ORIGIN", "http://localhost:8787"), origin_only=True)))
        elif args.command == "controller-enroll":
            from .controller_enrollment import enroll

            enroll(args.directory)
            print("Private controller enrollment is ready.")
        elif args.command == "controller-serve":
            import asyncio

            import uvicorn

            from .controller import InstallationController
            from .controller_enrollment import enroll
            from .controller_transport import create_controller_app
            from .store import Store

            identity = enroll(args.directory)
            roots = json.loads(os.environ.get("STACKARR_CONTROLLER_ROOTS", "[]"))
            os.environ["STACKARR_CONTROLLER_PORT"] = str(args.port)
            state = Path(os.environ.get("STACKARR_CONTROLLER_STATE", str(args.directory / "state")))
            if state.parent.resolve() != args.directory.resolve() or not (state.name == "state" or __import__("re").fullmatch(r"state-candidate-[a-f0-9]{32}", state.name)):
                raise ValueError("Controller state must stay inside its enrollment directory")
            from .backup_policy import direct

            direct(state)
            checking = os.environ.get("STACKARR_UPDATE_CHECKING") == "1"
            service = InstallationController(Store(state), roots,
                                             int(os.environ.get("STACKARR_PORT", "28000")), controller_port=args.port)
            app = create_controller_app(service, identity["key"].read_bytes(),
                                        f"host.docker.internal:{args.port}", run_worker=not checking)
            server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, proxy_headers=False, access_log=False,
                log_config=None, ssl_certfile=str(identity["certificate"]), ssl_keyfile=str(identity["private"])))

            async def watch():
                from .self_update import pending, read

                marker = args.directory / "self-update-stop.json"
                while True:
                    if marker.is_file():
                        value = read(marker)
                        job = pending(args.directory.parent)
                        if value.get("pid") == os.getpid() and job and value.get("job") == job["id"]:
                            marker.unlink()
                            server.should_exit = True
                            return
                    await asyncio.sleep(.2)

            async def serve_controller():
                watcher = asyncio.create_task(watch())
                try:
                    await server.serve()
                finally:
                    watcher.cancel()
                    from contextlib import suppress

                    with suppress(asyncio.CancelledError):
                        await watcher

            asyncio.run(serve_controller())
        elif args.command == "controller-probe":
            import asyncio

            from .controller_enrollment import client

            asyncio.run(client(args.directory).request("status"))
            print("Installation controller connected.")
        elif args.command == "setup-token":
            path = Path(os.environ.get("STACKARR_DATA", ".runtime")) / "setup-token"
            print(
                path.read_text().strip()
                if path.exists()
                else "Start Stackarr first, or setup is already complete."
            )
        elif args.command == "host-check":
            from .readiness import report

            data = json.loads(args.config.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict) and "config" in data and "plan" in data:
                data = data["config"]
            result = report(Config.model_validate(data), enabled=True)
            print(json.dumps(result, indent=2))
            if not result["preflight_passed"]:
                raise SystemExit(1)
        elif args.command in ("apply", "stop", "rollback"):
            Installer(args.directory).run(args.command)
            print("Operation complete. Application data and media were preserved.")
        else:
            config = Config.model_validate_json(args.config.read_text(encoding="utf-8-sig"))
            if args.command == "plan":
                print(json.dumps(compose_plan(config), indent=2))
            else:
                checks = preflight(config)
                print(json.dumps(checks, indent=2))
                if not all(c["ok"] for c in checks):
                    raise SystemExit(1)
                if args.command == "prepare":
                    Installer(args.directory).prepare(config)
                    print("Plan prepared. Review compose.json before running stackarr apply.")
    except (ValueError, OSError, ControllerConnectionError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()

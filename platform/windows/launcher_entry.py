from stackarr.launcher import main

if __name__ == "__main__":
    import argparse
    import sys

    if len(sys.argv) == 3 and sys.argv[1] == "--self-test-report":
        from stackarr.selftest import run

        raise SystemExit(run(sys.argv[2]))
    parser = argparse.ArgumentParser(description="Stackarr local setup")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--choose-media-folder", help="Internal native folder dialog result file")
    mode.add_argument("--package-first-run", action="store_true", help="Open readiness and reviewed Docker setup for this package")
    mode.add_argument("--runtime-report", help="Write a read-only Docker check to a new report file, without opening setup")
    mode.add_argument("--controller-enroll", help="Prepare a private controller enrollment directory")
    mode.add_argument("--controller-serve", help="Run the scoped controller from its enrollment directory")
    mode.add_argument("--host-recovery", action="store_true", help="Open the local whole-host recovery wizard")
    mode.add_argument("--host-recovery-review", help="Review a host-local recovery request file")
    mode.add_argument("--host-recovery-apply", help="Apply a saved host-local recovery review")
    mode.add_argument("--stackarr-maintenance", help="Run the independent Stackarr maintenance worker for this state directory")
    mode.add_argument("--stackarr-start", help="Start the active managed Stackarr release, recovering an interrupted update first")
    mode.add_argument("--lan-review", help="Review a prepared LAN gateway bundle on this computer")
    mode.add_argument("--lan-apply", help="Apply a saved LAN review with an encrypted rollback checkpoint")
    mode.add_argument("--lan-run", help="Resume the verified runtime, then run its separate HTTPS gateway")
    mode.add_argument("--lan-setup", help="Open guided home-network setup and recovery for this installation")
    parser.add_argument("--lan-workspace", help="Separate saved home-network setup folder")
    parser.add_argument("--lan-caddy", help="Pinned Caddy executable for source/lab use; packaged builds include it")
    parser.add_argument("--lan-ready-report", help="Write a new private local setup-window report")
    mode.add_argument("--stackarr-reinstall", help="Review reinstall of a retained, removed Stackarr installation")
    mode.add_argument("--stackarr-reinstall-review", help="Review a host-local reinstall request file")
    mode.add_argument("--stackarr-reinstall-apply", help="Apply a one-use host-local reinstall review")
    mode.add_argument("--stackarr-repair", help="Open local reviewed repair for an existing Stackarr runtime")
    mode.add_argument("--stackarr-repair-review", help="Review a host-local runtime repair request")
    mode.add_argument("--stackarr-repair-apply", help="Apply a one-use host-local runtime repair review")
    parser.add_argument("--maintenance-job")
    parser.add_argument("--maintenance-recover", action="store_true")
    parser.add_argument("--maintenance-report")
    parser.add_argument("--recovery-report", help="Write the recovery review or result to a new file")
    parser.add_argument("--controller-port", type=int, default=28010)
    parser.add_argument("--data-directory", help="Use a separate absolute data directory for an isolated preview")
    parser.add_argument("--connect-directory", help="Separate local dashboard data directory for existing-app connections")
    parser.add_argument("--media-folder", help="Existing media folder to offer during reviewed app setup")
    parser.add_argument("--prerequisite-directory", help="Separate Docker prerequisite journal directory")
    parser.add_argument("--first-run-report", help="Write a new private readiness-window address report")
    parser.add_argument("--launcher-ready-report", help="Write a new private local dashboard address report")
    parser.add_argument("--dashboard-port", type=int, default=28000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if args.lan_setup:
        import hashlib
        from pathlib import Path

        from stackarr.lan_setup_server import run

        state = Path(args.lan_setup).absolute()
        workspace = args.lan_workspace or str(state.parent / ("HomeNetwork-" + hashlib.sha256(str(state).casefold().encode()).hexdigest()[:12]))
        raise SystemExit(run(state, workspace, args.lan_caddy, args.lan_ready_report, args.no_browser))
    if args.lan_review or args.lan_apply or args.lan_run:
        import json
        from pathlib import Path

        from stackarr.lan_gateway import apply, review, serve

        if args.lan_run:
            raise SystemExit(serve(args.lan_run))
        if not args.maintenance_report:
            parser.error("--maintenance-report is required")
        if args.lan_review:
            review(args.lan_review, args.maintenance_report)
        else:
            value = apply(args.lan_apply)
            with Path(args.maintenance_report).open("x", encoding="utf-8") as output:
                json.dump(value, output)
        raise SystemExit(0)
    if args.choose_media_folder:
        from stackarr.media_folders import dialog

        raise SystemExit(dialog(args.choose_media_folder))
    if args.package_first_run:
        from stackarr.first_run_package import main as first_run_main

        raise SystemExit(first_run_main(args))
    if args.stackarr_repair:
        from stackarr.reinstall_wizard import wizard

        wizard(args.stackarr_repair, "repair")
        raise SystemExit(0)
    if args.stackarr_repair_review or args.stackarr_repair_apply:
        from stackarr.reinstall_wizard import command

        if not args.maintenance_report:
            parser.error("--maintenance-report is required")
        raise SystemExit(command("review" if args.stackarr_repair_review else "apply",
                                 args.stackarr_repair_review or args.stackarr_repair_apply, args.maintenance_report, "repair"))
    if args.stackarr_reinstall:
        from stackarr.reinstall_wizard import wizard

        wizard(args.stackarr_reinstall)
        raise SystemExit(0)
    if args.stackarr_reinstall_review or args.stackarr_reinstall_apply:
        from stackarr.reinstall_wizard import command

        if not args.maintenance_report:
            parser.error("--maintenance-report is required")
        raise SystemExit(command("review" if args.stackarr_reinstall_review else "apply",
                                 args.stackarr_reinstall_review or args.stackarr_reinstall_apply, args.maintenance_report))
    if args.stackarr_maintenance or args.stackarr_start:
        import json
        from pathlib import Path

        from stackarr.self_removal import StackarrRemoved
        from stackarr.self_update import SelfUpdates

        status = 0
        try:
            updates = SelfUpdates(Path(args.stackarr_maintenance or args.stackarr_start))
            if args.stackarr_start:
                value = {"url": updates.start(), "passed": True, "removed": False}
            else:
                updates.execute(args.maintenance_job, args.maintenance_recover)
                job = json.loads((updates.home / "jobs" / args.maintenance_job / "job.json").read_text())
                value = {k: job[k] for k in ("id", "phase", "message")}
                status = 1 if job["phase"] == "needs-recovery" else 0
        except StackarrRemoved:
            value = {"passed": True, "removed": True, "message": "Stackarr is removed with settings retained. Review reinstall from Start Stackarr."}
        except Exception:
            status, value = 1, {"passed": False, "message": "Stackarr could not complete maintenance. Check Docker and storage, then reopen Start Stackarr. Existing app volumes and media are preserved."}
        if args.maintenance_report:
            with Path(args.maintenance_report).open("x", encoding="utf-8") as output:
                json.dump(value, output)
        raise SystemExit(status)
    if args.host_recovery:
        from stackarr.recovery_wizard import wizard

        wizard()
        raise SystemExit(0)
    if args.host_recovery_review or args.host_recovery_apply:
        from stackarr.recovery_wizard import command

        if not args.recovery_report:
            parser.error("--recovery-report is required")
        raise SystemExit(command("review" if args.host_recovery_review else "apply",
                                 args.host_recovery_review or args.host_recovery_apply, args.recovery_report))
    if args.runtime_report:
        from stackarr.docker_runtime import write_report

        try:
            raise SystemExit(write_report(args.runtime_report))
        except OSError:
            raise SystemExit(2) from None
    if args.controller_enroll:
        from stackarr.controller_enrollment import enroll

        enroll(args.controller_enroll)
        raise SystemExit(0)
    if args.controller_serve:
        import json
        from pathlib import Path

        from stackarr.cli import main as controller_main

        sys.argv = [sys.argv[0], "controller-serve", args.controller_serve, "--port", str(args.controller_port)]
        try:
            controller_main()
        except Exception as exc:
            # Frozen background processes have no console; keep a redacted local diagnostic.
            try:
                (Path(args.controller_serve) / "startup-failure.json").write_text(json.dumps({
                    "error": type(exc).__name__, "message": "The private controller could not start. Check its port and enrollment."}), encoding="utf-8")
            except OSError:
                pass
            raise SystemExit(1) from None
        raise SystemExit(0)
    main(args.data_directory, ready_report=args.launcher_ready_report, open_browser=not args.no_browser)

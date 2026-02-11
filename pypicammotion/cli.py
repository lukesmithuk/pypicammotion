from __future__ import annotations

import argparse
import logging
import sys
import threading
from datetime import datetime
from pathlib import Path

log = logging.getLogger("pypicammotion")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)-5s %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stderr)


def cmd_list_cameras(args: argparse.Namespace) -> None:
    from picamera2 import Picamera2

    cameras = Picamera2.global_camera_info()
    if not cameras:
        print("no cameras detected")
        return
    for cam in cameras:
        print(f"  [{cam['Num']}] {cam['Model']}  id={cam['Id']}")


def cmd_test(args: argparse.Namespace) -> None:
    from .camera import Camera
    from .config import CameraConfig

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg = CameraConfig(
        name="test",
        device=args.camera,
        sensitivity=args.sensitivity,
    )

    stop_event = threading.Event()

    def on_clip(camera: str, path: Path, ts: datetime, dur: float, start_mono: float | None = None) -> None:
        print(f"  clip saved: {path} ({dur:.1f}s)")

    cam = Camera(
        config=cfg,
        storage_path=output_dir,
        on_clip_saved=on_clip,
        stop_event=stop_event,
    )

    print(f"testing camera {args.camera} (sensitivity={args.sensitivity})")
    print(f"clips → {output_dir}")
    print("press Ctrl+C to stop\n")

    cam.start()
    try:
        stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        print("\nstopping…")
        cam.stop()
        print("done")


def cmd_run(args: argparse.Namespace) -> None:
    from .config import load_config
    from .service import Service

    config = load_config(args.config)
    Service(config).run()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pypicammotion",
        description="Motion-detection video recording for Raspberry Pi cameras",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="enable debug logging"
    )
    sub = parser.add_subparsers(dest="command")

    # list-cameras
    sub.add_parser("list-cameras", help="list connected cameras")

    # test
    p_test = sub.add_parser("test", help="test a single camera")
    p_test.add_argument(
        "--camera", type=int, default=0, help="camera device number (default: 0)"
    )
    p_test.add_argument(
        "--sensitivity", type=float, default=0.05, help="motion sensitivity 0.0–1.0 (default: 0.05)"
    )
    p_test.add_argument(
        "--output-dir", default="/tmp/pypicammotion-test", help="directory for test clips"
    )

    # run
    p_run = sub.add_parser("run", help="run the service with a config file")
    p_run.add_argument(
        "--config", required=True, help="path to YAML config file"
    )

    args = parser.parse_args()
    _setup_logging(args.verbose)

    if args.command == "list-cameras":
        cmd_list_cameras(args)
    elif args.command == "test":
        cmd_test(args)
    elif args.command == "run":
        cmd_run(args)
    else:
        parser.print_help()
        sys.exit(1)

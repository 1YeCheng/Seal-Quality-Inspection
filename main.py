from __future__ import annotations

import argparse
import sys


def run_batch(args) -> int:
    from modules.config_manager import ConfigManager
    from modules.inspection_service import InspectionService

    config_manager = ConfigManager(args.config)
    service = InspectionService(config_manager)
    folder_2d = args.folder_2d or config_manager.resolve_path(config_manager.config["pairing"]["folder_2d"])
    folder_ir = args.folder_ir or config_manager.resolve_path(config_manager.config["pairing"]["folder_ir"])
    results = service.inspect_folders(folder_2d, folder_ir, save=not args.no_save)
    print(f"Detected {len(results)} bag records")
    for result in results:
        reasons = "; ".join(result.ng_reasons) if result.ng_reasons else "OK"
        print(f"{result.pair.bag_id}: 2D={result.result_2d.result}, IR={result.result_ir.result}, FINAL={result.final_result}, {reasons}")
    return 0


def run_ui() -> int:
    try:
        from PyQt5.QtWidgets import QApplication
        from ui.main_window import MainWindow
    except ImportError as exc:
        print("PyQt5 is not installed. Install requirements or run with --batch.")
        print(exc)
        return 1

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec_()


def main() -> int:
    parser = argparse.ArgumentParser(description="Multimodal Seal Quality Inspection System")
    parser.add_argument("--batch", action="store_true", help="run folder pairing and detection without UI")
    parser.add_argument("--config", default=None, help="path to config.json")
    parser.add_argument("--folder-2d", default=None, help="2D image folder")
    parser.add_argument("--folder-ir", default=None, help="infrared image folder")
    parser.add_argument("--no-save", action="store_true", help="do not write logs or NG artifacts in batch mode")
    args = parser.parse_args()
    if args.batch:
        return run_batch(args)
    return run_ui()


if __name__ == "__main__":
    raise SystemExit(main())

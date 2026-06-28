from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List


class IOController:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.history: List[Dict[str, Any]] = []
        self.state = {
            "ok_signal": False,
            "ng_signal": False,
            "alarm_on": False,
            "reject_triggered": False,
            "last_event": "",
        }

    def output(self, final_result: str, bag_id: str = "") -> Dict[str, Any]:
        is_ng = final_result == "NG"
        self.state = {
            "ok_signal": not is_ng,
            "ng_signal": is_ng,
            "alarm_on": is_ng,
            "reject_triggered": is_ng,
            "last_event": f"{bag_id}:{final_result}",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "simulate": bool(self.config.get("simulate", True)),
        }
        self.history.append(self.state.copy())
        return self.state.copy()

    def reset(self) -> None:
        self.state.update({
            "ok_signal": False,
            "ng_signal": False,
            "alarm_on": False,
            "reject_triggered": False,
            "last_event": "RESET",
        })


from typing import Any
from src.terminal.state_machine import Terminal


class TerminalManager:
    def __init__(self, mqtt_client: Any, config: Any):
        self.terminals: dict[str, Terminal] = {}
        for tid in ["ST-01", "ST-02", "ST-03"]:
            self.terminals[tid] = Terminal(tid, mqtt_client, config)

    def get_terminal(self, terminal_id: str) -> Terminal | None:
        return self.terminals.get(terminal_id)

    def get_all_terminals(self) -> list[Terminal]:
        return list(self.terminals.values())

    async def start(self) -> None:
        for t in self.terminals.values():
            t.publish_status()

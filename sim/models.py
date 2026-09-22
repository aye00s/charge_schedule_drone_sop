"""Phase 4 state-only data classes: UAV, Station, Mission. No behavior --
the engine (sim/mission_sim.py) owns all state transitions."""

from dataclasses import dataclass, field


@dataclass
class Mission:
    id: int
    destination: tuple
    release_time: float
    deadline: float
    assigned_uav: int = None
    completed_time: float = None


@dataclass
class UAV:
    id: int
    position: tuple
    battery_wh: float
    soc: float = 1.0
    state: str = "IDLE"  # IDLE, FLYING_MISSION, FLYING_TO_STATION, WAITING_FOR_PAD, CHARGING
    mission_id: int = None
    station_id: int = None
    charge_target: float = 1.0
    charge_start_soc: float = None
    charge_start_time: float = None
    dest: tuple = None


@dataclass
class Station:
    id: int
    position: tuple
    num_pads: int
    pads_busy: int = 0
    queue: list = field(default_factory=list)

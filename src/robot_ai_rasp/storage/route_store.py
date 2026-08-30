from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class HomePose:
    x_mm: float
    y_mm: float
    heading_rad: float
    reset_generation: int
    updated_at: float


@dataclass(frozen=True, slots=True)
class RoutePoint:
    index: int
    x_mm: float
    y_mm: float
    heading_rad: float


class RouteStore:
    """Persistent map/route database moved out of ESP32 RAM/NVS."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self._migrate()

    def _migrate(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS home_pose (
              singleton INTEGER PRIMARY KEY CHECK(singleton=1),
              x_mm REAL NOT NULL,
              y_mm REAL NOT NULL,
              heading_rad REAL NOT NULL,
              reset_generation INTEGER NOT NULL,
              updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS routes (
              name TEXT PRIMARY KEY,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS route_points (
              route_name TEXT NOT NULL,
              point_index INTEGER NOT NULL,
              x_mm REAL NOT NULL,
              y_mm REAL NOT NULL,
              heading_rad REAL NOT NULL,
              PRIMARY KEY(route_name, point_index),
              FOREIGN KEY(route_name) REFERENCES routes(name) ON DELETE CASCADE
            );
            """
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def set_home(self, x_mm: float, y_mm: float, heading_rad: float, reset_generation: int) -> HomePose:
        now = time.time()
        self.db.execute(
            "INSERT INTO home_pose(singleton,x_mm,y_mm,heading_rad,reset_generation,updated_at) "
            "VALUES(1,?,?,?,?,?) ON CONFLICT(singleton) DO UPDATE SET "
            "x_mm=excluded.x_mm,y_mm=excluded.y_mm,heading_rad=excluded.heading_rad,"
            "reset_generation=excluded.reset_generation,updated_at=excluded.updated_at",
            (x_mm, y_mm, heading_rad, int(reset_generation), now),
        )
        self.db.commit()
        return HomePose(x_mm, y_mm, heading_rad, int(reset_generation), now)

    def get_home(self) -> HomePose | None:
        row = self.db.execute(
            "SELECT x_mm,y_mm,heading_rad,reset_generation,updated_at FROM home_pose WHERE singleton=1"
        ).fetchone()
        return HomePose(*row) if row else None

    def save_route(self, name: str, points: list[RoutePoint]) -> None:
        if not name or len(name) > 64:
            raise ValueError("invalid route name")
        now = time.time()
        with self.db:
            self.db.execute(
                "INSERT INTO routes(name,created_at,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET updated_at=excluded.updated_at",
                (name, now, now),
            )
            self.db.execute("DELETE FROM route_points WHERE route_name=?", (name,))
            self.db.executemany(
                "INSERT INTO route_points(route_name,point_index,x_mm,y_mm,heading_rad) VALUES(?,?,?,?,?)",
                [(name, p.index, p.x_mm, p.y_mm, p.heading_rad) for p in points],
            )

    def load_route(self, name: str) -> list[RoutePoint]:
        rows = self.db.execute(
            "SELECT point_index,x_mm,y_mm,heading_rad FROM route_points WHERE route_name=? ORDER BY point_index",
            (name,),
        ).fetchall()
        return [RoutePoint(*row) for row in rows]

    def list_routes(self) -> list[str]:
        return [row[0] for row in self.db.execute("SELECT name FROM routes ORDER BY name")]

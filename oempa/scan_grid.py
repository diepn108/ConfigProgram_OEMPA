import csv
import json
from pathlib import Path

import numpy as np


class ScanGrid:
    def __init__(
        self,
        scan_dir,
        x_positions,
        y_positions,
        overwrite=False,
    ):
        self.scan_dir = Path(scan_dir)

        self.x_positions = np.asarray(
            x_positions,
            dtype=float,
        )

        self.y_positions = np.asarray(
            y_positions,
            dtype=float,
        )

        if self.x_positions.ndim != 1:
            raise ValueError(
                "x_positions must be one-dimensional."
            )

        if self.y_positions.ndim != 1:
            raise ValueError(
                "y_positions must be one-dimensional."
            )

        if self.x_positions.size == 0:
            raise ValueError(
                "x_positions cannot be empty."
            )

        if self.y_positions.size == 0:
            raise ValueError(
                "y_positions cannot be empty."
            )

        self.fmc_dir = (
            self.scan_dir
            / "fmc"
        )

        self.metadata_path = (
            self.scan_dir
            / "metadata.json"
        )

        self.positions_path = (
            self.scan_dir
            / "positions.csv"
        )

        self.overwrite = bool(
            overwrite
        )

        self._create_directories()
        self._write_metadata()
        self._initialize_positions_file()

    @property
    def x_count(self):
        return len(
            self.x_positions
        )

    @property
    def y_count(self):
        return len(
            self.y_positions
        )

    @property
    def position_count(self):
        return (
            self.x_count
            * self.y_count
        )

    def _create_directories(self):
        self.scan_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.fmc_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    def _write_metadata(self):
        metadata = {
            "x_positions": (
                self.x_positions.tolist()
            ),
            "y_positions": (
                self.y_positions.tolist()
            ),
            "x_count": self.x_count,
            "y_count": self.y_count,
            "position_count": (
                self.position_count
            ),
        }

        if (
            self.metadata_path.exists()
            and not self.overwrite
        ):
            return

        with self.metadata_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                metadata,
                file,
                indent=4,
            )

    def _initialize_positions_file(self):
        if (
            self.positions_path.exists()
            and not self.overwrite
        ):
            return

        with self.positions_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.writer(
                file
            )

            writer.writerow(
                [
                    "x_index",
                    "y_index",
                    "x_position",
                    "y_position",
                    "file",
                ]
            )

    def _validate_indices(
        self,
        x_index,
        y_index,
    ):
        x_index = int(
            x_index
        )

        y_index = int(
            y_index
        )

        if not (
            0
            <= x_index
            < self.x_count
        ):
            raise IndexError(
                f"Invalid X index: {x_index}"
            )

        if not (
            0
            <= y_index
            < self.y_count
        ):
            raise IndexError(
                f"Invalid Y index: {y_index}"
            )

        return (
            x_index,
            y_index,
        )

    def get_fmc_path(
        self,
        x_index,
        y_index,
    ):
        x_index, y_index = (
            self._validate_indices(
                x_index,
                y_index,
            )
        )

        filename = (
            f"y{y_index:04d}_"
            f"x{x_index:04d}.npy"
        )

        return (
            self.fmc_dir
            / filename
        )

    def is_complete(
        self,
        x_index,
        y_index,
    ):
        return self.get_fmc_path(
            x_index,
            y_index,
        ).exists()

    def save_fmc(
        self,
        x_index,
        y_index,
        fmc_data,
    ):
        x_index, y_index = (
            self._validate_indices(
                x_index,
                y_index,
            )
        )

        path = self.get_fmc_path(
            x_index,
            y_index,
        )

        if (
            path.exists()
            and not self.overwrite
        ):
            raise FileExistsError(
                f"FMC data already exists: {path}"
            )

        if hasattr(
            fmc_data,
            "data",
        ):
            array = np.asarray(
                fmc_data.data
            )
        else:
            array = np.asarray(
                fmc_data
            )

        if array.ndim != 3:
            raise ValueError(
                "FMC data must have shape "
                "(TX, RX, samples)."
            )

        np.save(
            path,
            array,
        )

        x_position = float(
            self.x_positions[
                x_index
            ]
        )

        y_position = float(
            self.y_positions[
                y_index
            ]
        )

        with self.positions_path.open(
            "a",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.writer(
                file
            )

            writer.writerow(
                [
                    x_index,
                    y_index,
                    x_position,
                    y_position,
                    path.name,
                ]
            )

        return path

    def load_fmc(
        self,
        x_index,
        y_index,
    ):
        path = self.get_fmc_path(
            x_index,
            y_index,
        )

        if not path.exists():
            raise FileNotFoundError(
                f"No FMC data at "
                f"X={x_index}, "
                f"Y={y_index}."
            )

        return np.load(
            path
        )

    def completed_mask(self):
        mask = np.zeros(
            (
                self.y_count,
                self.x_count,
            ),
            dtype=bool,
        )

        for y_index in range(
            self.y_count
        ):
            for x_index in range(
                self.x_count
            ):
                mask[
                    y_index,
                    x_index,
                ] = self.is_complete(
                    x_index,
                    y_index,
                )

        return mask

    def completed_count(self):
        return int(
            self.completed_mask().sum()
        )

    def next_incomplete(self):
        for y_index in range(
            self.y_count
        ):
            for x_index in range(
                self.x_count
            ):
                if not self.is_complete(
                    x_index,
                    y_index,
                ):
                    return (
                        x_index,
                        y_index,
                    )

        return None
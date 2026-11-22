"""PySide6 window for the AG06MK2 / AG03MK2 safe-subset controls."""
from __future__ import annotations

import math
import shutil
import subprocess
import sys

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QApplication, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMainWindow,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from .. import __version__
from .. import protocol as p
from ..device import Device, DeviceError, is_present

METER_FLOOR_DB = -60.0
METERS = (
    ("ch1_in", "CH1\nIN"), ("ch2_in", "CH2\nIN"),
    ("ch1_out", "CH1\nOUT"), ("ch2_out", "CH2\nOUT"),
    ("fx_l", "FX\nL"), ("fx_r", "FX\nR"),
    ("master_l", "MAIN\nL"), ("master_r", "MAIN\nR"),
)


class Bridge(QObject):
    status = Signal(object)


class MeterBar(QWidget):
    def __init__(self):
        super().__init__()
        self.level = METER_FLOOR_DB
        self.peak = METER_FLOOR_DB
        self.setMinimumSize(14, 160)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

    def set_db(self, db: float) -> None:
        db = max(METER_FLOOR_DB, db if db != -math.inf else METER_FLOOR_DB)
        self.level = db if db > self.level else max(db, self.level - 1.5)   # smooth fall
        self.peak = max(self.peak - 0.3, self.level)
        self.update()

    def _y(self, db: float) -> float:
        return self.height() * (db / METER_FLOOR_DB)

    def paintEvent(self, _e):
        qp = QPainter(self)
        r = self.rect()
        qp.fillRect(r, QColor("#1b1b1b"))
        grad = QLinearGradient(0, r.height(), 0, 0)
        grad.setColorAt(0.0, QColor("#2e9e4a"))
        grad.setColorAt(0.75, QColor("#d9c63a"))
        grad.setColorAt(1.0, QColor("#e0412b"))
        top = self._y(self.level)
        qp.fillRect(QRectF(1, top, r.width() - 2, r.height() - top), grad)
        qp.fillRect(QRectF(1, self._y(self.peak), r.width() - 2, 2), QColor("#f0f0f0"))
        qp.setPen(QColor("#555"))
        for db in (-6, -12, -24, -48):
            y = self._y(db)
            qp.drawLine(0, int(y), 3, int(y))


class ToggleButton(QPushButton):
    def __init__(self, text: str):
        super().__init__(text)
        self.setCheckable(True)
        self.setMinimumHeight(44)
        self.setStyleSheet(
            "QPushButton{background:#333;color:#ddd;border:1px solid #555;border-radius:6px;padding:6px}"
            "QPushButton:checked{background:#2f7d46;color:white;border-color:#4fc16f}"
            "QPushButton:disabled{color:#666}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AG Mixer Control")
        self.setWindowIcon(QIcon.fromTheme("agctl", QIcon.fromTheme("audio-card")))
        self.dev: Device | None = None
        self.bridge = Bridge()
        self.bridge.status.connect(self._apply_status)
        self._updating = False

        central = QWidget()
        root = QVBoxLayout(central)

        self.state_label = QLabel("Searching for AG06MK2 / AG03MK2…")
        f = QFont(); f.setPointSize(13); f.setBold(True)
        self.state_label.setFont(f)
        root.addWidget(self.state_label)

        sw_box = QGroupBox("Switches")
        grid = QGridLayout(sw_box)
        self.switch_buttons: dict[str, ToggleButton] = {}
        for i, (name, (_, _, label)) in enumerate(p.SWITCHES.items()):
            b = ToggleButton(label)
            b.toggled.connect(lambda on, n=name: self._on_switch(n, on))
            self.switch_buttons[name] = b
            grid.addWidget(b, i // 2, i % 2)
        root.addWidget(sw_box)

        foot_box = QGroupBox("Assignable foot switch")
        fl = QHBoxLayout(foot_box)
        self.foot = QComboBox()
        for k, v in p.FOOTSWITCH_FUNCTIONS.items():
            self.foot.addItem(v, k)
        self.foot.currentIndexChanged.connect(self._on_foot)
        fl.addWidget(self.foot)
        root.addWidget(foot_box)

        meter_box = QGroupBox("Levels (dBFS)")
        ml = QHBoxLayout(meter_box)
        self.meters: dict[str, MeterBar] = {}
        for key, label in METERS:
            col = QVBoxLayout()
            bar = MeterBar()
            self.meters[key] = bar
            col.addWidget(bar, 1, Qt.AlignHCenter)
            lab = QLabel(label); lab.setAlignment(Qt.AlignCenter)
            lab.setStyleSheet("color:#aaa;font-size:9px")
            col.addWidget(lab)
            ml.addLayout(col)
        root.addWidget(meter_box, 1)

        bottom = QHBoxLayout()
        self.full_btn = QPushButton("EQ / Comp / Reverb… (Yamaha editor)")
        self.full_btn.setToolTip("Opens Yamaha AG Controller (Windows version under Wine) for DSP editing")
        self.full_btn.clicked.connect(self._open_full_editor)
        self.full_btn.setVisible(shutil.which("ag-controller") is not None)
        bottom.addWidget(self.full_btn)
        bottom.addStretch(1)
        ver = QLabel(f"agctl {__version__}"); ver.setStyleSheet("color:#777")
        bottom.addWidget(ver)
        root.addLayout(bottom)

        self.setCentralWidget(central)
        self.resize(460, 560)
        self._set_controls_enabled(False)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(2000)
        QTimer.singleShot(0, self._tick)

    # -- connection management ---------------------------------------------
    def _set_controls_enabled(self, on: bool) -> None:
        for b in self.switch_buttons.values():
            b.setEnabled(on)
        self.foot.setEnabled(on)

    def _tick(self) -> None:
        if self.dev and not self.dev.alive():
            self._disconnect("Mixer disconnected. Waiting for it…")
        if self.dev is None and is_present():
            self._connect()
        elif self.dev and self.dev.last_status is None:
            try:
                self.dev.start_meters()
            except DeviceError:
                pass

    def _connect(self) -> None:
        dev = Device("agctl")
        dev.on_status = self.bridge.status.emit
        try:
            model = dev.open()
            dev.start_meters()
        except DeviceError as e:
            dev.close()
            self.state_label.setText(str(e))
            return
        self.dev = dev
        self.state_label.setText(f"● Connected: {model}")
        self.state_label.setStyleSheet("color:#4fc16f")

    def _disconnect(self, text: str) -> None:
        if self.dev:
            self.dev.close()
        self.dev = None
        self._set_controls_enabled(False)
        self.state_label.setText(text)
        self.state_label.setStyleSheet("color:#d0a030")
        for m in self.meters.values():
            m.set_db(-math.inf)

    # -- status in / commands out -------------------------------------------
    def _apply_status(self, st: p.Status) -> None:
        if self.dev is None:
            return
        self._updating = True
        try:
            self._set_controls_enabled(True)
            for name, on in st.switches.items():
                b = self.switch_buttons[name]
                if b.isChecked() != on:
                    b.setChecked(on)
            idx = self.foot.findData(st.footswitch)
            if idx >= 0 and idx != self.foot.currentIndex():
                self.foot.setCurrentIndex(idx)
        finally:
            self._updating = False
        for key, bar in self.meters.items():
            bar.set_db(st.meters_db.get(key, -math.inf))

    def _on_switch(self, name: str, on: bool) -> None:
        if self._updating or not self.dev:
            return
        try:
            self.dev.set_switch(name, on)
        except DeviceError as e:
            self.state_label.setText(f"Could not change switch: {e}")

    def _on_foot(self, _idx: int) -> None:
        if self._updating or not self.dev:
            return
        try:
            self.dev.set_footswitch(self.foot.currentData())
        except DeviceError as e:
            self.state_label.setText(f"Could not set foot switch: {e}")

    def _open_full_editor(self) -> None:
        exe = shutil.which("ag-controller")
        if exe:
            subprocess.Popen([exe], start_new_session=True)

    def closeEvent(self, e):
        if self.dev:
            self.dev.close()
        super().closeEvent(e)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("agctl")
    app.setDesktopFileName("agctl")
    app.setStyle("Fusion")
    pal = app.palette()
    for role, col in ((pal.ColorRole.Window, "#262626"), (pal.ColorRole.WindowText, "#e6e6e6"),
                      (pal.ColorRole.Base, "#1e1e1e"), (pal.ColorRole.Text, "#e6e6e6"),
                      (pal.ColorRole.Button, "#333333"), (pal.ColorRole.ButtonText, "#e6e6e6")):
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

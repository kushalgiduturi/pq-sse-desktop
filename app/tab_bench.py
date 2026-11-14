"""Benchmarks tab: BuildIndex CPU vs GPU with a chart and a table, per event operations for
all parameter sets, CSV export. Every number is measured on this machine."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCharts import QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QLogValueAxis
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QFileDialog, QGroupBox, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSplitter,
                               QVBoxLayout)

from pqsse import bench
from pqsse.pqbackend import PARAM_SETS

from .common import TabBase, fill_table, make_table

NOTE = ("What the GPU does here: only the symmetric batch work of BuildIndex, that is the HMAC-SHA3-256 address and "
        "mask derivation and the batched hash chain levels. Document encryption (AES-GCM), ML-DSA signatures and "
        "the cloud store run on the CPU, and ML-KEM / ML-DSA are never on the GPU. The chart shows both the "
        "symmetric phase and the whole BuildIndex so the real end to end effect is visible.")


class BenchTab(TabBase):
    def __init__(self, session, runner) -> None:
        super().__init__(session, runner)
        self.build_rows: list[dict] = []
        self.op_rows: list[dict] = []
        run_build = QPushButton("Run BuildIndex benchmark (1k, 10k, 100k)")
        run_ops = QPushButton("Run operation benchmarks (3 parameter sets)")
        export = QPushButton("Export CSV")
        run_build.clicked.connect(lambda: self.run_build())
        run_ops.clicked.connect(lambda: self.run_ops())
        export.clicked.connect(lambda: self.export_dialog())
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.stage = QLabel("")
        buttons = QHBoxLayout()
        for widget in (run_build, run_ops, export):
            buttons.addWidget(widget)
        buttons.addWidget(self.bar, 1)

        self.chart = QChart()
        self.chart.setTitle("BuildIndex time, CPU vs GPU (log scale, seconds)")
        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.build_table = make_table(["Occurrences", "Engine", "PRF s", "Chain s", "Documents s", "Batch sign s",
                                       "Cloud store s", "Total s", "PRF speedup", "Symmetric speedup", "Total speedup"])
        self.ops_table = make_table(["Operation"] + [p.label() for p in PARAM_SETS])
        build_box = QGroupBox("BuildIndex: CPU vs GPU")
        build_layout = QVBoxLayout(build_box)
        build_layout.addWidget(self.chart_view, 3)
        build_layout.addWidget(self.build_table, 2)
        ops_box = QGroupBox("Per event operations (milliseconds, CPU)")
        ops_layout = QVBoxLayout(ops_box)
        ops_layout.addWidget(self.ops_table)
        splitter = QSplitter()
        splitter.addWidget(build_box)
        splitter.addWidget(ops_box)
        splitter.setSizes([700, 480])
        note = QLabel(NOTE)
        note.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(note)
        layout.addLayout(buttons)
        layout.addWidget(self.stage)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.message)

    def _progress(self, progress):
        def report(message: str, fraction: float) -> None:
            progress(message, fraction)
        return report

    def on_progress(self, message: str, fraction: float) -> None:
        if message.startswith(("BuildIndex", "ML-KEM", "Operation")):
            self.stage.setText(message)
            self.bar.setValue(int(fraction * 1000))

    # ------------------------------------------------------------------ BuildIndex
    def run_build(self, sizes: tuple[int, ...] = bench.BUILD_SIZES) -> None:
        def done(rows: list[dict]) -> None:
            self.build_rows = rows
            self.show_build()
            gpu_rows = [r for r in rows if r["engine"] == "GPU"]
            if gpu_rows:
                best = gpu_rows[-1]
                self.notify(f"Measured at {best['occurrences']:,} occurrences: PRF phase {best['prf_speedup']:.1f}x, "
                            f"symmetric phase {best['symmetric_speedup']:.1f}x, whole BuildIndex {best['total_speedup']:.2f}x.")
            else:
                self.notify("No usable GPU: only CPU numbers were measured.")

        self.task(lambda p: bench.run_build_benchmarks(sizes, self._progress(p)), done, "Benchmark: BuildIndex", locked=False)

    def show_build(self) -> None:
        fill_table(self.build_table, [
            [f"{r['occurrences']:,}", r["engine"], f"{r['prf_s']:.4f}", f"{r['chain_s']:.4f}", f"{r['documents_s']:.4f}",
             f"{r['batch_sign_s']:.4f}", f"{r['cloud_store_s']:.4f}", f"{r['total_s']:.4f}",
             f"{r.get('prf_speedup', 1.0):.2f}x", f"{r.get('symmetric_speedup', 1.0):.2f}x", f"{r.get('total_speedup', 1.0):.2f}x"]
            for r in self.build_rows])
        self.chart.removeAllSeries()
        for axis in list(self.chart.axes()):
            self.chart.removeAxis(axis)
        sizes = sorted({r["occurrences"] for r in self.build_rows})
        if not sizes:
            return
        series = QBarSeries()
        colors = {"CPU symmetric": "#4c78a8", "GPU symmetric": "#54a24b", "CPU total": "#9ecae9", "GPU total": "#b6e3a8"}
        values = [1e-4]
        for engine in ("CPU", "GPU"):
            rows = {r["occurrences"]: r for r in self.build_rows if r["engine"] == engine}
            if not rows:
                continue
            for kind in ("symmetric", "total"):
                bar = QBarSet(f"{engine} {kind}" + (" (PRF + chain)" if kind == "symmetric" else " BuildIndex"))
                bar.setColor(QColor(colors[f"{engine} {kind}"]))
                for n in sizes:
                    r = rows.get(n)
                    value = 0.0 if r is None else (r["prf_s"] + r["chain_s"] if kind == "symmetric" else r["total_s"])
                    bar.append(max(value, 1e-5))
                    values.append(max(value, 1e-5))
                series.append(bar)
        self.chart.addSeries(series)
        axis_x = QBarCategoryAxis()
        axis_x.append([f"{n:,} occurrences" for n in sizes])
        axis_y = QLogValueAxis()
        axis_y.setBase(10)
        axis_y.setLabelFormat("%.4g s")
        axis_y.setRange(min(values) / 2, max(values) * 2)
        self.chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        self.chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)

    # ------------------------------------------------------------------ operations
    def run_ops(self, param_sets=PARAM_SETS, repeats: int = 3) -> None:
        def done(rows: list[dict]) -> None:
            self.op_rows = rows
            self.show_ops()
            self.notify(f"Operation benchmarks done with backend: {rows[0]['backend']}." if rows else "No rows.")

        self.task(lambda p: bench.run_operation_benchmarks(param_sets, repeats, self._progress(p)), done,
                  "Benchmark: operations", locked=False)

    def show_ops(self) -> None:
        names: list[str] = []
        for row in self.op_rows:
            if row["operation"] not in names:
                names.append(row["operation"])
        lookup = {(r["operation"], r["kem"]): r["milliseconds"] for r in self.op_rows}
        fill_table(self.ops_table, [[name] + [f"{lookup[(name, p.kem)]:.2f}" if (name, p.kem) in lookup else ""
                                              for p in PARAM_SETS] for name in names])

    # ------------------------------------------------------------------ export
    def export_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Export benchmark CSV files to folder")
        if folder:
            self.export_csv(Path(folder))

    def export_csv(self, folder: Path) -> list[Path]:
        written = []
        if self.build_rows:
            bench.write_csv(folder / "buildindex.csv", self.build_rows, bench.BUILD_COLUMNS)
            written.append(folder / "buildindex.csv")
        if self.op_rows:
            bench.write_csv(folder / "operations.csv", self.op_rows, bench.OPS_COLUMNS)
            written.append(folder / "operations.csv")
        if written:
            self.notify("Exported: " + ", ".join(str(p) for p in written))
        else:
            self.notify("Run a benchmark first, there is nothing to export.", error=True)
        return written

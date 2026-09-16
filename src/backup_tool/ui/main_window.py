from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backup_tool.storage.database import AppDatabase, DashboardSummary


class MainWindow(QMainWindow):
    def __init__(self, database: AppDatabase) -> None:
        super().__init__()
        self.database = database

        self.setWindowTitle("Backup Tool")
        self.resize(1180, 740)
        self.setMinimumSize(980, 620)

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_sidebar())
        root_layout.addWidget(self._build_content(), 1)

        self.setCentralWidget(root)
        self.setStyleSheet(APP_STYLESHEET)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(238)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 22, 20, 22)
        layout.setSpacing(12)

        title = QLabel("Backup Tool")
        title.setObjectName("brandTitle")
        subtitle = QLabel("MSSQL cloud backups")
        subtitle.setObjectName("brandSubtitle")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(18)

        for label in ("Dashboard", "Backup Jobs", "SQL Servers", "Cloud", "History", "Settings"):
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            layout.addWidget(button)

        layout.addStretch(1)

        status = QLabel("Ready")
        status.setObjectName("sidebarStatus")
        layout.addWidget(status)
        return sidebar

    def _build_content(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        header = QHBoxLayout()
        header_text = QVBoxLayout()

        page_title = QLabel("Dashboard")
        page_title.setObjectName("pageTitle")
        page_subtitle = QLabel("Local MSSQL backups first, cloud upload after a verified file exists.")
        page_subtitle.setObjectName("pageSubtitle")

        header_text.addWidget(page_title)
        header_text.addWidget(page_subtitle)
        header.addLayout(header_text, 1)

        add_job = QPushButton("New backup job")
        add_job.setObjectName("primaryButton")
        add_job.setCursor(Qt.CursorShape.PointingHandCursor)
        header.addWidget(add_job)

        layout.addLayout(header)
        layout.addLayout(self._build_summary_grid(self.database.dashboard_summary()))

        stack = QStackedWidget()
        stack.addWidget(self._build_placeholder_panel())
        layout.addWidget(stack, 1)

        return container

    def _build_summary_grid(self, summary: DashboardSummary) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(14)
        grid.addWidget(self._summary_tile("Jobs", str(summary.job_count)), 0, 0)
        grid.addWidget(self._summary_tile("Cloud destinations", str(summary.destination_count)), 0, 1)
        grid.addWidget(self._summary_tile("Successful runs", str(summary.successful_runs)), 0, 2)
        grid.addWidget(self._summary_tile("Failed runs", str(summary.failed_runs)), 0, 3)
        return grid

    def _summary_tile(self, label: str, value: str) -> QWidget:
        tile = QFrame()
        tile.setObjectName("summaryTile")
        tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        tile.setMinimumHeight(104)

        layout = QVBoxLayout(tile)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        value_label = QLabel(value)
        value_label.setObjectName("summaryValue")
        text_label = QLabel(label)
        text_label.setObjectName("summaryLabel")

        layout.addWidget(value_label)
        layout.addWidget(text_label)
        return tile

    def _build_placeholder_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("mainPanel")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel("Next build step")
        title.setObjectName("panelTitle")
        body = QLabel(
            "Add the first wizard for SQL Server connection, database selection, "
            "local backup folder, and rclone cloud destination."
        )
        body.setObjectName("panelBody")
        body.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(body)
        layout.addStretch(1)
        return panel


APP_STYLESHEET = """
QWidget {
    background: #f5f7fb;
    color: #18212f;
    font-family: "Segoe UI";
    font-size: 14px;
}

#sidebar {
    background: #111827;
}

#brandTitle {
    color: #ffffff;
    font-size: 23px;
    font-weight: 700;
}

#brandSubtitle, #sidebarStatus {
    color: #94a3b8;
}

#navButton {
    background: transparent;
    color: #d7dee9;
    border: none;
    border-radius: 7px;
    text-align: left;
    padding: 11px 12px;
}

#navButton:hover {
    background: #1f2937;
    color: #ffffff;
}

#pageTitle {
    font-size: 28px;
    font-weight: 700;
}

#pageSubtitle {
    color: #667085;
}

#primaryButton {
    background: #2563eb;
    color: #ffffff;
    border: none;
    border-radius: 7px;
    padding: 11px 16px;
    font-weight: 600;
}

#primaryButton:hover {
    background: #1d4ed8;
}

#summaryTile, #mainPanel {
    background: #ffffff;
    border: 1px solid #e3e8ef;
    border-radius: 8px;
}

#summaryValue {
    font-size: 27px;
    font-weight: 700;
}

#summaryLabel {
    color: #667085;
}

#panelTitle {
    font-size: 18px;
    font-weight: 700;
}

#panelBody {
    color: #475467;
    line-height: 1.45;
}
"""


def run_app(database: AppDatabase) -> int:
    app = QApplication(sys.argv)
    window = MainWindow(database)
    window.show()
    return app.exec()

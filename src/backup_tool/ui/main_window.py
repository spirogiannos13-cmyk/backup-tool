from __future__ import annotations

import sys
from pathlib import Path
from xmlrpc import server

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backup_tool.cloud.rclone import (
    RcloneDestination,
    find_rclone,
    list_remotes,
)
from backup_tool.mssql.backup import SqlServerConnection
from backup_tool.services.backup_service import BackupRequest, BackupService
from backup_tool.mssql.database_browser import list_databases
from backup_tool.mssql.udl import udl_to_fields
from backup_tool.security.credentials import (
    load_sql_password,
    save_sql_password,
)
from backup_tool.storage.database import (
    AppDatabase,
    BackupRunRecord,
    CloudDestinationRecord,
    DashboardSummary,
    SqlServerRecord,
)


class MainWindow(QMainWindow):
    def __init__(self, database: AppDatabase) -> None:
        super().__init__()
        self.database = database
        self.backup_service = BackupService(database)
        self.editing_sql_server_id: int | None = None
        self.editing_backup_job_id: int | None = None
        self.editing_cloud_destination_id: int | None = None
        self.setWindowTitle("Backup Tool")
        self.resize(1180, 740)
        self.setMinimumSize(980, 620)

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.stack = QStackedWidget()
        self.nav_buttons: dict[str, QPushButton] = {}
        self.sidebar_status = QLabel("Ready")

        root_layout.addWidget(self._build_sidebar())
        root_layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.setStyleSheet(APP_STYLESHEET)

        self._add_pages()
        self._select_page("Dashboard")

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(238)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 22, 20, 22)
        layout.setSpacing(8)

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
            button.clicked.connect(lambda _checked=False, name=label: self._select_page(name))
            self.nav_buttons[label] = button
            layout.addWidget(button)

        layout.addStretch(1)
        self.sidebar_status.setObjectName("sidebarStatus")
        layout.addWidget(self.sidebar_status)
        return sidebar

    def _add_pages(self) -> None:
        self.stack.addWidget(self._build_dashboard_page())
        self.stack.addWidget(self._build_backup_jobs_page())
        self.stack.addWidget(self._build_sql_servers_page())
        self.stack.addWidget(self._build_cloud_page())
        self.stack.addWidget(self._build_history_page())
        self.stack.addWidget(self._build_placeholder_page("Settings", "Application settings will be shown here."))

    def _select_page(self, name: str) -> None:
        names = list(self.nav_buttons)
        index = names.index(name)
        self.stack.setCurrentIndex(index)
        for label, button in self.nav_buttons.items():
            button.setProperty("active", label == name)
            button.style().unpolish(button)
            button.style().polish(button)
        if name == "Cloud":
            self._refresh_cloud_page()
        elif name == "SQL Servers":
            self._refresh_sql_servers_page()
        elif name == "Backup Jobs":
            self._refresh_backup_job_servers()
        elif name == "History":
            self._refresh_history_page()

    def _build_dashboard_page(self) -> QWidget:
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
        add_job.clicked.connect(lambda: self._select_page("Backup Jobs"))
        header.addWidget(add_job)
        layout.addLayout(header)
        layout.addLayout(self._build_summary_grid(self.database.dashboard_summary()))

        panel = QFrame()
        panel.setObjectName("mainPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(24, 22, 24, 22)
        panel_layout.setSpacing(12)
        title = QLabel("Cloud verification")
        title.setObjectName("panelTitle")
        body = QLabel(
            "Every cloud upload now runs through rclone copyto and a follow-up rclone check. "
            "A run is marked successful only after the remote copy is verified."
        )
        body.setObjectName("panelBody")
        body.setWordWrap(True)
        panel_layout.addWidget(title)
        panel_layout.addWidget(body)
        panel_layout.addStretch(1)
        layout.addWidget(panel, 1)
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
    def _build_backup_jobs_page(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        title = QLabel("Backup Jobs")
        title.setObjectName("pageTitle")

        subtitle = QLabel(
            "Create and manage backup jobs for your saved SQL Server profiles."
        )
        subtitle.setObjectName("pageSubtitle")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        panel = QFrame()
        panel.setObjectName("mainPanel")

        form = QGridLayout(panel)
        form.setContentsMargins(22, 20, 22, 20)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)

        # Job name
        self.job_name = QLineEdit()
        self.job_name.setPlaceholderText("e.g. ERP Production Daily")

        # SQL Server
        self.job_server = QComboBox()
        self.job_server.currentIndexChanged.connect(
            self._load_backup_job_databases
        )

        # Database
        self.job_database = QComboBox()
        self.job_database.setPlaceholderText("Select a database")

        # Backup type
        self.job_backup_type = QComboBox()
        self.job_backup_type.addItem("Full", "full")
        self.job_backup_type.addItem("Differential", "differential")
        self.job_backup_type.addItem("Log", "log")

        # Local folder
        self.job_local_folder = QLineEdit()
        self.job_local_folder.setPlaceholderText(
            "Folder where .bak files will be stored"
        )

        browse_folder = QPushButton("Browse...")
        browse_folder.setObjectName("secondaryButton")
        browse_folder.clicked.connect(self._browse_backup_job_folder)

        folder_row = QHBoxLayout()
        folder_row.addWidget(self.job_local_folder, 1)
        folder_row.addWidget(browse_folder)

        # Cloud destination
        self.job_cloud_destination = QComboBox()
        self.job_cloud_destination.addItem("No cloud destination", None)

        # Retention
        self.job_retention_days = QSpinBox()
        self.job_retention_days.setRange(1, 3650)
        self.job_retention_days.setValue(14)
        self.job_retention_days.setSuffix(" days")

        # Compression / checksum
        self.job_compression = QCheckBox("Enable compression")
        self.job_compression.setChecked(True)

        self.job_checksum = QCheckBox("Enable checksum")
        self.job_checksum.setChecked(True)

        form.addWidget(QLabel("Job name"), 0, 0)
        form.addWidget(self.job_name, 0, 1)

        form.addWidget(QLabel("SQL Server"), 1, 0)
        form.addWidget(self.job_server, 1, 1)

        form.addWidget(QLabel("Database"), 2, 0)
        form.addWidget(self.job_database, 2, 1)

        form.addWidget(QLabel("Backup type"), 3, 0)
        form.addWidget(self.job_backup_type, 3, 1)

        form.addWidget(QLabel("Local backup folder"), 4, 0)
        form.addLayout(folder_row, 4, 1)

        form.addWidget(QLabel("Cloud destination"), 5, 0)
        form.addWidget(self.job_cloud_destination, 5, 1)

        form.addWidget(QLabel("Retention"), 6, 0)
        form.addWidget(self.job_retention_days, 6, 1)

        options_row = QHBoxLayout()
        options_row.addWidget(self.job_compression)
        options_row.addWidget(self.job_checksum)
        options_row.addStretch(1)

        form.addWidget(QLabel("Options"), 7, 0)
        form.addLayout(options_row, 7, 1)

        self.job_save_button = QPushButton("Save Backup Job")
        self.job_save_button.setObjectName("primaryButton")
        self.job_save_button.clicked.connect(self._save_backup_job)

        self.job_cancel_button = QPushButton("Cancel")
        self.job_cancel_button.setObjectName("secondaryButton")
        self.job_cancel_button.clicked.connect(self._cancel_backup_job_edit)
        self.job_cancel_button.setVisible(False)

        job_buttons = QHBoxLayout()
        job_buttons.addStretch(1)
        job_buttons.addWidget(self.job_cancel_button)
        job_buttons.addWidget(self.job_save_button)

        form.addLayout(job_buttons, 8, 1)

        layout.addWidget(panel)

        jobs_title = QLabel("Saved Backup Jobs")
        jobs_title.setObjectName("panelTitle")
        layout.addWidget(jobs_title)

        self.backup_job_list = QVBoxLayout()
        layout.addLayout(self.backup_job_list)

        layout.addStretch(1)

        self._refresh_backup_jobs_page()

        return container
    def _build_sql_servers_page(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        title = QLabel("SQL Servers")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Connect like SSMS: direct SQL Server or an existing .udl connection file."
        )
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        panel = QFrame()
        panel.setObjectName("mainPanel")
        form = QGridLayout(panel)
        form.setContentsMargins(22, 20, 22, 20)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)

        self.sql_method = QComboBox()
        self.sql_method.addItem("Direct SQL Server", "direct")
        self.sql_method.addItem("UDL File", "udl")
        self.sql_method.currentIndexChanged.connect(self._update_sql_method)

        self.sql_name = QLineEdit()
        self.sql_name.setPlaceholderText("e.g. ERP Production")

        self.sql_host = QLineEdit()
        self.sql_host.setPlaceholderText("Server or IP")

        self.sql_instance = QLineEdit()
        self.sql_instance.setPlaceholderText("Optional instance, e.g. SQLEXPRESS")

        self.sql_port = QSpinBox()
        self.sql_port.setRange(0, 65535)
        self.sql_port.setSpecialValueText("Default")
        self.sql_port.setValue(0)

        self.sql_auth = QComboBox()
        self.sql_auth.addItem("Windows Authentication", "windows")
        self.sql_auth.addItem("SQL Server Authentication", "sql")
        self.sql_auth.currentIndexChanged.connect(self._update_sql_auth_fields)

        self.sql_username = QLineEdit("sa")
        self.sql_password = QLineEdit("Sun$up1")
        self.sql_password.setEchoMode(QLineEdit.EchoMode.Password)

        self.sql_database = QComboBox()
        self.sql_database.setEditable(True)
        self.sql_database.setPlaceholderText("Test connection to load databases")

        self.sql_udl = QLineEdit()
        self.sql_udl.setReadOnly(True)
        self.sql_udl.setPlaceholderText("Select a .udl file")
        browse = QPushButton("Browse...")
        browse.setObjectName("secondaryButton")
        browse.clicked.connect(self._browse_udl)
        udl_row = QHBoxLayout()
        udl_row.addWidget(self.sql_udl, 1)
        udl_row.addWidget(browse)

        form.addWidget(QLabel("Connection method"), 0, 0)
        form.addWidget(self.sql_method, 0, 1)
        form.addWidget(QLabel("Profile name"), 1, 0)
        form.addWidget(self.sql_name, 1, 1)
        form.addWidget(QLabel("Server"), 2, 0)
        form.addWidget(self.sql_host, 2, 1)
        form.addWidget(QLabel("Instance"), 3, 0)
        form.addWidget(self.sql_instance, 3, 1)
        form.addWidget(QLabel("Port"), 4, 0)
        form.addWidget(self.sql_port, 4, 1)
        form.addWidget(QLabel("Authentication"), 5, 0)
        form.addWidget(self.sql_auth, 5, 1)
        form.addWidget(QLabel("Username"), 6, 0)
        form.addWidget(self.sql_username, 6, 1)
        form.addWidget(QLabel("Password"), 7, 0)
        form.addWidget(self.sql_password, 7, 1)
        form.addWidget(QLabel("Database"), 8, 0)
        form.addWidget(self.sql_database, 8, 1)
        form.addWidget(QLabel("UDL file"), 9, 0)
        form.addLayout(udl_row, 9, 1)

        buttons = QHBoxLayout()
        test = QPushButton("Test Connection")
        test.setObjectName("secondaryButton")
        test.clicked.connect(self._test_sql_connection)
        load = QPushButton("Load Databases")
        load.setObjectName("secondaryButton")
        load.clicked.connect(self._load_sql_databases)
        self.sql_save_button = QPushButton("Save Server")
        self.sql_save_button.setObjectName("primaryButton")
        self.sql_save_button.clicked.connect(self._save_sql_server)
        self.sql_cancel_button = QPushButton("Cancel")
        self.sql_cancel_button.setObjectName("secondaryButton")
        self.sql_cancel_button.clicked.connect(self._cancel_sql_server_edit)
        self.sql_cancel_button.setVisible(False)
        buttons.addStretch(1)
        buttons.addWidget(test)
        buttons.addWidget(load)
        buttons.addWidget(self.sql_cancel_button)
        buttons.addWidget(self.sql_save_button)
        form.addLayout(buttons, 10, 1)

        layout.addWidget(panel)
        self.sql_server_list = QVBoxLayout()
        layout.addLayout(self.sql_server_list)
        layout.addStretch(1)

        self._update_sql_method()
        return container
    def _refresh_backup_job_servers(self) -> None:
        if not hasattr(self, "job_server"):
            return

        self.job_server.blockSignals(True)
        self.job_server.clear()

        servers: list[SqlServerRecord] = self.database.list_sql_servers()

        for server in servers:
            self.job_server.addItem(
                f"{server.name}  β€Ά  {server.server_address}",
                server.id,
            )

        self.job_server.blockSignals(False)

        if servers:
            self._load_backup_job_databases()
        else:
            self.job_database.clear()
            self.job_database.setPlaceholderText(
                "No saved SQL Servers"
            )

    def _load_backup_job_databases(self) -> None:
        if not hasattr(self, "job_server"):
            return

        server_id = self.job_server.currentData()
        if not server_id:
            self.job_database.clear()
            self.job_database.setPlaceholderText("Select a SQL Server first")
            return

        servers = self.database.list_sql_servers()
        server = next((item for item in servers if item.id == server_id), None)

        if server is None:
            self.job_database.clear()
            self.job_database.setPlaceholderText("SQL Server not found")
            return

        try:
            password = None

            password = None
            if server.auth_mode == "sql":
                password = load_sql_password(server.id)

            connection = SqlServerConnection(
                host=server.host,
                instance=server.instance,
                port=server.port,
                username=server.username if server.auth_mode == "sql" else None,
                password=password,
                database="master",
            )

            names = list_databases(connection)

        except Exception as exc:
            self.job_database.clear()
            self.job_database.setPlaceholderText("Could not load databases")
            QMessageBox.critical(
                self,
                "Database discovery failed",
                str(exc),
            )
            return

        self.job_database.clear()
        self.job_database.addItems(names)

        if names:
            self.job_database.setCurrentIndex(0)
        else:
            self.job_database.setPlaceholderText("No databases found")
    def _browse_backup_job_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select backup folder",
            str(Path.home()),
        )

        if not path:
            return

        self.job_local_folder.setText(path)

    def _save_backup_job(self) -> None:
        name = self.job_name.text().strip()
        server_id = self.job_server.currentData()
        database_name = self.job_database.currentText().strip()
        backup_type = self.job_backup_type.currentText().strip().lower()
        local_folder = self.job_local_folder.text().strip()

        if not name:
            QMessageBox.warning(
                self,
                "Missing information",
                "Please enter a backup job name.",
            )
            return

        if not server_id:
            QMessageBox.warning(
                self,
                "Missing information",
                "Please select a SQL Server.",
            )
            return

        if not database_name:
            QMessageBox.warning(
                self,
                "Missing information",
                "Please select a database.",
            )
            return

        if not local_folder:
            QMessageBox.warning(
                self,
                "Missing information",
                "Please select a local backup folder.",
            )
            return

        cloud_destination_id = self.job_cloud_destination.currentData()

        try:
            if self.editing_backup_job_id is not None:
                self.database.update_backup_job(
                    job_id=self.editing_backup_job_id,
                    name=name,
                    server_id=server_id,
                    database_name=database_name,
                    backup_type=backup_type,
                    local_folder=local_folder,
                    cloud_destination_id=cloud_destination_id,
                    retention_days=self.job_retention_days.value(),
                    compression_enabled=self.job_compression.isChecked(),
                    checksum_enabled=self.job_checksum.isChecked(),
                    schedule_notes="",
                )

                self.editing_backup_job_id = None
                self.job_save_button.setText("Save Backup Job")
                self.job_cancel_button.setVisible(False)

            else:
                self.database.add_backup_job(
                    name=name,
                    server_id=server_id,
                    database_name=database_name,
                    backup_type=backup_type,
                    local_folder=local_folder,
                    cloud_destination_id=cloud_destination_id,
                    retention_days=self.job_retention_days.value(),
                    compression_enabled=self.job_compression.isChecked(),
                    checksum_enabled=self.job_checksum.isChecked(),
                    schedule_notes="",
                )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Save Backup Job failed",
                str(exc),
            )
            return

        QMessageBox.information(
            self,
            "Backup Job saved",
            f"Backup job '{name}' was saved successfully.",
        )

        self.job_name.clear()
        self.job_local_folder.clear()
        self._refresh_backup_jobs_page()

    def _refresh_backup_jobs_page(self) -> None:
        if not hasattr(self, "backup_job_list"):
            return

        while self.backup_job_list.count():
            item = self.backup_job_list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        jobs = self.database.list_backup_jobs()

        if not jobs:
            label = QLabel("No backup jobs configured.")
            label.setStyleSheet("color: #888;")
            self.backup_job_list.addWidget(label)
            return

        for job in jobs:
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)

            layout = QVBoxLayout(frame)

            name = getattr(job, "name", "Unnamed Job")
            database_name = getattr(job, "database_name", "")
            backup_type = getattr(job, "backup_type", "")
            local_folder = getattr(job, "local_folder", "")
            retention_days = getattr(job, "retention_days", 0)

            layout.addWidget(QLabel(f"<b>{name}</b>"))
            layout.addWidget(
                QLabel(
                    f"Database: {database_name}  β€Ά  "
                    f"Type: {backup_type}"
                )
            )
            layout.addWidget(
                QLabel(
                    f"Local folder: {local_folder}  β€Ά  "
                    f"Retention: {retention_days} days"
                )
            )

            button_row = QHBoxLayout()

            run_button = QPushButton("Run Backup")
            run_button.setObjectName("primaryButton")
            run_button.clicked.connect(
                lambda _checked=False, job_id=job.id, job_name=name:
                self._run_backup_job(job_id, job_name)
            )

            edit_button = QPushButton("Edit")
            edit_button.setObjectName("secondaryButton")
            edit_button.clicked.connect(
                lambda _checked=False, job_id=job.id:
                self._edit_backup_job(job_id)
            )

            delete_button = QPushButton("Delete")
            delete_button.setObjectName("secondaryButton")
            delete_button.clicked.connect(
                lambda _checked=False, job_id=job.id, job_name=name:
                self._delete_backup_job(job_id, job_name)
            )

            button_row.addStretch(1)
            button_row.addWidget(run_button)
            button_row.addWidget(edit_button)
            button_row.addWidget(delete_button)

            layout.addLayout(button_row)
            self.backup_job_list.addWidget(frame)

        self.backup_job_list.addStretch()

    def _cancel_backup_job_edit(self) -> None:
        self.editing_backup_job_id = None

        self.job_name.clear()
        self.job_local_folder.clear()

        self.job_server.setCurrentIndex(-1)
        self.job_database.clear()

        self.job_backup_type.setCurrentIndex(
            self.job_backup_type.findData("full")
        )

        self.job_cloud_destination.setCurrentIndex(0)

        self.job_retention_days.setValue(14)
        self.job_compression.setChecked(True)
        self.job_checksum.setChecked(True)

        self.job_save_button.setText("Save Backup Job")
        self.job_cancel_button.setVisible(False)

        self.job_name.setFocus()

    def _edit_backup_job(self, job_id: int) -> None:
        jobs = self.database.list_backup_jobs()
        job = next((item for item in jobs if item.id == job_id), None)

        if job is None:
            QMessageBox.warning(
                self,
                "Backup Job",
                "The selected Backup Job could not be found.",
            )
            return

        self.editing_backup_job_id = job.id

        # Job name
        self.job_name.setText(job.name)

        # SQL Server
        server_index = self.job_server.findData(
            next(
                (
                    server.id
                    for server in self.database.list_sql_servers()
                    if server.name == job.server_name
                ),
                None,
            )
        )

        if server_index >= 0:
            self.job_server.setCurrentIndex(server_index)

        # Database
        self.job_database.setCurrentText(job.database_name)

        # Backup type
        backup_type_index = self.job_backup_type.findData(job.backup_type)
        if backup_type_index >= 0:
            self.job_backup_type.setCurrentIndex(backup_type_index)

        # Local folder
        self.job_local_folder.setText(job.local_folder)

        # Cloud destination
        if job.cloud_destination_name:
            cloud_index = self.job_cloud_destination.findText(
                job.cloud_destination_name,
                Qt.MatchFlag.MatchExactly,
            )
            if cloud_index >= 0:
                self.job_cloud_destination.setCurrentIndex(cloud_index)
        else:
            self.job_cloud_destination.setCurrentIndex(0)

        # Retention
        self.job_retention_days.setValue(job.retention_days)

        # Options
        self.job_compression.setChecked(job.compression_enabled)
        self.job_checksum.setChecked(job.checksum_enabled)

        self.job_save_button.setText("Update Backup Job")
        self.job_cancel_button.setVisible(True)

        self.job_name.setFocus()

    def _run_backup_job(self, job_id: int, job_name: str) -> None:
        answer = QMessageBox.question(
            self,
            "Run Backup",
            f"Run backup job '{job_name}' now?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        jobs = self.database.list_backup_jobs()
        job = next((item for item in jobs if item.id == job_id), None)

        if job is None:
            QMessageBox.critical(
                self,
                "Backup failed",
                "The selected Backup Job could not be found.",
            )
            return

        servers = self.database.list_sql_servers()
        server = next(
            (item for item in servers if item.name == job.server_name),
            None,
        )

        if server is None:
            QMessageBox.critical(
                self,
                "Backup failed",
                f"SQL Server '{job.server_name}' could not be found.",
            )
            return

        try:
            password = None

            if server.auth_mode == "sql":
                password = load_sql_password(server.id)

            connection = SqlServerConnection(
                host=server.host,
                instance=server.instance,
                port=server.port,
                username=server.username
                if server.auth_mode == "sql"
                else None,
                password=password,
                database="master",
            )

            request = BackupRequest(
                connection=connection,
                database_name=job.database_name,
                backup_type=job.backup_type,
                local_folder=Path(job.local_folder),
                job_id=job.id,
                compression=job.compression_enabled,
                checksum=job.checksum_enabled,
            )

            self.sidebar_status.setText(
                f"Running backup: {job.name}"
            )

            backup_path = self.backup_service.run_backup(request)

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Backup failed",
                str(exc),
            )
            self.sidebar_status.setText("Backup failed")
            return

        self.sidebar_status.setText("Backup completed")

        QMessageBox.information(
            self,
            "Backup completed",
            f"Backup completed successfully.\n\n"
            f"File:\n{backup_path}",
        )
    def _delete_backup_job(self, job_id: int, job_name: str) -> None:
        answer = QMessageBox.question(
            self,
            "Delete Backup Job",
            f"Are you sure you want to delete '{job_name}'?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.database.delete_backup_job(job_id)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Delete failed",
                str(exc),
            )
            return

        self.sidebar_status.setText("Backup job deleted")
        self._refresh_backup_jobs_page()
    def _update_sql_method(self) -> None:
        is_udl = self.sql_method.currentData() == "udl"
        for widget in (
            self.sql_host,
            self.sql_instance,
            self.sql_port,
            self.sql_auth,
            self.sql_username,
            self.sql_password,
        ):
            widget.setEnabled(not is_udl)
        self.sql_udl.setEnabled(is_udl)
        self.sql_auth.setEnabled(not is_udl)
        self._update_sql_auth_fields()

    def _update_sql_auth_fields(self) -> None:
        is_sql = self.sql_method.currentData() == "direct" and self.sql_auth.currentData() == "sql"
        self.sql_username.setEnabled(is_sql)
        self.sql_password.setEnabled(is_sql)
        if self.sql_method.currentData() == "direct" and not is_sql:
            self.sql_username.clear()
            self.sql_password.clear()

    def _browse_udl(self) -> None:
        default_dir = Path(r"C:\ProgramData\Sunsoft\BackOffice")

        if not default_dir.exists():
            default_dir = Path.home()

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select UDL file",
            str(default_dir),
            "UDL files (*.udl);;All files (*.*)",
        )
        if not path:
            return
        self.sql_udl.setText(path)
        try:
            fields = udl_to_fields(Path(path))
        except Exception as exc:
            QMessageBox.critical(self, "UDL error", str(exc))
            return

        if fields["host"]:
            self.sql_host.setText(str(fields["host"]))
        if fields["database"]:
            self.sql_database.clear()
            self.sql_database.addItem(str(fields["database"]))
            self.sql_database.setCurrentText(str(fields["database"]))
        if fields["username"]:
            self.sql_username.setText(str(fields["username"]))
        if fields["password"]:
            self.sql_password.setText(str(fields["password"]))

    def _current_sql_connection(self) -> SqlServerConnection:
        if self.sql_method.currentData() == "udl":
            if not self.sql_udl.text().strip():
                raise ValueError("Select a .udl file first.")
            fields = udl_to_fields(Path(self.sql_udl.text()))
            host_value = fields["host"]
            if not host_value:
                raise ValueError("The UDL does not contain a Data Source/Server value.")
            return SqlServerConnection(
                host=host_value,
                username=fields["username"] or None,
                password=fields["password"] or None,
                database=fields["database"] or "master",
            )

        host = self.sql_host.text().strip()
        if not host:
            raise ValueError("Enter a SQL Server host.")
        instance = self.sql_instance.text().strip() or None
        port = self.sql_port.value() or None
        if instance and port:
            raise ValueError("Use either an instance or a port, not both.")
        auth = str(self.sql_auth.currentData())
        username = self.sql_username.text().strip() if auth == "sql" else None
        password = self.sql_password.text() if auth == "sql" else None
        if auth == "sql" and not username:
            raise ValueError("Enter a SQL username.")
        database = self.sql_database.currentText().strip() or "master"
        return SqlServerConnection(
            host=host,
            instance=instance,
            port=port,
            username=username,
            password=password,
            database=database,
        )

    def _test_sql_connection(self) -> None:
        try:
            import pyodbc
            connection = self._current_sql_connection()
            with pyodbc.connect(connection.to_odbc_connection_string(), timeout=5):
                pass
        except Exception as exc:
            QMessageBox.critical(self, "Connection failed", str(exc))
            return
        self.sidebar_status.setText("SQL connection OK")
        self._load_sql_databases(show_message=False)
        QMessageBox.information(self, "Connection successful", "SQL Server connection successful.")

    def _load_sql_databases(self, show_message: bool = True) -> None:
        try:
            connection = self._current_sql_connection()
            names = list_databases(connection)
        except Exception as exc:
            QMessageBox.critical(self, "Database discovery failed", str(exc))
            return
        self.sql_database.clear()
        self.sql_database.addItems(names)
        if show_message:
            self.sidebar_status.setText(f"Loaded {len(names)} database(s)")

    def _save_sql_server(self) -> None:
        name = self.sql_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing information", "Enter a profile name.")
            return

        try:
            connection = self._current_sql_connection()

            auth_mode = (
                "windows"
                if self.sql_method.currentData() == "udl" and not connection.username
                else str(self.sql_auth.currentData())
            )

            database_name = connection.database or None
            udl_path = (
                self.sql_udl.text().strip()
                if self.sql_method.currentData() == "udl"
                else None
            )

            if self.editing_sql_server_id is not None:
                server_id = self.editing_sql_server_id

                self.database.update_sql_server(
                    server_id=server_id,
                    name=name,
                    host=connection.host,
                    instance=connection.instance,
                    port=connection.port,
                    auth_mode=auth_mode,
                    username=connection.username,
                    database_name=database_name,
                    udl_path=udl_path,
                )

                if connection.username and connection.password:
                    save_sql_password(
                        server_id,
                        connection.username,
                        connection.password,
                    )

                self.editing_sql_server_id = None
                self.sql_save_button.setText("Save Server")
                self.sql_cancel_button.setVisible(False)

            else:
                server_id = self.database.add_sql_server(
                    name=name,
                    host=connection.host,
                    instance=connection.instance,
                    port=connection.port,
                    auth_mode=auth_mode,
                    username=connection.username,
                    database_name=database_name,
                    udl_path=udl_path,
                )

                if connection.username:
                    save_sql_password(
                        server_id,
                        connection.username,
                        connection.password or "",
                    )

        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return

        self.sidebar_status.setText("SQL server saved")
        self._refresh_sql_servers_page()

    def _cancel_sql_server_edit(self) -> None:
        self.editing_sql_server_id = None

        self.sql_name.clear()
        self.sql_host.clear()
        self.sql_instance.clear()
        self.sql_port.setValue(0)
        self.sql_username.clear()
        self.sql_password.clear()
        self.sql_database.setCurrentIndex(-1)
        self.sql_udl.clear()

        self.sql_method.setCurrentIndex(
            self.sql_method.findData("direct")
        )
        self.sql_auth.setCurrentIndex(
            self.sql_auth.findData("windows")
        )

        self.sql_save_button.setText("Save Server")
        self.sql_cancel_button.setVisible(False)

        self._update_sql_method()
        self._update_sql_auth_fields()

        self.sql_name.setFocus()

    def _refresh_sql_servers_page(self) -> None:
        if not hasattr(self, "sql_server_list"):
            return
        while self.sql_server_list.count():
            item = self.sql_server_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        servers: list[SqlServerRecord] = self.database.list_sql_servers()
        if not servers:
            empty = QLabel("No SQL Server profiles saved yet.")
            empty.setObjectName("panelBody")
            self.sql_server_list.addWidget(empty)
            return
        for server in servers:
            card = QFrame()
            card.setObjectName("summaryTile")
            card.setMinimumHeight(50)
            card.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )

            row = QHBoxLayout(card)
            auth = "Windows Authentication" if server.auth_mode == "windows" else f"SQL Authentication β€Ά {server.username or ''}"
            label = QLabel(f"{server.name}  β€Ά  {server.server_address}  β€Ά  {auth}")
            label.setObjectName("panelBody")
            row.addWidget(label, 1)

            edit_button = QPushButton("Edit")
            edit_button.setObjectName("secondaryButton")
            edit_button.clicked.connect(
                lambda _checked=False, server_id=server.id:
                self._edit_sql_server(server_id)
            )
            row.addWidget(edit_button)

            delete_button = QPushButton("Delete")
            delete_button.setObjectName("secondaryButton")
            delete_button.clicked.connect(
                lambda _checked=False, server_id=server.id, server_name=server.name:
                self._delete_sql_server(server_id, server_name)
            )
            row.addWidget(delete_button)

            self.sql_server_list.addWidget(card)

    def _edit_sql_server(self, server_id: int) -> None:
        server = next(
            (item for item in self.database.list_sql_servers() if item.id == server_id),
            None,
        )

        if server is None:
            QMessageBox.warning(
                self,
                "SQL Server",
                "The selected SQL Server could not be found.",
            )
            return

        self.editing_sql_server_id = server.id

        # Select connection method first
        if server.udl_path:
            self.sql_method.setCurrentIndex(
                self.sql_method.findData("udl")
            )
            self.sql_udl.setText(server.udl_path)
        else:
            self.sql_method.setCurrentIndex(
                self.sql_method.findData("direct")
            )
            self.sql_udl.clear()

        # Basic server information
        self.sql_name.setText(server.name)
        self.sql_host.setText(server.host)
        self.sql_instance.setText(server.instance or "")
        self.sql_port.setValue(server.port or 0)

        # Database
        if server.database_name:
            database_index = self.sql_database.findText(
                server.database_name,
                Qt.MatchFlag.MatchExactly,
            )

            if database_index < 0:
                self.sql_database.addItem(server.database_name)
                database_index = self.sql_database.findText(
                    server.database_name,
                    Qt.MatchFlag.MatchExactly,
                )

            self.sql_database.setCurrentIndex(database_index)
        else:
            self.sql_database.setCurrentIndex(-1)

        # Authentication
        if server.auth_mode == "sql":
            self.sql_auth.setCurrentIndex(
                self.sql_auth.findData("sql")
            )
            self.sql_username.setText(server.username or "")
        else:
            self.sql_auth.setCurrentIndex(
                self.sql_auth.findData("windows")
            )
            self.sql_username.clear()
            self.sql_password.clear()

        # Load saved SQL password
        if server.auth_mode == "sql":
            password = load_sql_password(server.id)
            self.sql_password.setText(password or "")

        self.sql_save_button.setText("Update Server")
        self.sql_cancel_button.setVisible(True)

        self._update_sql_method()
        self._update_sql_auth_fields()

        self.sql_name.setFocus()


    def _delete_sql_server(self, server_id: int, server_name: str) -> None:
        answer = QMessageBox.question(
            self,
            "Delete SQL Server",
            f"Are you sure you want to delete '{server_name}'?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.database.delete_sql_server(server_id)
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Cannot delete SQL Server",
                str(exc),
            )
            return
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Delete failed",
                str(exc),
            )
            return

        self.sidebar_status.setText("SQL Server deleted")
        self._refresh_sql_servers_page()

    def _build_cloud_page(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        title = QLabel("Cloud")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Manage rclone destinations used by backup jobs.")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        status_row = QHBoxLayout()
        self.rclone_status = QLabel()
        self.rclone_status.setObjectName("statusLabel")
        test_button = QPushButton("Test rclone")
        test_button.setObjectName("secondaryButton")
        test_button.clicked.connect(self._test_rclone)
        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.clicked.connect(self._refresh_cloud_page)
        status_row.addWidget(self.rclone_status, 1)
        status_row.addWidget(test_button)
        status_row.addWidget(refresh_button)
        layout.addLayout(status_row)

        panel = QFrame()
        panel.setObjectName("mainPanel")
        form = QGridLayout(panel)
        form.setContentsMargins(22, 20, 22, 20)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)

        self.cloud_name = QLineEdit()
        self.cloud_name.setPlaceholderText("e.g. Main Google Drive")
        self.cloud_provider = QComboBox()
        self.cloud_provider.addItems(["Google Drive", "OneDrive", "Dropbox", "S3", "MEGA", "Other"])
        self.cloud_remote = QComboBox()
        self.cloud_remote.setEditable(False)
        self.cloud_path = QLineEdit()
        self.cloud_path.setPlaceholderText("ERP-Backups")
        self.cloud_save_button = QPushButton("Save destination")
        self.cloud_save_button.setObjectName("primaryButton")
        self.cloud_save_button.clicked.connect(self._save_cloud_destination)

        self.cloud_cancel_button = QPushButton("Cancel")
        self.cloud_cancel_button.setObjectName("secondaryButton")
        self.cloud_cancel_button.clicked.connect(
            self._cancel_cloud_destination_edit
        )
        self.cloud_cancel_button.setVisible(False)

        cloud_buttons = QHBoxLayout()
        cloud_buttons.addStretch(1)
        cloud_buttons.addWidget(self.cloud_cancel_button)
        cloud_buttons.addWidget(self.cloud_save_button)
        form.addWidget(QLabel("Name"), 0, 0)
        form.addWidget(self.cloud_name, 0, 1)
        form.addWidget(QLabel("Provider"), 1, 0)
        form.addWidget(self.cloud_provider, 1, 1)
        form.addWidget(QLabel("rclone remote"), 2, 0)
        form.addWidget(self.cloud_remote, 2, 1)
        form.addWidget(QLabel("Remote folder"), 3, 0)
        form.addWidget(self.cloud_path, 3, 1)
        form.addLayout(cloud_buttons, 4, 1)
        layout.addWidget(panel)

        self.cloud_list = QVBoxLayout()
        layout.addLayout(self.cloud_list)
        layout.addStretch(1)
        return container

    def _refresh_cloud_page(self) -> None:
        if not hasattr(self, "cloud_remote"):
            return
        self.cloud_remote.clear()
        remotes = list_remotes()
        self.cloud_remote.addItems(remotes)
        self.rclone_status.setText(
            "rclone ready β€” no remotes configured yet."
            if not remotes
            else f"rclone ready β€” {len(remotes)} remote(s) available."
        )
        while self.cloud_list.count():
            item = self.cloud_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        destinations: list[CloudDestinationRecord] = self.database.list_cloud_destinations()
        if not destinations:
            empty = QLabel("No cloud destinations saved yet.")
            empty.setObjectName("panelBody")
            self.cloud_list.addWidget(empty)
            return
        for destination in destinations:
            card = QFrame()
            card.setObjectName("summaryTile")
            card.setMinimumHeight(50)
            card.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )

            row = QHBoxLayout(card)

            label = QLabel(
                f"{destination.name}  β€Ά  {destination.provider}  β€Ά  "
                f"{destination.rclone_remote}:{destination.remote_path}"
            )
            label.setObjectName("panelBody")
            row.addWidget(label, 1)

            edit_button = QPushButton("Edit")
            edit_button.setObjectName("secondaryButton")
            edit_button.clicked.connect(
                lambda _checked=False, destination_id=destination.id:
                self._edit_cloud_destination(destination_id)
            )
            row.addWidget(edit_button)

            delete_button = QPushButton("Delete")
            delete_button.setObjectName("secondaryButton")
            delete_button.clicked.connect(
                lambda _checked=False,
                destination_id=destination.id,
                destination_name=destination.name:
                self._delete_cloud_destination(
                    destination_id,
                    destination_name,
                )
            )
            row.addWidget(delete_button)

            self.cloud_list.addWidget(card)

    def _test_rclone(self) -> None:
        if not find_rclone():
            self.rclone_status.setText("rclone not found on PATH.")
            return
        try:
            remotes = list_remotes()
        except Exception as exc:
            self.rclone_status.setText(f"rclone error: {exc}")
            return
        self.rclone_status.setText(f"rclone OK β€” {len(remotes)} remote(s) configured.")


    def _edit_cloud_destination(self, destination_id: int) -> None:
        destinations = self.database.list_cloud_destinations()

        destination = next(
            (
                item
                for item in destinations
                if item.id == destination_id
            ),
            None,
        )

        if destination is None:
            QMessageBox.warning(
                self,
                "Destination not found",
                "The selected cloud destination could not be found.",
            )
            return

        self.editing_cloud_destination_id = destination.id

        self.cloud_name.setText(destination.name)

        provider_index = self.cloud_provider.findText(destination.provider)
        if provider_index >= 0:
            self.cloud_provider.setCurrentIndex(provider_index)

        remote_index = self.cloud_remote.findText(destination.rclone_remote)
        if remote_index >= 0:
            self.cloud_remote.setCurrentIndex(remote_index)

        self.cloud_path.setText(destination.remote_path)

        self.cloud_save_button.setText("Update destination")
        self.cloud_cancel_button.setVisible(True)

        self.cloud_name.setFocus()

    def _save_cloud_destination(self) -> None:
        name = self.cloud_name.text().strip()
        remote = self.cloud_remote.currentText().strip()
        path = self.cloud_path.text().strip()
        provider = self.cloud_provider.currentText().strip()

        if not name or not remote:
            QMessageBox.warning(
                self,
                "Missing information",
                "Enter a destination name and select an rclone remote.",
            )
            return

        try:
            if self.editing_cloud_destination_id is not None:
                self.database.update_cloud_destination(
                    destination_id=self.editing_cloud_destination_id,
                    name=name,
                    provider=provider,
                    rclone_remote=remote,
                    remote_path=path,
                )
                message = "Cloud destination updated"
            else:
                self.database.upsert_cloud_destination(
                    name=name,
                    provider=provider,
                    rclone_remote=remote,
                    remote_path=path,
                )
                message = "Cloud destination saved"
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return

        self.editing_cloud_destination_id = None
        self.cloud_name.clear()
        self.cloud_provider.setCurrentIndex(0)
        self.cloud_remote.setCurrentIndex(-1)
        self.cloud_path.clear()

        self.cloud_save_button.setText("Save destination")
        self.cloud_cancel_button.setVisible(False)

        self.sidebar_status.setText(message)
        self._refresh_cloud_page()

    def _delete_cloud_destination(
        self,
        destination_id: int,
        destination_name: str,
    ) -> None:
        answer = QMessageBox.question(
            self,
            "Delete Cloud Destination",
            f"Are you sure you want to delete '{destination_name}'?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.database.delete_cloud_destination(destination_id)
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Cannot delete Cloud Destination",
                str(exc),
            )
            return
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Delete failed",
                str(exc),
            )
            return

        if self.editing_cloud_destination_id == destination_id:
            self._cancel_cloud_destination_edit()

        self.sidebar_status.setText("Cloud destination deleted")
        self._refresh_cloud_page()

    def _cancel_cloud_destination_edit(self) -> None:
        self.editing_cloud_destination_id = None

        self.cloud_name.clear()
        self.cloud_provider.setCurrentIndex(0)
        self.cloud_remote.setCurrentIndex(-1)
        self.cloud_path.clear()

        self.cloud_save_button.setText("Save destination")
        self.cloud_cancel_button.setVisible(False)

        self.cloud_name.setFocus()

    def _build_placeholder_page(self, title_text: str, body_text: str) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)
        title = QLabel(title_text)
        title.setObjectName("pageTitle")
        subtitle = QLabel(body_text)
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        panel = QFrame()
        panel.setObjectName("mainPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(24, 22, 24, 22)
        body = QLabel(body_text)
        body.setObjectName("panelBody")
        body.setWordWrap(True)
        panel_layout.addWidget(body)
        panel_layout.addStretch(1)
        layout.addWidget(panel, 1)
        return container

    def _refresh_history_page(self) -> None:
        if not hasattr(self, "history_list"):
            return

        while self.history_list.count():
            item = self.history_list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        runs = self.database.list_backup_runs()

        if not runs:
            label = QLabel("No backup runs yet.")
            label.setStyleSheet("color: #888;")
            self.history_list.addWidget(label)
            return

        for run in runs:
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)

            layout = QVBoxLayout(frame)

            job_name = run.job_name or "Manual / Unknown Job"
            backup_type = run.backup_type.upper()

            if run.status == "success":
                status_text = "SUCCESS"
            elif run.status == "failed":
                status_text = "FAILED"
            elif run.status == "running":
                status_text = "RUNNING"
            else:
                status_text = run.status.upper()

            layout.addWidget(
                QLabel(
                    f"<b>{job_name}</b>  β€Ά  {status_text}"
                )
            )

            layout.addWidget(
                QLabel(
                    f"Database: {run.database_name}  β€Ά  "
                    f"Type: {backup_type}"
                )
            )

            layout.addWidget(
                QLabel(
                    f"Started: {run.started_at}  β€Ά  "
                    f"Finished: {run.finished_at or '-'}"
                )
            )

            if run.bytes_written is not None:
                size_mb = run.bytes_written / (1024 * 1024)

                layout.addWidget(
                    QLabel(
                        f"Size: {size_mb:.2f} MB"
                    )
                )

            if run.local_path:
                path_label = QLabel(
                    f"Local: {run.local_path}"
                )
                path_label.setWordWrap(True)
                layout.addWidget(path_label)

            if run.cloud_path:
                cloud_label = QLabel(
                    f"Cloud: {run.cloud_path}"
                )
                cloud_label.setWordWrap(True)
                layout.addWidget(cloud_label)

            if run.error_message:
                error_label = QLabel(
                    f"Error: {run.error_message}"
                )
                error_label.setWordWrap(True)
                layout.addWidget(error_label)

            self.history_list.addWidget(frame)

        self.history_list.addStretch()

    def _build_history_page(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        title = QLabel("History")
        title.setObjectName("pageTitle")

        subtitle = QLabel(
            "View previous backup runs and their results."
        )
        subtitle.setObjectName("pageSubtitle")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        panel = QFrame()
        panel.setObjectName("mainPanel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 20, 22, 20)
        panel_layout.setSpacing(12)

        self.history_list = QVBoxLayout()
        self.history_list.setSpacing(10)

        panel_layout.addLayout(self.history_list)
        panel_layout.addStretch(1)

        layout.addWidget(panel, 1)

        self._refresh_history_page()

        return container

APP_STYLESHEET = """
QWidget {
    background: #f5f7fb;
    color: #18212f;
    font-family: "Segoe UI";
    font-size: 14px;
}

/* Sidebar */
#sidebar {
    background: #111827;
}

#brandTitle {
    background: transparent;
    color: #ffffff;
    font-size: 23px;
    font-weight: 700;
}

#brandSubtitle {
    background: transparent;
    color: #94a3b8;
}

#sidebarStatus {
    background: transparent;
    color: #94a3b8;
}

/* Navigation */
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

#navButton[active="true"] {
    background: #2563eb;
    color: #ffffff;
}

/* Page header */
#pageTitle {
    background: transparent;
    color: #18212f;
    font-size: 28px;
    font-weight: 700;
}

#pageSubtitle {
    background: transparent;
    color: #667085;
}

/* Buttons */
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

#secondaryButton {
    background: #ffffff;
    color: #344054;
    border: 1px solid #d0d5dd;
    border-radius: 7px;
    padding: 9px 14px;
    font-weight: 600;
}

#secondaryButton:hover {
    background: #f8fafc;
}

/* Cards */
#summaryTile,
#mainPanel {
    background: #ffffff;
    border: 1px solid #e3e8ef;
    border-radius: 8px;
}

#summaryValue {
    background: transparent;
    color: #18212f;
    font-size: 27px;
    font-weight: 700;
}

#summaryLabel {
    background: transparent;
    color: #667085;
}

#panelTitle {
    background: transparent;
    color: #18212f;
    font-size: 18px;
    font-weight: 700;
}

#panelBody {
    background: transparent;
    color: #475467;
}

#statusLabel {
    background: transparent;
    color: #475467;
}

/* Form controls */
QLineEdit,
QComboBox {
    background: #ffffff;
    color: #18212f;
    border: 1px solid #d0d5dd;
    border-radius: 6px;
    padding: 8px 10px;
}

QLineEdit:focus,
QComboBox:focus {
    border: 1px solid #2563eb;
}

QLabel {
    background: transparent;
}
"""

def run_app(database: AppDatabase) -> int:
    app = QApplication(sys.argv)
    window = MainWindow(database)
    window.show()
    return app.exec()

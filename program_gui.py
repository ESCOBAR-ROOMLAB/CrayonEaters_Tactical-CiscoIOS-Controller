import sys

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QLabel, QFrame, QAbstractItemView
)
from PyQt5.QtCore import Qt, QSize, QTimer

from PyQt5.QtGui import QFont, QColor, QPalette

# Local helper module; provides utility functions such as get_absolute_path()
import common_helper_functions

# Standard library module for writing structured log messages (INFO, ERROR, etc.)
import logging

# Logging handler that auto-rotates the log file when it reaches a defined size limit
from logging.handlers import RotatingFileHandler

###################################################################################################################################

# SETUP LOGGING
# -------------
logger = logging.getLogger(__name__) # use the module's name as the name in the logs
logger.setLevel(logging.INFO) # set the logging level
log_file_path = 'execution_logs.log' # define the logging file path

# Use RotatingFileHandler
# log_file_path = the absolute path for the log file
# maxBytes: 5 * 1024
# backupCount=0: When the file is full, delete it and start a new one
handler = RotatingFileHandler(
    log_file_path, maxBytes=5*1024*1024, backupCount=0
)

# Set the format of the log messages
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

# Add the formatted HANDLER to the logger
logger.addHandler(handler)

###################################################################################################################################

# ── PALETTE — USMC: Navy Blue / Scarlet Red / White ───────────────────────────

BG_BASE        = "#0a0f2e"      # deep navy
BG_PANEL       = "#0d1435"      # slightly lighter navy panel
BG_ROW         = "#0d1435"
BG_ROW_ALT     = "#111840"      # alternating row — subtle lighter navy
BORDER         = "#1e2d6e"      # navy border
BORDER_LIGHT   = "#263580"      # lighter navy border

ACCENT         = "#cc0000"      # USMC scarlet
ACCENT_MID     = "#e00000"      # brighter scarlet
ACCENT_LIGHT   = "#ff3333"      # light scarlet for hover
ACCENT_SHINE   = "#ff6666"      # scarlet highlight
ACCENT_DIM     = "#2a0a0a"      # very dark scarlet tint

SILVER         = "#d0d8e8"      # metallic silver-white
SILVER_BRIGHT  = "#eef2fa"      # bright silver
SILVER_DIM     = "#8898b8"      # muted silver

TEXT_PRIMARY   = "#eef2fa"      # bright silver-white — max readability
TEXT_SECONDARY = "#b0bcd8"      # mid silver
TEXT_MUTED     = "#6878a8"      # muted blue-silver
TEXT_HEADER    = "#d0d8e8"      # silver for headers

GOLD           = "#c8a84a"      # brass/gold for title details
GOLD_LIGHT     = "#e8c870"

DANGER         = "#cc0000"
DANGER_LIGHT   = "#ff3333"
DANGER_DIM     = "#2a0808"

BTN_DISABLED   = "#1a2050"
BTN_DIS_TEXT   = "#3a4878"

###################################################################################################################################

STYLESHEET = f"""

    QMainWindow {{
        background-color: {BG_BASE};
    }}
    QWidget#centralWidget {{
        background: qlineargradient(
            x1:0, y1:0, x2:1, y2:1,
            stop:0   #0c1138,
            stop:0.3 #0a0f2e,
            stop:0.7 #0d1230,
            stop:1   #080d28
        );
    }}

    /* ── Title ── */
    QLabel#appTitle {{
        color: {SILVER_BRIGHT};
        font-size: 13px;
        font-family: 'Courier New', monospace;
        letter-spacing: 4px;
        font-weight: bold;
        font-style: italic;
    }}
    QLabel#appSubtitle {{
        color: {GOLD};
        font-size: 9px;
        font-family: 'Courier New', monospace;
        letter-spacing: 5px;
        font-style: oblique; 
    }}
    QLabel#sectionLabel {{
        color: {SILVER};
        font-size: 12px;
        font-family: 'Courier New', monospace;
        letter-spacing: 3px;
        font-weight: bold;
    }}

    /* ── Sheet input ── */
    QLineEdit#sheetInput {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #161e50, stop:1 {BG_PANEL});
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_LIGHT};
        border-radius: 6px;
        padding: 8px 14px;
        font-size: 13px;
        font-family: 'Courier New', monospace;
        selection-background-color: {ACCENT_DIM};
        selection-color: {ACCENT_SHINE};
    }}
    QLineEdit#sheetInput:focus {{
        border: 1px solid {ACCENT};
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #1a2260, stop:1 {BG_PANEL});
    }}

   /* ── Show button ── */
    QPushButton#btnShow {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {GOLD_LIGHT}, stop:0.4 #d4a840, stop:1 {GOLD});
        color: #0a0f2e;
        border: 1px solid {GOLD};
        border-bottom: 2px solid #8a6818;
        border-radius: 6px;
        padding: 8px 18px;
        font-size: 11px;
        font-family: 'Courier New', monospace;
        font-weight: bold;
        letter-spacing: 1px;
    }}
    QPushButton#btnShow:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #f8e898, stop:0.4 {GOLD_LIGHT}, stop:1 #d4a840);
    }}
    QPushButton#btnShow:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {GOLD}, stop:1 #8a6818);
        border-bottom: 1px solid #6a5010;
    }}

    QPushButton#btnShow:disabled {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #6a5a2a, stop:0.4 #5a4a20, stop:1 #4a3a18);
        color: #1a1a0a;  /* Very dark text for contrast */
        border: 1px solid #5a4a20;
        border-bottom: 2px solid #3a2a10;
    }}

    /* ── Table panel ── */
    QFrame#tablePanel {{
        background: #141e50;
        border: 1px solid {BORDER_LIGHT};
        border-top: 2px solid {ACCENT};
        border-radius: 8px;
    }}

    /* ── Table ── */
QTableWidget {{
    background-color: #0d1435;  /* solid background for empty space */
    color: #eef2fa;
    gridline-color: #1e2d6e;
    border: none;
    font-size: 12px;
    font-family: 'Courier New', monospace;
    selection-background-color: #2a0a0a;
    selection-color: #ff6666;
    outline: none;
    }}

    QTableWidget QAbstractItemView {{
        background-color: #0d1435;
    }}

    QTableWidget::item {{
        padding: 4px 10px;
        border: none;
        color: {TEXT_PRIMARY};
    }}
    QTableWidget::item:alternate {{
        background-color: {BG_ROW_ALT};
    }}
    QTableWidget::item:selected {{
        background-color: {ACCENT_DIM};
        color: {ACCENT_SHINE};
    }}

    /* ── Table header ── */
    QHeaderView::section {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #1e2d70, stop:0.5 #192560, stop:1 #141e50);
        color: {TEXT_HEADER};
        border: none;
        border-bottom: 2px solid {ACCENT};
        border-right: 1px solid {BORDER};
        padding: 7px 10px;
        font-size: 10px;
        font-family: 'Courier New', monospace;
        letter-spacing: 2px;
        font-weight: bold;
    }}
    QHeaderView::section:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #2a3a88, stop:1 #1e2d70);
    }}
    QHeaderView::section:last {{ border-right: none; }}

    /* ── Select All button ── */
    QPushButton#btnSelectAll {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {GOLD_LIGHT}, stop:1 {GOLD});
        color: #0a0f2e;
        border: 1px solid {GOLD};
        border-radius: 3px;
        font-size: 8px;
        font-family: 'Courier New', monospace;
        font-weight: bold;
        letter-spacing: 1px;
        padding: 2px 4px;
    }}
    QPushButton#btnSelectAll:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #f8e090, stop:1 {GOLD_LIGHT});
    }}
    QPushButton#btnSelectAll:checked {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {ACCENT_MID}, stop:1 {ACCENT});
        border-color: {ACCENT_MID};
        color: {SILVER_BRIGHT};
    }}

    /* ── Checkbox ── */
    QCheckBox {{ spacing: 0px; }}
    QCheckBox::indicator {{
        width: 15px;
        height: 15px;
        border: 1px solid {BORDER_LIGHT};
        border-radius: 3px;
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #1a2260, stop:1 {BG_PANEL});
    }}
    QCheckBox::indicator:checked {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {ACCENT_LIGHT}, stop:1 {ACCENT});
        border-color: {ACCENT_MID};
    }}
    QCheckBox::indicator:hover {{ border-color: {ACCENT_MID}; }}

    /* ── Start button ── */
    QPushButton#btnStart {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #4a8a50, stop:0.4 #306838, stop:1 #1e4824);
        color: {SILVER_BRIGHT};
        border: 1px solid #3a7840;
        border-bottom: 2px solid #142e18;
        border-radius: 6px;
        font-size: 12px;
        font-family: 'Courier New', monospace;
        font-weight: bold;
        letter-spacing: 2px;
    }}
    QPushButton#btnStart:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #5aaa60, stop:0.4 #4a8a50, stop:1 #306838);
    }}
    QPushButton#btnStart:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #1e4824, stop:1 #0e2810);
        border-bottom: 1px solid #0e2810;
    }}
    QPushButton#btnStart:disabled {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #2a4a30, stop:0.4 #1a3820, stop:1 #0e2814);;
        color: #6a8a70;
        border: 1px solid {BORDER};
        border-bottom: 2px solid {BORDER};
    }}

    /* ── Cancel button ── */
    QPushButton#btnCancel {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #1a2260, stop:1 #0d1435);
        color: #8898b8;
        border: 1px solid #263580;
        border-bottom: 2px solid #1e2d6e;
        border-radius: 6px;
        font-size: 12px;
        font-family: 'Courier New', monospace;
        letter-spacing: 2px;
    }}
    QPushButton#btnCancel:enabled {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #ff3333, stop:0.4 #e00000, stop:1 #cc0000);
        color: #eef2fa;
        border: 1px solid #e00000;
        border-bottom: 2px solid #8a0000;
    }}
    QPushButton#btnCancel:enabled:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #ff5555, stop:0.4 #ff3333, stop:1 #e00000);
    }}
    QPushButton#btnCancel:enabled:pressed {{
        background: #cc0000;
        border-bottom: 1px solid #660000;
    }}

    QPushButton#btnCancel:disabled {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #5a2020, stop:0.4 #4a1818, stop:1 #3a1010);
        color: #aa8888;
        border: 1px solid #4a1818;
        border-bottom: 2px solid #2a0808;
    }}

    /* ── Vertical scrollbar ── */
    QScrollBar:vertical {{
        background: {BG_PANEL};
        width: 8px;
        margin: 0;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {ACCENT_LIGHT}, stop:0.5 {ACCENT_MID}, stop:1 {ACCENT});
        border-radius: 4px;
        min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #ff5555, stop:1 {ACCENT_MID});
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical,  QScrollBar::sub-page:vertical  {{ background: none; }}

    /* ── Horizontal scrollbar ── */
    QScrollBar:horizontal {{
        background: {BG_PANEL};
        height: 8px;
        margin: 0;
        border-radius: 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {ACCENT_LIGHT}, stop:0.5 {ACCENT_MID}, stop:1 {ACCENT});
        border-radius: 4px;
        min-width: 28px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #ff5555, stop:1 {ACCENT_MID});
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
"""

###################################################################################################################################

# MAIN WINDOW
# -----------
class MainWindow(QMainWindow):

    ### <=== LAYOUT MANAGER ===> ###
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cisco Tactical Updater — CrayonEaters Series")
        self.setFixedSize(QSize(860, 610))
        self.setStyleSheet(STYLESHEET)

        self._all_checked    = False
        self._update_running = False
        self._selected_for_update = set()  # Track which rows were selected for update

        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(24, 18, 24, 20)
        root.setSpacing(14)

        # ── TITLE BLOCK ────────────────────────────────────────────────────────
        title_block = QVBoxLayout()
        title_block.setSpacing(2)

        title = QLabel("CISCO TACTICAL UPDATER")
        title.setObjectName("appTitle")

        subtitle = QLabel("CRAYONEATERS SERIES")
        subtitle.setObjectName("appSubtitle")

        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        root.addLayout(title_block)

        # Scarlet/gold shimmer separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 transparent, stop:0.2 {GOLD_LIGHT}, stop:0.5 {ACCENT}, "
            f"stop:0.8 {GOLD_LIGHT}, stop:1 transparent); "
            f"max-height: 1px; border: none;"
        )
        root.addWidget(sep)

        # ── TOP ROW ────────────────────────────────────────────────────────────
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        self.sheet_input = QLineEdit()
        self.sheet_input.setObjectName("sheetInput")
        self.sheet_input.setPlaceholderText("Enter Excel sheet name...")
        self.sheet_input.setFixedHeight(38)
        self.sheet_input.textChanged.connect(self._update_show_button_state)

        self.btn_show = QPushButton("SHOW ELIGIBLE DEVICES")
        self.btn_show.setObjectName("btnShow")
        self.btn_show.setFixedHeight(38)
        self.btn_show.setFixedWidth(234)
        self.btn_show.setCursor(Qt.PointingHandCursor)
        self.btn_show.setEnabled(False)
        self._update_show_button_state()

        top_row.addWidget(self.sheet_input)
        top_row.addWidget(self.btn_show)
        root.addLayout(top_row)

        # ── TABLE PANEL ────────────────────────────────────────────────────────
        table_panel = QFrame()
        table_panel.setObjectName("tablePanel")
        panel_layout = QVBoxLayout(table_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        header_bar = QHBoxLayout()
        header_bar.setContentsMargins(14, 8, 14, 0)
        header_bar.setSpacing(0)
        lbl = QLabel("ELIGIBLE DEVICES")
        lbl.setObjectName("sectionLabel")
        header_bar.addWidget(lbl)
        header_bar.addStretch()
        panel_layout.addLayout(header_bar)

        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 {BORDER}, stop:0.5 {ACCENT}, stop:1 {BORDER}); "
            f"max-height: 1px; border: none;"
        )
        panel_layout.addWidget(div)

        # ── TABLE ──────────────────────────────────────────────────────────────
        self.table = QTableWidget()
        self.table.setObjectName("deviceTable")
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "", "HOSTNAME", "IP ADDRESS", "CURRENT VER", "TARGET VER"
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.verticalHeader().setDefaultSectionSize(34)

        # Interactive columns — user can drag to resize
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 52)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.table.setColumnWidth(1, 300)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.setColumnWidth(2, 160)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.table.setColumnWidth(3, 140)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Interactive)
        self.table.setColumnWidth(4, 149)

        # Both scrollbars — vertical always on, horizontal as needed
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

        panel_layout.addWidget(self.table)

        # SELECT ALL floating button inside col-0 header
        hdr = self.table.horizontalHeader()
        self.btn_select_all = QPushButton("ALL", hdr)
        self.btn_select_all.setObjectName("btnSelectAll")
        self.btn_select_all.setCheckable(True)
        self.btn_select_all.setCursor(Qt.PointingHandCursor)
        self.btn_select_all.setFixedSize(36, 20)
        self.btn_select_all.clicked.connect(self._toggle_select_all)

        root.addWidget(table_panel, stretch=1)

        # ── BOTTOM BUTTONS ─────────────────────────────────────────────────────
        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        self.btn_cancel = QPushButton("CANCEL UPDATE")
        self.btn_cancel.setObjectName("btnCancel")
        self.btn_cancel.setFixedHeight(44)
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)

        self.btn_start = QPushButton("START UPDATE")
        self.btn_start.setObjectName("btnStart")
        self.btn_start.setFixedHeight(44)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self._on_start)

        bottom.addWidget(self.btn_cancel, stretch=1)
        bottom.addWidget(self.btn_start,  stretch=2)
        root.addLayout(bottom)

        self._load_demo_rows()
        self.table.horizontalHeader().geometriesChanged.connect(self._reposition_select_all)


    ### <=== SELECT ALL BUTTON ===> ###
    # Center it in COL 0
    def _reposition_select_all(self):

        """
        Repositions the SELECT ALL button so it stays centered inside the
        col-0 header cell at all times.

        The button is a floating QPushButton parented to the header viewport
        rather than placed via a layout — so its position must be calculated
        and set manually in pixel coordinates whenever the header geometry
        changes (e.g. on first render, or when the user resizes a column).

        The horizontal center is computed by taking the left edge of col-0
        in viewport coordinates, then offsetting by half the difference
        between the column width and the button width.

        The vertical center is computed by taking half the difference between
        the header height and the button height.

        raise_() ensures the button renders on top of the header cell and is
        not obscured by it.
        """

        hdr   = self.table.horizontalHeader()
        x     = self.table.columnViewportPosition(0)  # left edge of col-0 in viewport px
        col_w = self.table.columnWidth(0)
        btn_w = self.btn_select_all.width()
        btn_h = self.btn_select_all.height()
        hdr_h = hdr.height()
        self.btn_select_all.move(
            x + (col_w - btn_w) // 2,   # horizontally centered within col-0
            (hdr_h - btn_h) // 2        # vertically centered within the header row
        )
        self.btn_select_all.raise_()

    # Capture the select all button click
    def _on_header_clicked(self, col):

        """
        Slot connected to the horizontalHeader().sectionClicked signal.

        sectionClicked emits the index of whichever column header the user
        clicked. This function intercepts that signal and delegates to
        _toggle_select_all() only when col-0 is clicked — the checkbox
        column. Clicks on any other column header are ignored, leaving
        their default sort/resize behaviour unaffected.
        """

        if col == 0:
            self._toggle_select_all()

    # Selects all devices after clicking on the select all button
    def _toggle_select_all(self):

        """
        Toggles the checked state of every device checkbox in the table.

        Flips the internal _all_checked flag on each call, then applies
        that state to every row's QCheckBox and syncs the SELECT ALL
        button's checked appearance. Also calls _update_button_states()
        so the START UPDATE and CANCEL UPDATE buttons reflect the new
        selection state immediately.
        """

        self._all_checked = not self._all_checked
        self.btn_select_all.setChecked(self._all_checked)
        for row in range(self.table.rowCount()):
            chk = self._get_checkbox(row)
            if chk:
                chk.setChecked(self._all_checked)
        self._update_button_states()


    ### <=== START UPDATE BUTTON ===> ###
    def _on_start(self):

        """
        Triggers the firmware update workflow for selected devices.
        
        Captures the indices of all currently checked device rows in
        self._selected_for_update. Disables checkboxes for devices that
        were NOT selected, preventing them from being modified during
        the update process. Selected devices retain enabled checkboxes
        so the user can choose which ones to cancel.
        
        Simulates a 30-second update process (for testing), showing
        "UPDATING..." on the start button. Sets _update_running flag to True,
        disables START UPDATE button, and enables CANCEL UPDATE button.
        Cancel button will only be functional if at least one selected
        device is checked for cancellation.
        """

        # Capture which rows are selected for update
        self._selected_for_update.clear()
        for row in range(self.table.rowCount()):
            chk = self._get_checkbox(row)
            if chk and chk.isChecked():
                self._selected_for_update.add(row)
        
        # Disable checkboxes for unselected rows
        for row in range(self.table.rowCount()):
            chk = self._get_checkbox(row)
            if chk:
                chk.setEnabled(row in self._selected_for_update)
                chk.stateChanged.disconnect()
                chk.stateChanged.connect(self._update_cancel_button_state)
        
        # Disable SELECT ALL button during update
        self.btn_select_all.setEnabled(False)
        
        # Grey out Show button and input field
        self.btn_show.setEnabled(False)
        self.sheet_input.setEnabled(False)
        
        # Update button text to show progress
        self.btn_start.setText("UPDATING...")
        self.btn_start.setEnabled(False)
        
        self._update_running = True
        self._update_cancel_button_state()
        
        # Simulate 30-second update process
        QTimer.singleShot(30000, self._complete_update)


    ### <=== CANCEL BUTTON ===> ###
    def _on_cancel(self):
        
        """
        Aborts an in-progress firmware update and resets UI state.
        
        Simulates a 5-second cancellation process (for testing), then
        clears the _update_running flag and restores all checkboxes to
        their fully enabled state. Reconnects the original stateChanged
        signal handlers for normal device selection behavior.
        
        Re-enables the SELECT ALL button, Show button, and input field.
        Calls _update_button_states() to restore the START UPDATE button
        based on current selections.
        """

        # Simulate cancellation process with 5-second delay
        self.btn_cancel.setText("CANCELLING...")
        self.btn_cancel.setEnabled(False)
        
        # Use QTimer to avoid blocking the UI
        QTimer.singleShot(5000, self._complete_cancellation)

    # State Management for the button
    def _update_cancel_button_state(self):

        """
        Controls the enabled state of the CANCEL UPDATE button during an active update.
        
        The cancel button is enabled only when at least one checkbox belonging
        to a device that was originally selected for update is checked. This
        allows the user to selectively cancel specific devices from the update
        batch.
        
        Unselected devices' checkboxes are disabled during the update and
        cannot affect the cancel button state.
        """

        if not self._update_running:
            self.btn_cancel.setEnabled(False)
            return
        
        # Don't modify if currently showing "CANCELLING..."
        if self.btn_cancel.text() == "CANCELLING...":
            return
        
        has_cancel_selection = False
        for row in self._selected_for_update:
            chk = self._get_checkbox(row)
            if chk and chk.isChecked():
                has_cancel_selection = True
                break
        
        self.btn_cancel.setEnabled(has_cancel_selection)

    # Calls the functionality for the button
    def _on_cancel_clicked(self):

        """Handle cancel button click - either cancel devices or abort entirely."""

        if self._update_running and self._selected_for_update:
            self._cancel_selected_devices()
        else:
            self._on_cancel()

    # TO BE MODIFIED: ensures that the devices that were already cancelled cannot get selected again for cancellation
    def _cancel_selected_devices(self):

        """
        Removes the selected devices from the active update batch.
        
        Iterates through the originally selected devices and unchecks
        those that the user has marked for cancellation. These devices
        will be excluded from the ongoing update process.
        
        Called when the CANCEL UPDATE button is clicked during an active update.
        """

        for row in list(self._selected_for_update):
            chk = self._get_checkbox(row)
            if chk and chk.isChecked():
                self._selected_for_update.remove(row)
                chk.setChecked(False)
                chk.setEnabled(False)  # Can't re-select once cancelled
        
        self._update_cancel_button_state()


    ### <=== RESTORE ALL GUI ELEMENTS TO ORIGINAL STATE, AFTER UPDATE PROCESS FINISHES ===> ###
    def _complete_update(self):

        """
        Completes the update process after the 30-second delay.
        
        Restores all UI elements to their pre-update state, re-enables
        checkboxes for all devices, and resets button states. Called
        automatically when the update timer expires.
        """

        # Only complete if update is still running (not cancelled)
        if not self._update_running:
            return
        
        self._update_running = False
        
        # Restore start button text
        self.btn_start.setText("START UPDATE")
        
        # Re-enable all checkboxes and restore original signal
        for row in range(self.table.rowCount()):
            chk = self._get_checkbox(row)
            if chk:
                chk.setEnabled(True)
                chk.stateChanged.disconnect()
                chk.stateChanged.connect(self._update_button_states)
        
        # Re-enable SELECT ALL button
        self.btn_select_all.setEnabled(True)
        
        # Re-enable Show button and input field
        self.sheet_input.setEnabled(True)
        self._update_show_button_state()

        # Ensure the CANCEL UPDATE button is disabled again 
        self.btn_cancel.setEnabled(False)
        self._update_button_states()

    ### <=== RESTORE ALL GUI ELEMENTS TO ORIGINAL STATE, AFTER CANCELLATION PROCESS FINISHES ===> ###
    def _complete_cancellation(self):

        """
        Completes the cancellation process after the 5-second delay.
        
        Restores all UI elements to their pre-update state, re-enables
        checkboxes for all devices, and resets button states.
        """

        self._update_running = False
        
        # Restore button texts
        self.btn_cancel.setText("CANCEL UPDATE")
        self.btn_start.setText("START UPDATE")
        
        # Re-enable all checkboxes and restore original signal
        for row in range(self.table.rowCount()):
            chk = self._get_checkbox(row)
            if chk:
                chk.setEnabled(True)
                chk.stateChanged.disconnect()
                chk.stateChanged.connect(self._update_button_states)
        
        # Re-enable SELECT ALL button
        self.btn_select_all.setEnabled(True)
        
        # Re-enable Show button and input field
        self.sheet_input.setEnabled(True)
        self._update_show_button_state()
        
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self._update_button_states()


    ### <=== CHECKBOX RETRIEVAL ===> ###
    def _get_checkbox(self, row):

        """
        PURPOSE 
        -------
        Retrieves the QCheckBox widget embedded in a specific table row.
        
        Each row's first column (col-0) contains a container QWidget that
        holds a QHBoxLayout with a centered QCheckBox. This method navigates
        that widget hierarchy to extract the checkbox instance.
        
        The container widget is fetched via cellWidget(row, 0). If it exists,
        findChild() searches its children recursively for a QCheckBox object.
        This approach is necessary because the checkbox is not a direct
        QTableWidgetItem but rather a custom widget embedded in the cell.
        

        ARGUMENTS
        ---------
        row (int): Zero-based index of the table row to inspect.
            
        
        RETURNS
        -------
        QCheckBox or None: The checkbox widget if found and the row
        contains a valid container; otherwise None (e.g., empty row,
        malformed cell, or row index out of bounds).
        """

        container = self.table.cellWidget(row, 0)
        if container:
            return container.findChild(QCheckBox)
        return None
    

    ## <=== BUTTON STATE MANAGEMENT ===> ###
    def _update_button_states(self):

        """
        Evaluates current UI conditions and enables/disables action buttons accordingly.
        
        The START UPDATE button requires three conditions to be enabled:
            1. The table contains at least one device row (has_devices)
            2. At least one checkbox is currently checked (has_selection)
            3. No update is currently in progress (not _update_running)
            
        If any condition fails, the START button remains disabled (dark green).
        
        The CANCEL UPDATE button is managed separately — it is only enabled
        during an active update process (_update_running is True). This method
        ensures CANCEL is forcefully disabled when no update is running,
        returning it to its dark-red disabled state.
        
        This method is called after any action that modifies device selection,
        table content, or the update running state, including:

            - Toggling individual checkboxes
            - Clicking SELECT ALL
            - Loading demo data
            - Completing or cancelling an update
            
        Note:
            During an active update, _update_cancel_button_state() handles
            the more nuanced cancel button behavior (only enabled when at
            least one originally-selected device is checked). This method
            provides the baseline state management outside of updates.
        """

        row_count = self.table.rowCount()
        has_devices = row_count > 0
        has_selection = False
        
        if has_devices:
            for row in range(row_count):
                chk = self._get_checkbox(row)
                if chk and chk.isChecked():
                    has_selection = True
                    break
        
        # Both buttons require devices AND at least one selected
        enabled = has_devices and has_selection and not self._update_running
        
        self.btn_start.setEnabled(enabled)
        # Cancel button only enabled when update is running
        if not self._update_running:
            self.btn_cancel.setEnabled(False)


    ### <=== SHOW BUTTON STATE MANAGEMENT ===> ###
    def _update_show_button_state(self):

        """
        Controls the enabled state of the SHOW ELIGIBLE DEVICES button.
        
        The SHOW button is enabled only when the sheet input QLineEdit contains
        non-whitespace text. An empty field or one containing only spaces/tabs
        results in the button being disabled and rendered in muted gold/brown
        tones via the :disabled stylesheet state.
        
        This method is connected to the textChanged signal of self.sheet_input,
        meaning it fires on every keystroke in the input field. It is also
        called manually during initialization and after cancellation/completion
        of an update to restore the correct button state based on current
        input content.
        
        The strip() call ensures that purely whitespace input (spaces, tabs,
        newlines) is treated as empty, preventing the user from triggering
        a search with meaningless input.
        """

        has_text = bool(self.sheet_input.text().strip())
        self.btn_show.setEnabled(has_text)


    ### TEMP: provides the ficitonal device rows
    def _load_demo_rows(self):
        # Long hostnames intentionally included to trigger horizontal scrollbar
        demo_data = [
            ("SW1-HEADQUARTERS-BLDG-A-FLOOR-3-sdfghjkikjhnuuikgb3444545",       "10.17.1.10",  "17.09.04a", "17.12.06"),
            ("SW2-HEADQUARTERS-BLDG-A-FLOOR-3",       "10.17.1.11",  "17.09.04a", "17.12.06"),
            ("SW3-DATACENTER-PRIMARY-RACK-12",         "10.17.1.12",  "17.09.04a", "17.12.06"),
            ("SW4-DATACENTER-PRIMARY-RACK-13",         "10.17.1.13",  "17.06.03a", "17.12.06"),
            ("SW5-DATACENTER-SECONDARY-RACK-01",       "10.17.1.14",  "17.06.03a", "17.12.06"),
            ("R1-CORE-EDGE-NORTHEAST-CAMPUS",          "10.17.1.20",  "17.06.03a", "17.12.06"),
            ("R2-CORE-EDGE-SOUTHWEST-CAMPUS",          "10.17.1.21",  "17.06.03a", "17.12.06"),
            ("R3-BRANCH-OFFICE-QUANTICO-VA",           "10.17.1.22",  "17.03.06",  "17.12.06"),
            ("R4-BRANCH-OFFICE-CAMP-LEJEUNE-NC",       "10.17.1.23",  "17.03.06",  "17.12.06"),
            ("R5-BRANCH-OFFICE-CAMP-PENDLETON-CA",     "10.17.1.24",  "17.03.06",  "17.12.06"),
            ("CORE1-DISTRIBUTION-LAYER-PRIMARY",       "10.17.1.30",  "17.09.04a", "17.12.06"),
            ("CORE2-DISTRIBUTION-LAYER-SECONDARY",     "10.17.1.31",  "17.09.04a", "17.12.06"),
            ("DIST1-ACCESS-AGGREGATION-ZONE-A",        "10.17.1.40",  "17.06.03a", "17.12.06"),
            ("DIST2-ACCESS-AGGREGATION-ZONE-B",        "10.17.1.41",  "17.06.03a", "17.12.06"),
            ("ACC1-USER-ACCESS-BLDG-B-FLOOR-1",        "10.17.1.50",  "17.03.06",  "17.12.06"),
            ("ACC2-USER-ACCESS-BLDG-B-FLOOR-2",        "10.17.1.51",  "17.03.06",  "17.12.06"),
            ("ACC3-USER-ACCESS-BLDG-C-FLOOR-1",        "10.17.1.52",  "17.03.06",  "17.12.06"),
        ]

        self.table.setRowCount(len(demo_data))

        for row_idx, (hostname, ip, current, target) in enumerate(demo_data):
            chk = QCheckBox()
            chk.stateChanged.connect(self._update_button_states)
            container = QWidget()
            lay = QHBoxLayout(container)
            lay.addWidget(chk)
            lay.setAlignment(Qt.AlignCenter)
            lay.setContentsMargins(0, 0, 0, 0)
            container.setStyleSheet("background: transparent;")
            self.table.setCellWidget(row_idx, 0, container)

            for col_idx, value in enumerate([hostname, ip, current, target], start=1):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                self.table.setItem(row_idx, col_idx, item)
        self._update_button_states()


# Ensure this code only executes on the main program file, and not imported as an external module
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

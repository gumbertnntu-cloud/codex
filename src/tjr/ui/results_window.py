from __future__ import annotations

import html
import re
from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tjr.core.matching import extract_lemmas
from tjr.core.scanner import MatchRecord
from tjr.ui.smooth_scroll import enable_smooth_wheel_scroll

_TOKEN_RE = re.compile(r"[\w-]+", re.UNICODE)


class ExpandableMessageWidget(QWidget):
    def __init__(self, text: str, highlight_lemmas: set[str], on_toggle, parent=None) -> None:
        super().__init__(parent)
        self._full_text = text
        self._highlight_lemmas = highlight_lemmas
        self._on_toggle = on_toggle
        self._expanded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setTextFormat(Qt.RichText)
        self.message_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.message_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.toggle_button = QPushButton("...")
        self.toggle_button.setFlat(True)
        self.toggle_button.setCursor(Qt.PointingHandCursor)
        self.toggle_button.clicked.connect(self._toggle)

        layout.addWidget(self.message_label)

        controls = QHBoxLayout()
        controls.addStretch(1)
        controls.addWidget(self.toggle_button)
        layout.addLayout(controls)

        self._render()

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._render()
        self._on_toggle()

    def _render(self) -> None:
        self.message_label.setText(_highlight_text(self._full_text, self._highlight_lemmas))
        line_height = self.fontMetrics().lineSpacing()

        if self._expanded:
            self.message_label.setMaximumHeight(16777215)
            self.toggle_button.setText("Свернуть")
        else:
            self.message_label.setMaximumHeight((line_height * 3) + 6)
            self.toggle_button.setText("...")


class MatchResultsDialog(QDialog):
    def __init__(
        self,
        records: list[MatchRecord],
        on_ban_message: Callable[[str, bool], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Найденные совпадения")
        self.resize(1280, 760)
        self._records = list(records)
        self._visible_records = list(records)
        self._on_ban_message = on_ban_message

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel(f"Найдено совпадений: {len(records)}"))
        top.addStretch(1)
        top.addWidget(QLabel("Сортировка по дате"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Сначала новые", userData="desc")
        self.sort_combo.addItem("Сначала старые", userData="asc")
        self.sort_combo.currentIndexChanged.connect(self._apply_sort_and_render)
        top.addWidget(self.sort_combo)
        layout.addLayout(top)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Бан", "Дата", "Сообщение", "Ссылка", "Канал", "Совпавшие слова"]
        )
        self.table.setRowCount(len(records))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setWordWrap(True)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)

        vertical_step = max(1, int(self.table.verticalScrollBar().singleStep() * 0.79))
        horizontal_step = max(1, int(self.table.horizontalScrollBar().singleStep() * 0.79))
        self.table.verticalScrollBar().setSingleStep(vertical_step)
        self.table.horizontalScrollBar().setSingleStep(horizontal_step)
        enable_smooth_wheel_scroll(self.table, speed_factor=0.73, duration_ms=110)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        self.table.setColumnWidth(0, 56)
        self.table.setColumnWidth(1, 170)
        self.table.setColumnWidth(2, 560)
        self.table.setColumnWidth(3, 260)
        self.table.setColumnWidth(4, 220)
        self.table.setColumnWidth(5, 320)

        self.table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self.table)

        bottom = QHBoxLayout()
        bottom.addStretch(1)

        export_button = QPushButton("Экспорт в XLSX")
        export_button.clicked.connect(self._export_to_xlsx)
        bottom.addWidget(export_button)

        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.close)
        bottom.addWidget(close_button)

        layout.addLayout(bottom)
        self._apply_sort_and_render()

    def _apply_sort_and_render(self) -> None:
        sort_order = self.sort_combo.currentData()
        reverse = sort_order != "asc"
        self._visible_records = sorted(
            self._records,
            key=lambda record: record.published_at,
            reverse=reverse,
        )

        self.table.clearContents()
        self.table.setRowCount(len(self._visible_records))
        for row, record in enumerate(self._visible_records):
            self._set_row(row, record)
            self.table.resizeRowToContents(row)

    def _set_row(self, row: int, record: MatchRecord) -> None:
        date_text = _format_dt(record.published_at)
        matched_words = _format_matched_terms(record)

        ban_checkbox = QCheckBox()
        ban_checkbox.setToolTip("Больше не показывать это сообщение")
        ban_checkbox.stateChanged.connect(lambda state, rec=record: self._on_ban_checked(state, rec))
        ban_wrapper = QWidget()
        ban_layout = QHBoxLayout(ban_wrapper)
        ban_layout.setContentsMargins(0, 0, 0, 0)
        ban_layout.addWidget(ban_checkbox, alignment=Qt.AlignCenter)
        self.table.setCellWidget(row, 0, ban_wrapper)

        self.table.setItem(row, 1, QTableWidgetItem(date_text))
        message_widget = ExpandableMessageWidget(
            text=record.text,
            highlight_lemmas=_collect_highlight_lemmas(record),
            on_toggle=lambda r=row: self.table.resizeRowToContents(r),
            parent=self.table,
        )
        self.table.setCellWidget(row, 2, message_widget)

        link_item = QTableWidgetItem(record.link)
        link_item.setData(Qt.UserRole, record.link)
        link_item.setToolTip("Клик для открытия ссылки")
        link_item.setForeground(QBrush(QColor("#0a66d6")))
        self.table.setItem(row, 3, link_item)

        self.table.setItem(row, 4, QTableWidgetItem(record.channel))
        self.table.setItem(row, 5, QTableWidgetItem(matched_words))

    def _on_cell_clicked(self, row: int, column: int) -> None:
        if column != 3:
            return
        item = self.table.item(row, column)
        if item is None:
            return
        link = item.data(Qt.UserRole)
        if isinstance(link, str) and link:
            QDesktopServices.openUrl(QUrl(link))

    def _on_ban_checked(self, state: int, record: MatchRecord) -> None:
        if self._on_ban_message is None or not record.link:
            return
        is_banned = Qt.CheckState(state) == Qt.CheckState.Checked
        self._on_ban_message(record.link, is_banned)

    def _export_to_xlsx(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить результаты",
            "tjr-results.xlsx",
            "Excel Files (*.xlsx)",
        )
        if not path:
            return

        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        try:
            from openpyxl import Workbook

            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Matches"
            headers = ["Дата", "Сообщение", "Ссылка", "Канал", "Совпавшие слова"]
            sheet.append(headers)

            for record in self._visible_records:
                sheet.append(
                    [
                        _format_dt(record.published_at),
                        record.text,
                        record.link,
                        record.channel,
                        _format_matched_terms(record),
                    ]
                )

            workbook.save(path)
            QMessageBox.information(self, "Экспорт завершен", f"Файл сохранен:\n{path}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Ошибка экспорта", str(exc))


def _format_dt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _format_matched_terms(record: MatchRecord) -> str:
    result = record.match_result
    chunks: list[str] = []

    if result.matched_title_terms:
        chunks.append("Название: " + ", ".join(result.matched_title_terms))
    if result.matched_profile_terms:
        chunks.append("Профиль: " + ", ".join(result.matched_profile_terms))
    if result.matched_industry_terms:
        chunks.append("Отрасль: " + ", ".join(result.matched_industry_terms))

    return " | ".join(chunks) if chunks else "-"


def _collect_highlight_lemmas(record: MatchRecord) -> set[str]:
    terms = (
        record.match_result.matched_title_terms
        + record.match_result.matched_profile_terms
        + record.match_result.matched_industry_terms
    )
    lemmas: set[str] = set()
    for term in terms:
        lemmas.update(extract_lemmas(term))
    return lemmas


def _highlight_text(text: str, highlight_lemmas: set[str]) -> str:
    if not text:
        return ""

    if not highlight_lemmas:
        return _wrap_preformatted(html.escape(text))

    parts: list[str] = []
    cursor = 0
    for match in _TOKEN_RE.finditer(text):
        start, end = match.span()
        token = match.group(0)

        if start > cursor:
            parts.append(html.escape(text[cursor:start]))

        token_lemma = next(iter(extract_lemmas(token)), token.lower())
        safe_token = html.escape(token)
        if token_lemma in highlight_lemmas:
            parts.append(
                f'<span style="background-color:#1f5a36; color:#ffffff; border-radius: 2px;">{safe_token}</span>'
            )
        else:
            parts.append(safe_token)

        cursor = end

    if cursor < len(text):
        parts.append(html.escape(text[cursor:]))

    return _wrap_preformatted("".join(parts))


def _wrap_preformatted(content: str) -> str:
    return f'<div style="white-space: pre-wrap;">{content}</div>'

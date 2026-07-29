########################################################
# @file App/Presentation/Views/Widgets/SideBar.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
########################################################
import json
import os
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QMenu,
    QProxyStyle,
    QSizePolicy,
    QStyle,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QColor, QDrag, QIcon, QLinearGradient, QPainter
from PyQt6.QtCore import (
    QAbstractAnimation,
    QByteArray,
    QEasingCurve,
    QFileSystemWatcher,
    QMimeData,
    QRect,
    QSize,
    QTimer,
    QVariantAnimation,
    Qt,
    pyqtSignal,
    pyqtSlot,
)

from App.Infrastructure.Helpers.ResourceHelper import resource_path
from App.Infrastructure.Helpers.MediaHelper import (
    MEDIA_EXTENSIONS as SUPPORTED_MEDIA_EXTENSIONS,
)
from App.Presentation.ViewModels.FeatureViewModel.SidebarViewModel import (
    SidebarViewModel,
)


class SidebarShimmerBar(QWidget):
    """A tiny width-responsive shimmer that consumes no CPU while idle."""

    HEIGHT = 3
    DURATION_MS = 1100

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarShimmerBar")
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self._active = False
        self._phase = 0.0

        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setDuration(self.DURATION_MS)
        self._animation.setLoopCount(-1)
        self._animation.setEasingCurve(QEasingCurve.Type.Linear)
        self._animation.valueChanged.connect(self._on_animation_value)
        self.hide()

    def set_active(self, active):
        active = bool(active)
        self._active = active
        if active:
            self.show()
            if self.isVisible():
                self._start_animation()
            return

        self._animation.stop()
        self._phase = 0.0
        self.hide()

    def is_active(self):
        return self._active

    def is_animation_running(self):
        return (
            self._animation.state()
            == QAbstractAnimation.State.Running
        )

    def phase(self):
        return self._phase

    def _start_animation(self):
        if not self.is_animation_running():
            self._animation.start()

    def _on_animation_value(self, value):
        self._phase = float(value)
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        if self._active:
            self._start_animation()

    def hideEvent(self, event):
        self._animation.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        del event
        if self.width() <= 0:
            return

        painter = QPainter(self)
        base_color = QColor("#0078D7")
        base_color.setAlpha(62)
        painter.fillRect(self.rect(), base_color)

        highlight_width = max(44.0, self.width() * 0.28)
        center = (
            -highlight_width
            + self._phase * (self.width() + 2.0 * highlight_width)
        )
        gradient = QLinearGradient(
            center - highlight_width,
            0,
            center + highlight_width,
            0,
        )
        gradient.setColorAt(0.0, QColor(116, 201, 255, 0))
        gradient.setColorAt(0.35, QColor(116, 201, 255, 105))
        gradient.setColorAt(0.5, QColor(225, 248, 255, 245))
        gradient.setColorAt(0.65, QColor(116, 201, 255, 105))
        gradient.setColorAt(1.0, QColor(116, 201, 255, 0))
        painter.fillRect(self.rect(), gradient)


class DropIndicatorProxyStyle(QProxyStyle):
    """Custom style dùng để đổi màu và vẽ thanh drop indicator đúng vị trí."""

    def __init__(self, base_style=None, color="#0078D7", height=3):
        super().__init__(base_style)
        self._drop_indicator_color = QColor(color)
        self._drop_indicator_height = max(1, int(height))

    @staticmethod
    def _owner_view(widget):
        current = widget
        while current is not None:
            if hasattr(current, "_custom_drop_indicator_rect"):
                return current
            current = current.parent()
        return None

    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PrimitiveElement.PE_IndicatorItemViewItemDrop:
            view = self._owner_view(widget)
            rect = getattr(view, "_custom_drop_indicator_rect", QRect())

            # Không cho Qt vẽ indicator native tại row Image/Video/File nữa.
            # Chỉ vẽ khi DraggableTreeWidget đã snap indicator về PROJECT hoặc ITEM hợp lệ.
            if not rect.isValid():
                return

            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._drop_indicator_color)
            painter.drawRect(rect)
            painter.restore()
            return

        super().drawPrimitive(element, option, painter, widget)


class DraggableTreeWidget(QTreeWidget):
    INTERNAL_NODE_MIME = "application/x-tnh-optima-sidebar-node"
    DROP_INDICATOR_COLOR = "#0078D7"  # Xanh dương của thanh drop indicator
    DROP_INDICATOR_HEIGHT = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropOverwriteMode(False)
        self.setAutoScroll(True)
        self.setAutoScrollMargin(24)
        self.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)

        self._custom_drop_indicator_rect = QRect()
        self._custom_drop_target_item = None
        self._custom_drop_position = None
        self._drop_indicator_style = DropIndicatorProxyStyle(
            color=self.DROP_INDICATOR_COLOR,
            height=self.DROP_INDICATOR_HEIGHT,
        )
        self.setStyle(self._drop_indicator_style)
        self._dragged_tree_item = None
        self._drag_scroll_timer = QTimer(self)
        self._drag_scroll_timer.setInterval(40)
        self._drag_scroll_timer.timeout.connect(
            self._perform_drag_autoscroll
        )
        self._drag_scroll_direction = 0
        self._drag_scroll_margin = 32
        self._drag_scroll_step = 16

    @staticmethod
    def _node_kind(item):
        if item is None:
            return None
        parent = item.parent()
        if parent is None:
            return "PROJECT"
        if parent.parent() is None:
            return "ITEM"
        if (
            parent.text(0) in ("Image", "Video")
            and parent.parent() is not None
            and parent.parent().parent() is not None
            and parent.parent().parent().parent() is None
        ):
            return "FILE"
        return None

    @staticmethod
    def _project_item_of(item):
        current = item
        while current is not None and current.parent() is not None:
            current = current.parent()
        return current

    @staticmethod
    def _direct_item_of(item):
        if item is None:
            return None
        project_item = DraggableTreeWidget._project_item_of(item)
        current = item
        while current is not None and current.parent() is not project_item:
            current = current.parent()
        return current if current is not project_item else None

    def _internal_drag_payload(self, item, kind):
        project_item = self._project_item_of(item)
        payload = {
            "kind": kind,
            "project_path": project_item.data(
                0, Qt.ItemDataRole.UserRole
            ) if project_item is not None else None,
        }
        if kind == "ITEM":
            payload["item_path"] = item.data(0, Qt.ItemDataRole.UserRole)
        return QByteArray(json.dumps(payload).encode("utf-8"))

    def startDrag(self, supportedActions):
        item = self.currentItem()
        kind = self._node_kind(item)
        if item is None or kind is None:
            return

        if kind in ("PROJECT", "ITEM"):
            # Include Qt's model MIME so QAbstractItemView can calculate and
            # paint its native above/below drop indicator. The custom MIME is
            # still the authority used by our constrained drop handler.
            mime_data = self.mimeData([item])
            mime_data.setData(
                self.INTERNAL_NODE_MIME,
                self._internal_drag_payload(item, kind),
            )
            drag = QDrag(self)
            drag.setMimeData(mime_data)
            self._dragged_tree_item = item
            try:
                drag.exec(Qt.DropAction.MoveAction)
            finally:
                self._stop_drag_autoscroll()
                self._dragged_tree_item = None
                self._clear_drop_indicator()
            return

        # Media files keep the existing copy-drag contract used by the editor.
        if kind != "FILE" or item.childCount() > 0:
            return

        temp = item
        path_parts = []
        while temp.parent() is not None:
            path_parts.insert(0, temp.text(0))
            temp = temp.parent()

        if not path_parts:
            return

        project_name = temp.text(0)
        file_relative_path = os.path.join(*path_parts)

        mime_data = QMimeData()
        mime_data.setText(f"{project_name}|{file_relative_path}")

        drag = QDrag(self)
        drag.setMimeData(mime_data)
        try:
            drag.exec(Qt.DropAction.CopyAction)
        finally:
            self._stop_drag_autoscroll()

    def dragEnterEvent(self, event):
        if (
            event.source() is self
            and event.mimeData().hasFormat(self.INTERNAL_NODE_MIME)
        ):
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        pos = event.position().toPoint()
        if self._is_internal_reorder_drag(event):
            # Keep scrolling even when the current row itself is not a valid
            # reorder destination. This lets the pointer pass over expanded
            # Image/Video/file descendants while their PROJECT/ITEM ancestor
            # remains the snapped target.
            self._update_drag_autoscroll(pos)
        else:
            self._stop_drag_autoscroll()

        drop_info = self._drop_info_at(pos)
        if drop_info is None:
            self._clear_drop_indicator()
            event.ignore()
            return

        target, drop_position = drop_info
        self._set_drop_indicator(target, drop_position)

        # Let QAbstractItemView keep autoscroll/drag state updated. The proxy
        # style above will ignore Qt's raw indicator rect and use our snapped rect.
        super().dragMoveEvent(event)
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def dragLeaveEvent(self, event):
        self._stop_drag_autoscroll()
        self._clear_drop_indicator()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._stop_drag_autoscroll()
        if not (
            event.source() is self
            and event.mimeData().hasFormat(self.INTERNAL_NODE_MIME)
        ):
            self._clear_drop_indicator()
            event.ignore()
            return

        source = self._dragged_tree_item
        drop_info = self._drop_info_at(event.position().toPoint())
        if source is None or source.treeWidget() is not self or drop_info is None:
            self._clear_drop_indicator()
            event.ignore()
            return

        target, drop_position = drop_info
        moved = self._move_internal_item(source, target, drop_position)
        self._clear_drop_indicator()

        if moved:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

    def _is_internal_reorder_drag(self, event):
        if (
            event.source() is not self
            or not event.mimeData().hasFormat(self.INTERNAL_NODE_MIME)
            or self._dragged_tree_item is None
        ):
            return False

        source = self._dragged_tree_item
        return (
            source.treeWidget() is self
            and self._node_kind(source) in ("PROJECT", "ITEM")
        )

    def _update_drag_autoscroll(self, pos):
        source = self._dragged_tree_item
        if (
            source is None
            or source.treeWidget() is not self
            or self._node_kind(source) not in ("PROJECT", "ITEM")
        ):
            self._stop_drag_autoscroll()
            return

        viewport_height = self.viewport().height()
        margin = min(
            self._drag_scroll_margin,
            max(0, viewport_height // 2),
        )
        if pos.y() < margin:
            direction = -1
        elif pos.y() > viewport_height - margin:
            direction = 1
        else:
            self._stop_drag_autoscroll()
            return

        self._drag_scroll_direction = direction
        if not self._drag_scroll_timer.isActive():
            self._drag_scroll_timer.start()

    def _perform_drag_autoscroll(self):
        if self._drag_scroll_direction == 0:
            self._stop_drag_autoscroll()
            return

        scrollbar = self.verticalScrollBar()
        current_value = scrollbar.value()
        new_value = current_value + (
            self._drag_scroll_direction * self._drag_scroll_step
        )
        new_value = max(
            scrollbar.minimum(),
            min(scrollbar.maximum(), new_value),
        )
        if new_value == current_value:
            self._stop_drag_autoscroll()
            return

        scrollbar.setValue(new_value)
        self.viewport().update()

    def _stop_drag_autoscroll(self):
        self._drag_scroll_direction = 0
        if self._drag_scroll_timer.isActive():
            self._drag_scroll_timer.stop()

    def _clear_drop_indicator(self):
        old_rect = QRect(self._custom_drop_indicator_rect)
        self._custom_drop_indicator_rect = QRect()
        self._custom_drop_target_item = None
        self._custom_drop_position = None
        if old_rect.isValid():
            self.viewport().update(old_rect.adjusted(0, -4, 0, 4))

    def _set_drop_indicator(self, target, drop_position):
        new_rect = self._drop_indicator_rect_for(target, drop_position)
        old_rect = QRect(self._custom_drop_indicator_rect)
        self._custom_drop_indicator_rect = new_rect
        self._custom_drop_target_item = target
        self._custom_drop_position = drop_position

        update_rect = QRect(new_rect)
        if old_rect.isValid():
            update_rect = update_rect.united(old_rect) if update_rect.isValid() else old_rect
        if update_rect.isValid():
            self.viewport().update(update_rect.adjusted(0, -4, 0, 4))

    def _drop_indicator_rect_for(self, item, drop_position):
        if item is None or item.treeWidget() is not self:
            return QRect()

        item_rect = self.visualItemRect(item)
        if not item_rect.isValid():
            return QRect()

        line_height = max(1, self.DROP_INDICATOR_HEIGHT)
        if drop_position == QAbstractItemView.DropIndicatorPosition.AboveItem:
            center_y = item_rect.top()
        else:
            center_y = item_rect.bottom()

        y = center_y - line_height // 2
        return QRect(0, y, self.viewport().width(), line_height)

    def _drop_position_for_item_rect(self, item, pos):
        item_rect = self.visualItemRect(item)
        if item_rect.isValid() and pos.y() < item_rect.center().y():
            return QAbstractItemView.DropIndicatorPosition.AboveItem
        return QAbstractItemView.DropIndicatorPosition.BelowItem

    def _drop_info_at(self, pos):
        source = self._dragged_tree_item
        if source is None or source.treeWidget() is not self:
            return None

        kind = self._node_kind(source)
        if kind == "PROJECT":
            return self._project_drop_info_at(source, pos)
        if kind == "ITEM":
            return self._item_drop_info_at(source, pos)
        return None

    def _project_drop_info_at(self, source, pos):
        target = self.itemAt(pos)
        if target is None:
            if self.topLevelItemCount() == 0:
                return None
            target_project = self.topLevelItem(self.topLevelItemCount() - 1)
            drop_position = QAbstractItemView.DropIndicatorPosition.BelowItem
        else:
            target_project = self._project_item_of(target)
            if target_project is None:
                return None
            # Dù con trỏ đang nằm trên Item/Image/Video/File, indicator vẫn được
            # snap về row PROJECT, không gạch ngang node con.
            drop_position = self._drop_position_for_item_rect(target_project, pos)

        if not self._project_move_would_change(source, target_project, drop_position):
            return None
        return target_project, drop_position

    def _item_drop_info_at(self, source, pos):
        project_item = source.parent()
        if project_item is None:
            return None

        target = self.itemAt(pos)
        if target is None or self._project_item_of(target) is not project_item:
            return None

        target_item = self._direct_item_of(target)
        if target_item is None:
            # Khi rê trên row Project cha, chỉ cho hiển thị ở dưới Item cuối cùng.
            if project_item.childCount() == 0:
                return None
            target_item = project_item.child(project_item.childCount() - 1)
            drop_position = QAbstractItemView.DropIndicatorPosition.BelowItem
        else:
            # Nếu target là Image/Video/File thì snap indicator về Item cha.
            # Vì con trỏ đang nằm trong vùng con của Item, vị trí hợp lý là dưới Item.
            if target is target_item:
                drop_position = self._drop_position_for_item_rect(target_item, pos)
            else:
                drop_position = QAbstractItemView.DropIndicatorPosition.BelowItem

        if not self._item_move_would_change(source, target_item, drop_position):
            return None
        return target_item, drop_position

    def _can_drop_internal_at(self, pos):
        return self._drop_info_at(pos) is not None

    @staticmethod
    def _insert_after_drop_position(drop_position):
        return drop_position in (
            QAbstractItemView.DropIndicatorPosition.OnItem,
            QAbstractItemView.DropIndicatorPosition.BelowItem,
        )

    def _project_insert_index(self, source, target_project, drop_position):
        source_index = self.indexOfTopLevelItem(source)
        if source_index < 0:
            return -1

        if target_project is None:
            insert_index = self.topLevelItemCount()
        else:
            target_index = self.indexOfTopLevelItem(target_project)
            if target_index < 0:
                return -1
            insert_index = target_index + (
                1 if self._insert_after_drop_position(drop_position) else 0
            )

        if source_index < insert_index:
            insert_index -= 1
        return insert_index

    def _project_move_would_change(self, source, target_project, drop_position):
        source_index = self.indexOfTopLevelItem(source)
        insert_index = self._project_insert_index(source, target_project, drop_position)
        return source_index >= 0 and insert_index >= 0 and insert_index != source_index

    def _item_insert_index(self, source, target_item, drop_position):
        project_item = source.parent()
        if project_item is None:
            return -1

        source_index = project_item.indexOfChild(source)
        if source_index < 0:
            return -1

        if target_item is None:
            insert_index = project_item.childCount()
        else:
            target_index = project_item.indexOfChild(target_item)
            if target_index < 0:
                return -1
            insert_index = target_index + (
                1 if self._insert_after_drop_position(drop_position) else 0
            )

        if source_index < insert_index:
            insert_index -= 1
        return insert_index

    def _item_move_would_change(self, source, target_item, drop_position):
        project_item = source.parent()
        if project_item is None:
            return False
        source_index = project_item.indexOfChild(source)
        insert_index = self._item_insert_index(source, target_item, drop_position)
        return source_index >= 0 and insert_index >= 0 and insert_index != source_index

    def _move_internal_item(self, source, target, drop_position):
        kind = self._node_kind(source)
        if kind == "PROJECT":
            target_project = self._project_item_of(target)
            return self._move_project(
                source,
                target_project,
                self._insert_after_drop_position(drop_position),
            )
        if kind == "ITEM":
            return self._move_item(
                source,
                target,
                drop_position,
            )
        return False

    def _move_project(self, source, target_project, insert_after):
        source_index = self.indexOfTopLevelItem(source)
        if source_index < 0:
            return False

        if target_project is None:
            insert_index = self.topLevelItemCount()
        else:
            target_index = self.indexOfTopLevelItem(target_project)
            if target_index < 0:
                return False
            insert_index = target_index + (1 if insert_after else 0)

        if source_index < insert_index:
            insert_index -= 1
        if insert_index == source_index:
            return False

        moved_item = self.takeTopLevelItem(source_index)
        self.insertTopLevelItem(insert_index, moved_item)
        self.setCurrentItem(moved_item)
        self.scrollToItem(moved_item)
        return True

    def _move_item(self, source, target, drop_position):
        project_item = source.parent()
        if project_item is None:
            return False

        if target is None:
            insert_index = project_item.childCount()
        else:
            if self._project_item_of(target) is not project_item:
                return False
            target_item = self._direct_item_of(target)
            if target_item is None:
                insert_index = project_item.childCount()
            else:
                target_index = project_item.indexOfChild(target_item)
                if target_index < 0:
                    return False
                insert_index = target_index + (
                    1 if self._insert_after_drop_position(drop_position) else 0
                )

        source_index = project_item.indexOfChild(source)
        if source_index < 0:
            return False
        if source_index < insert_index:
            insert_index -= 1
        if insert_index == source_index:
            return False

        moved_item = project_item.takeChild(source_index)
        project_item.insertChild(insert_index, moved_item)
        self.setCurrentItem(moved_item)
        self.scrollToItem(moved_item)
        return True

    def drawBranches(self, painter, rect, index):
        item = self.itemFromIndex(index)
        if item is None:
            return
        has_indicator = (
            item.childCount() > 0
            or item.childIndicatorPolicy()
            == QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
        )
        if has_indicator:
            if self.isExpanded(index):
                icon = self.window().sidebar.icon_branch_open if hasattr(self.window(), "sidebar") else self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
            else:
                icon = self.window().sidebar.icon_branch_closed if hasattr(self.window(), "sidebar") else self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight)

            pm = icon.pixmap(12, 12)
            
            # --- BẢN SỬA LỖI UI ---
            # Lấy chiều rộng chuẩn của 1 cấp (level)
            indent = self.indentation() 
            
            # Tính toán x dựa vào mép phải (right) của rect thay vì mép trái (x).
            # Điều này ép mũi tên luôn nằm gọn trong ô cuối cùng, sát cạnh với Folder icon.
            x = rect.right() - indent + (indent - pm.width()) // 2 + 6
            y = rect.y() + (rect.height() - pm.height()) // 2
            
            painter.drawPixmap(x, y, pm)


class ProjectSidebar(QDockWidget):
    MEDIA_LOADED_ROLE = int(Qt.ItemDataRole.UserRole) + 1
    MAX_CONCURRENT_MEDIA_SCANS = 2
    MEDIA_EXTENSIONS = SUPPORTED_MEDIA_EXTENSIONS

    sig_new_item = pyqtSignal(str)
    sig_delete = pyqtSignal(str)
    sig_rename = pyqtSignal(str)
    sig_save_as = pyqtSignal(str)
    sig_import_file = pyqtSignal(str)
    sig_import_item = pyqtSignal(str)

    sig_paste_to_project = pyqtSignal(str)
    sig_item_copy = pyqtSignal(str, str)
    sig_item_cut = pyqtSignal(str, str)
    sig_item_save = pyqtSignal(str, str)
    sig_item_delete = pyqtSignal(str, str)
    sig_item_rename = pyqtSignal(str, str)
    sig_item_open_media = pyqtSignal(str, str, str)
    sig_open_editor = pyqtSignal(str, str)

    sig_file_copy = pyqtSignal(str, str, str, str)
    sig_file_cut = pyqtSignal(str, str, str, str)
    sig_file_rename = pyqtSignal(str, str, str, str, str)
    sig_file_delete = pyqtSignal(str, str, str, str)
    sig_file_paste = pyqtSignal(str, str, str)
    shutdown_ready = pyqtSignal()

    # Read-only compatibility views for older integrations and diagnostics.
    @property
    def _media_scan_workers(self):
        return self.scan_view_model._workers

    @property
    def _media_scan_queue(self):
        return self.scan_view_model._queue

    @property
    def _pending_media_refreshes(self):
        return set(self.scan_view_model._pending_refreshes)

    @staticmethod
    def _scan_media_directory(media_dir, media_type, hidden_names=()):
        return SidebarViewModel._scan_media_directory(
            media_dir,
            ProjectSidebar.MEDIA_EXTENSIONS.get(media_type, ()),
            hidden_names,
        )

    def __init__(self, parent=None):
        super().__init__("Project Manager", parent)
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.setMinimumWidth(100)
        self.setMaximumWidth(16777215)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )

        self.app_config = {
            "sub_folders": ["Image", "Video"],
            "valid_extensions": sorted(
                {
                    extension
                    for extensions in self.MEDIA_EXTENSIONS.values()
                    for extension in extensions
                }
            ),
        }

        self._init_icons()

        self.fs_watcher = QFileSystemWatcher(self)
        self.fs_watcher.directoryChanged.connect(self.on_directory_changed)
        self.watched_paths = {}
        self.scan_view_model = SidebarViewModel(
            self.MAX_CONCURRENT_MEDIA_SCANS,
            self,
        )
        self.scan_view_model.media_scan_completed.connect(
            self._apply_media_scan
        )
        self.scan_view_model.media_scan_failed.connect(
            lambda path, message: print(
                f"Error scanning {path}: {message}"
            )
        )
        self.scan_view_model.loading_changed.connect(
            lambda active: self.set_loading_source(
                "sidebar-media-scans",
                active,
            )
        )
        self.scan_view_model.shutdown_ready.connect(
            self._on_scan_shutdown_ready
        )
        self._media_name_cache = {}
        self._hidden_media_paths = set()
        self._hidden_media_names_by_dir = {}
        self._shutting_down = False
        self._loading_sources = set()

        container = QWidget()
        container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.loading_bar = SidebarShimmerBar(container)
        layout.addWidget(self.loading_bar)

        self.tabs = QTabWidget()
        self.tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)

        self.tab_project = QWidget()
        self.setup_tab_project()
        self.tabs.addTab(self.tab_project, "Project")

        self.tab_calibration = QWidget()
        self.setup_tab_calibration()
        self.tabs.addTab(self.tab_calibration, "Calibration Tool")

        layout.addWidget(self.tabs)
        self.setWidget(container)

    @pyqtSlot(str, bool)
    def set_loading_source(self, source, active):
        """Keep the busy bar visible until every tracked source is finished."""
        if not isinstance(source, str) or not source:
            return
        if active:
            self._loading_sources.add(source)
        else:
            self._loading_sources.discard(source)
        self.loading_bar.set_active(bool(self._loading_sources))

    def is_loading(self):
        return bool(self._loading_sources)

    def _init_icons(self):
        style = self.style()
        self.icon_dir = style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        self.icon_dir_closed = style.standardIcon(QStyle.StandardPixmap.SP_DirClosedIcon)

        icon_path = resource_path(os.path.join("App", "ReSource", "Icon", "SideBar"))

        path_img = os.path.join(icon_path, "image_file.svg")
        path_vid = os.path.join(icon_path, "video_file.svg")
        path_arrow_down = os.path.join(icon_path, "arrow_down.svg")
        path_arrow_next = os.path.join(icon_path, "arrow_next.svg")

        self.icon_branch_open = QIcon(path_arrow_down) if os.path.exists(path_arrow_down) else style.standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
        self.icon_branch_closed = QIcon(path_arrow_next) if os.path.exists(path_arrow_next) else style.standardIcon(QStyle.StandardPixmap.SP_ArrowRight)

        if os.path.exists(path_img):
            self.icon_image = QIcon(path_img)
        else:
            self.icon_image = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)

        if os.path.exists(path_vid):
            self.icon_video = QIcon(path_vid)
        else:
            self.icon_video = style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)

    def _get_sidebar_style(self):
        resource_dir = resource_path(os.path.join("App", "ReSource", "Icon", "SideBar"))
        arrow_down_path = os.path.join(resource_dir, "arrow_down.svg")
        arrow_next_path = os.path.join(resource_dir, "arrow_next.svg")

        if os.path.exists(arrow_down_path) and os.path.exists(arrow_next_path):
            style = """
            QTreeWidget {
                border: 1px solid #C0C0C0;
                outline: none;
            }
            QTreeWidget::item {
                padding: 2px 0px;
                border: none;
                min-height: 18px;
            }
            QTreeWidget::item:selected {
                background-color: #3399FF;
                color: white;
            }
            QTreeWidget::item:hover {
                background-color: #E0E0E0;
            }
            QTreeWidget::branch {
                background: transparent;
                border-image: none;
                image: none;
            }
            """
            return style
        return ""

    def setup_tab_project(self):
        layout = QVBoxLayout(self.tab_project)
        layout.setContentsMargins(0, 0, 0, 0)

        self.project_tree = DraggableTreeWidget()
        self.project_tree.setRootIsDecorated(True)
        self.project_tree.setItemsExpandable(True)
        self.project_tree.setHeaderHidden(True)
        self.project_tree.setIndentation(18)
        self.project_tree.setUniformRowHeights(True)
        self.project_tree.setIconSize(QSize(14, 14))
        self.project_tree.setStyleSheet(self._get_sidebar_style())

        self.project_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.project_tree.customContextMenuRequested.connect(self.show_context_menu)
        self.project_tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.project_tree.itemExpanded.connect(self._on_item_expanded)

        layout.addWidget(self.project_tree)

    def setup_tab_calibration(self):
        layout = QVBoxLayout(self.tab_calibration)
        layout.setContentsMargins(0, 0, 0, 0)
        self.calibration_list = QTreeWidget()
        self.calibration_list.setHeaderHidden(True)
        self.calibration_list.setStyleSheet("border: 1px solid #C0C0C0;")
        layout.addWidget(self.calibration_list)

    def _get_project_root_of(self, item):
        if item is None:
            return None
        temp = item
        while temp.parent() is not None:
            temp = temp.parent()
        return temp

    def on_item_double_clicked(self, item, column):
        if item.childCount() == 0:
            text = item.text(0)
            _, ext = os.path.splitext(text)
            if ext.lower() in self.app_config["valid_extensions"]:
                path_parts = []
                temp = item
                project_root = None

                while temp.parent() is not None:
                    if temp.parent().parent() is None:
                        project_root = temp.parent()
                        path_parts.insert(0, temp.text(0))
                        break
                    else:
                        path_parts.insert(0, temp.text(0))
                        temp = temp.parent()

                if project_root:
                    project_name = project_root.text(0)
                    relative_path = os.path.join(*path_parts)
                    self.sig_open_editor.emit(project_name, relative_path)

    def show_context_menu(self, pos):
        item = self.project_tree.itemAt(pos)
        if item is None:
            return

        project_root = self._get_project_root_of(item)
        project_name = project_root.text(0)

        if item == project_root:
            self._show_project_context_menu(project_name, pos)
            return

        parent = item.parent()
        if parent == project_root:
            self._show_item_context_menu(project_name, item.text(0), pos)
            return

        item_node = item
        while item_node.parent() != project_root:
            item_node = item_node.parent()
        item_name = item_node.text(0)

        if item.text(0) in ["Image", "Video"]:
            self._show_media_folder_context_menu(project_name, item_name, item.text(0), pos)
        elif item.parent() and item.parent().text(0) in ["Image", "Video"]:
            media_type = item.parent().text(0)
            file_name = item.text(0)
            self._show_file_context_menu(project_name, item_name, media_type, file_name, pos)

    def _show_project_context_menu(self, project_name, pos):
        menu = QMenu(self)
        act_new_item = menu.addAction("New Item...")
        act_open_proj = menu.addAction("Open Project...")
        act_open_item = menu.addAction("Open Item...")
        act_paste = menu.addAction("Paste")
        menu.addSeparator()
        act_rename = menu.addAction("Rename")
        act_delete = menu.addAction("Delete")
        menu.addSeparator()
        act_save_as = menu.addAction("Save As...")

        action = menu.exec(self.project_tree.mapToGlobal(pos))

        if action == act_new_item:
            self.sig_new_item.emit(project_name)
        elif action == act_open_proj:
            self.sig_import_file.emit(project_name)
        elif action == act_open_item:
            self.sig_import_item.emit(project_name)
        elif action == act_paste:
            self.sig_paste_to_project.emit(project_name)
        elif action == act_delete:
            self.sig_delete.emit(project_name)
        elif action == act_rename:
            self.sig_rename.emit(project_name)
        elif action == act_save_as:
            self.sig_save_as.emit(project_name)

    def _show_item_context_menu(self, project_name, folder_name, pos):
        menu = QMenu(self)
        act_open_image = menu.addAction("Open Image...")
        act_open_video = menu.addAction("Open Video...")
        menu.addSeparator()
        act_copy = menu.addAction("Copy")
        act_cut = menu.addAction("Cut")
        menu.addSeparator()
        act_rename = menu.addAction("Rename")
        act_delete = menu.addAction("Delete")

        action = menu.exec(self.project_tree.mapToGlobal(pos))

        if action == act_open_image:
            self.sig_item_open_media.emit(
                project_name,
                folder_name,
                "Image",
            )
        elif action == act_open_video:
            self.sig_item_open_media.emit(
                project_name,
                folder_name,
                "Video",
            )
        elif action == act_copy:
            self.sig_item_copy.emit(project_name, folder_name)
        elif action == act_cut:
            self.sig_item_cut.emit(project_name, folder_name)
        elif action == act_rename:
            self.sig_item_rename.emit(project_name, folder_name)
        elif action == act_delete:
            self.sig_item_delete.emit(project_name, folder_name)

    def _show_file_context_menu(self, project_name, item_name, media_type, file_name, pos):
        menu = QMenu(self)
        act_copy = menu.addAction("Copy")
        act_cut = menu.addAction("Cut")
        menu.addSeparator()
        act_rename = menu.addAction("Rename")
        act_delete = menu.addAction("Delete")

        action = menu.exec(self.project_tree.mapToGlobal(pos))

        if action == act_copy:
            self.sig_file_copy.emit(project_name, item_name, media_type, file_name)
        elif action == act_cut:
            self.sig_file_cut.emit(project_name, item_name, media_type, file_name)
        elif action == act_rename:
            self.sig_file_rename.emit(project_name, item_name, media_type, file_name, "")
        elif action == act_delete:
            self.sig_file_delete.emit(project_name, item_name, media_type, file_name)

    def _show_media_folder_context_menu(self, project_name, item_name, media_type, pos):
        menu = QMenu(self)
        act_paste = menu.addAction("Paste")

        action = menu.exec(self.project_tree.mapToGlobal(pos))

        if action == act_paste:
            self.sig_file_paste.emit(project_name, item_name, media_type)

    def add_project_item(self, project_name, project_path):
        items = self.project_tree.findItems(project_name, Qt.MatchFlag.MatchExactly)
        if not items:
            item = QTreeWidgetItem(self.project_tree)
            item.setText(0, project_name)
            item.setIcon(0, self.icon_dir)
            item.setData(0, Qt.ItemDataRole.UserRole, project_path)
            self.project_tree.addTopLevelItem(item)
            item.setExpanded(True)
            self.project_tree.setCurrentItem(item)

    def add_structure_item(self, project_name, folder_name, item_path):
        items = self.project_tree.findItems(project_name, Qt.MatchFlag.MatchExactly)
        if items:
            project_item = items[0]
            found = False
            for i in range(project_item.childCount()):
                if project_item.child(i).text(0) == folder_name:
                    found = True
                    break

            if not found:
                folder_item = QTreeWidgetItem(project_item)
                folder_item.setText(0, folder_name)
                folder_item.setIcon(0, self.icon_dir_closed)
                folder_item.setData(0, Qt.ItemDataRole.UserRole, item_path)

                image_node = QTreeWidgetItem(folder_item)
                image_node.setText(0, "Image")
                image_node.setIcon(0, self.icon_dir)
                image_node.setData(0, self.MEDIA_LOADED_ROLE, False)
                image_node.setChildIndicatorPolicy(
                    QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicatorWhenChildless
                )

                video_node = QTreeWidgetItem(folder_item)
                video_node.setText(0, "Video")
                video_node.setIcon(0, self.icon_dir)
                video_node.setData(0, self.MEDIA_LOADED_ROLE, False)
                video_node.setChildIndicatorPolicy(
                    QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicatorWhenChildless
                )

                self._watch_item_media(item_path, project_name, folder_name)
                self._refresh_media_node(
                    project_name, folder_name, "Image"
                )
                self._refresh_media_node(
                    project_name, folder_name, "Video"
                )

            project_item.setExpanded(True)

    @staticmethod
    def _normalize_media_path(path):
        if not isinstance(path, str) or not path.strip():
            return None
        return os.path.normcase(os.path.abspath(os.path.normpath(path)))

    def _is_media_hidden(self, media_dir, file_name):
        full_path = self._normalize_media_path(
            os.path.join(media_dir, file_name)
        )
        return full_path in self._hidden_media_paths

    def _hidden_names_for_media_dir(self, media_dir):
        normalized_dir = self._normalize_media_path(media_dir)
        if normalized_dir is None:
            return ()
        return tuple(
            self._hidden_media_names_by_dir.get(normalized_dir, ())
        )

    def _add_hidden_media_path(self, path):
        if path is None:
            return
        self._hidden_media_paths.add(path)
        directory = os.path.dirname(path)
        self._hidden_media_names_by_dir.setdefault(directory, set()).add(
            os.path.normcase(os.path.basename(path))
        )

    def _discard_hidden_media_path(self, path):
        if path is None:
            return
        self._hidden_media_paths.discard(path)
        directory = os.path.dirname(path)
        hidden_names = self._hidden_media_names_by_dir.get(directory)
        if hidden_names is None:
            return
        hidden_names.discard(os.path.normcase(os.path.basename(path)))
        if not hidden_names:
            del self._hidden_media_names_by_dir[directory]

    @pyqtSlot(list)
    def set_hidden_media_paths(self, paths):
        normalized_paths = {
            normalized
            for path in paths
            if (normalized := self._normalize_media_path(path)) is not None
        }
        self._hidden_media_paths.clear()
        self._hidden_media_names_by_dir.clear()
        for path in normalized_paths:
            self._add_hidden_media_path(path)

    @pyqtSlot(QTreeWidgetItem)
    def _on_item_expanded(self, item):
        if item is None or item.text(0) not in ("Image", "Video"):
            return
        if item.data(0, self.MEDIA_LOADED_ROLE):
            return
        folder_item = item.parent()
        if folder_item is None:
            return
        project_item = folder_item.parent()
        if project_item is None:
            return
        item_path = folder_item.data(0, Qt.ItemDataRole.UserRole)
        media_dir = (
            os.path.join(item_path, item.text(0)) if item_path else None
        )
        cached_names = self._media_name_cache.get(media_dir)
        if (
            cached_names is not None
            and not self.scan_view_model.is_scan_pending(media_dir)
        ):
            self._apply_media_scan(
                project_item.text(0),
                folder_item.text(0),
                item.text(0),
                media_dir,
                cached_names,
            )
            return
        self._refresh_media_node(
            project_item.text(0), folder_item.text(0), item.text(0)
        )

    def _watch_item_media(self, item_path, project_name, item_name):
        image_dir = os.path.join(item_path, "Image")
        video_dir = os.path.join(item_path, "Video")
        for media_dir in (image_dir, video_dir):
            if (
                media_dir not in self.watched_paths
                and self.fs_watcher.addPath(media_dir)
            ):
                self.watched_paths[media_dir] = (project_name, item_name, os.path.basename(media_dir))

    def _unwatch_item_media(self, item_path):
        image_dir = os.path.join(item_path, "Image")
        video_dir = os.path.join(item_path, "Video")
        for media_dir in (image_dir, video_dir):
            if media_dir in self.watched_paths:
                self.fs_watcher.removePath(media_dir)
                del self.watched_paths[media_dir]
            self.scan_view_model.cancel_media_scan(media_dir)
            self._media_name_cache.pop(media_dir, None)

    @pyqtSlot(str, str)
    def unwatch_item_media(self, project_name, folder_name):
        items = self.project_tree.findItems(project_name, Qt.MatchFlag.MatchExactly)
        if items:
            for i in range(items[0].childCount()):
                child = items[0].child(i)
                if child.text(0) == folder_name:
                    item_path = child.data(0, Qt.ItemDataRole.UserRole)
                    if item_path:
                        self._unwatch_item_media(item_path)
                    break

    @pyqtSlot(str)
    def unwatch_project_media(self, project_name):
        items = self.project_tree.findItems(project_name, Qt.MatchFlag.MatchExactly)
        if items:
            proj_item = items[0]
            for i in range(proj_item.childCount()):
                child = proj_item.child(i)
                item_path = child.data(0, Qt.ItemDataRole.UserRole)
                if item_path:
                    self._unwatch_item_media(item_path)

    @pyqtSlot(str)
    def on_directory_changed(self, path):
        info = self.watched_paths.get(path)
        if not info:
            return
        project_name, item_name, media_type = info
        self._refresh_media_node(project_name, item_name, media_type)

    @pyqtSlot(str, str, str, str)
    def notify_media_created(
        self, project_name, item_name, media_type, full_path
    ):
        """Reveal a newly captured media file without relying on OS watcher timing."""
        if media_type not in ("Image", "Video"):
            return
        self.reveal_media_file(
            project_name,
            item_name,
            media_type,
            full_path,
        )

    @pyqtSlot(str, str, str, str)
    def reveal_media_file(
        self, project_name, item_name, media_type, full_path
    ):
        """Render a media path already validated by the ViewModel."""
        if media_type not in ("Image", "Video"):
            return
        project_items = self.project_tree.findItems(
            project_name, Qt.MatchFlag.MatchExactly
        )
        if not project_items:
            return
        project_item = project_items[0]
        item_node = next(
            (
                project_item.child(index)
                for index in range(project_item.childCount())
                if project_item.child(index).text(0) == item_name
            ),
            None,
        )
        if item_node is None:
            return

        item_path = item_node.data(0, Qt.ItemDataRole.UserRole)
        if not item_path:
            return
        media_dir = os.path.join(item_path, media_type)
        expected_dir = os.path.normcase(os.path.abspath(media_dir))
        actual_dir = os.path.normcase(
            os.path.abspath(os.path.dirname(full_path))
        )
        if actual_dir != expected_dir:
            return

        media_node = next(
            (
                item_node.child(index)
                for index in range(item_node.childCount())
                if item_node.child(index).text(0) == media_type
            ),
            None,
        )
        if media_node is None:
            return

        filename = os.path.basename(full_path)
        if self._is_media_hidden(media_dir, filename):
            return
        media_node.setChildIndicatorPolicy(
            QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
        )
        existing_names = [
            media_node.child(index).text(0)
            for index in range(media_node.childCount())
        ]
        if filename not in existing_names:
            file_item = QTreeWidgetItem()
            file_item.setText(0, filename)
            file_item.setIcon(
                0,
                self.icon_image if media_type == "Image" else self.icon_video,
            )
            sort_key = filename.casefold()
            insert_at = next(
                (
                    index
                    for index, name in enumerate(existing_names)
                    if sort_key < name.casefold()
                ),
                media_node.childCount(),
            )
            media_node.insertChild(insert_at, file_item)

        cached_names = self._media_name_cache.get(media_dir)
        if cached_names is not None:
            self._media_name_cache[media_dir] = sorted(
                set(cached_names) | {filename},
                key=str.casefold,
            )
        project_item.setExpanded(True)
        item_node.setExpanded(True)
        was_expanded = media_node.isExpanded()
        media_node.setExpanded(True)
        if was_expanded:
            self._refresh_media_node(project_name, item_name, media_type)

    def _refresh_media_node(self, project_name, item_name, media_type):
        if self._shutting_down:
            return
        proj_items = self.project_tree.findItems(project_name, Qt.MatchFlag.MatchExactly)
        if not proj_items:
            return
        proj_item = proj_items[0]

        item_node = None
        for i in range(proj_item.childCount()):
            if proj_item.child(i).text(0) == item_name:
                item_node = proj_item.child(i)
                break
        if not item_node:
            return

        media_node = None
        for i in range(item_node.childCount()):
            if item_node.child(i).text(0) == media_type:
                media_node = item_node.child(i)
                break
        if not media_node:
            return

        item_path = item_node.data(0, Qt.ItemDataRole.UserRole)
        if not item_path:
            return
        media_dir = os.path.join(item_path, media_type)
        if media_dir not in self.watched_paths:
            return

        media_node.setData(0, self.MEDIA_LOADED_ROLE, False)
        self.scan_view_model.request_media_scan(
            project_name,
            item_name,
            media_type,
            media_dir,
            self.MEDIA_EXTENSIONS.get(media_type, ()),
            self._hidden_names_for_media_dir(media_dir),
        )

    def _apply_media_scan(
        self, project_name, item_name, media_type, media_dir, names
    ):
        current_info = self.watched_paths.get(media_dir)
        if current_info != (project_name, item_name, media_type):
            return

        project_items = self.project_tree.findItems(
            project_name, Qt.MatchFlag.MatchExactly
        )
        if not project_items:
            return
        project_item = project_items[0]
        item_node = next(
            (
                project_item.child(index)
                for index in range(project_item.childCount())
                if project_item.child(index).text(0) == item_name
            ),
            None,
        )
        if item_node is None:
            return
        media_node = next(
            (
                item_node.child(index)
                for index in range(item_node.childCount())
                if item_node.child(index).text(0) == media_type
            ),
            None,
        )
        if media_node is None:
            return

        names = [
            name
            for name in names
            if not self._is_media_hidden(media_dir, name)
        ]
        self._media_name_cache[media_dir] = names
        media_node.setChildIndicatorPolicy(
            QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
            if names
            else QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicatorWhenChildless
        )
        self.project_tree.viewport().update()

        if not media_node.isExpanded():
            media_node.takeChildren()
            media_node.setData(0, self.MEDIA_LOADED_ROLE, False)
            return

        media_node.takeChildren()
        self._append_media_batch(media_node, media_type, names, 0)

    def _append_media_batch(self, media_node, media_type, names, start):
        if media_node.treeWidget() is not self.project_tree:
            return
        end = min(start + 200, len(names))
        icon = self.icon_image if media_type == "Image" else self.icon_video
        for name in names[start:end]:
            file_item = QTreeWidgetItem(media_node)
            file_item.setText(0, name)
            file_item.setIcon(0, icon)
        if end < len(names):
            QTimer.singleShot(
                0,
                lambda: self._append_media_batch(
                    media_node, media_type, names, end
                ),
            )
        else:
            media_node.setData(0, self.MEDIA_LOADED_ROLE, True)

    def shutdown(self, wait_ms=0):
        self._shutting_down = True
        return self.scan_view_model.shutdown()

    @pyqtSlot()
    def _on_scan_shutdown_ready(self):
        self._media_name_cache.clear()
        self.set_loading_source("sidebar-media-scans", False)
        self.shutdown_ready.emit()

    def remove_project_item(self, project_name):
        items = self.project_tree.findItems(project_name, Qt.MatchFlag.MatchExactly)
        for item in items:
            for i in range(item.childCount()):
                child = item.child(i)
                item_path = child.data(0, Qt.ItemDataRole.UserRole)
                if item_path:
                    self._unwatch_item_media(item_path)
            index = self.project_tree.indexOfTopLevelItem(item)
            removed = self.project_tree.takeTopLevelItem(index)
            del removed

    def remove_item_node(self, project_name, folder_name):
        items = self.project_tree.findItems(project_name, Qt.MatchFlag.MatchExactly)
        if items:
            project_item = items[0]
            for i in range(project_item.childCount()):
                child = project_item.child(i)
                if child.text(0) == folder_name:
                    item_path = child.data(0, Qt.ItemDataRole.UserRole)
                    if item_path:
                        self._unwatch_item_media(item_path)
                    project_item.removeChild(child)
                    del child
                    break

    @pyqtSlot(str, str, str, str, bool)
    def remove_file_node(
        self,
        project_name,
        item_name,
        media_type,
        file_name,
        hide_from_scans,
    ):
        project_items = self.project_tree.findItems(
            project_name,
            Qt.MatchFlag.MatchExactly,
        )
        if not project_items:
            return
        project_item = project_items[0]
        item_node = next(
            (
                project_item.child(index)
                for index in range(project_item.childCount())
                if project_item.child(index).text(0) == item_name
            ),
            None,
        )
        if item_node is None:
            return

        item_path = item_node.data(0, Qt.ItemDataRole.UserRole)
        if not item_path:
            return
        media_dir = os.path.join(item_path, media_type)
        full_path = self._normalize_media_path(
            os.path.join(media_dir, file_name)
        )
        if hide_from_scans:
            self._add_hidden_media_path(full_path)
        else:
            self._discard_hidden_media_path(full_path)

        cached_names = self._media_name_cache.get(media_dir)
        if cached_names is not None:
            self._media_name_cache[media_dir] = [
                name
                for name in cached_names
                if os.path.normcase(name) != os.path.normcase(file_name)
            ]

        media_node = next(
            (
                item_node.child(index)
                for index in range(item_node.childCount())
                if item_node.child(index).text(0) == media_type
            ),
            None,
        )
        if media_node is None:
            return

        for index in range(media_node.childCount() - 1, -1, -1):
            child = media_node.child(index)
            if os.path.normcase(child.text(0)) == os.path.normcase(file_name):
                removed = media_node.takeChild(index)
                del removed

        visible_names = self._media_name_cache.get(media_dir)
        if visible_names is not None:
            media_node.setChildIndicatorPolicy(
                QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
                if visible_names
                else QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicatorWhenChildless
            )

        if not hide_from_scans:
            self._refresh_media_node(
                project_name,
                item_name,
                media_type,
            )

    def clear_all_items(self):
        for path in list(self.watched_paths.keys()):
            self.fs_watcher.removePath(path)
        self.watched_paths.clear()
        self.project_tree.clear()

    def collapse_all(self):
        root = self.project_tree.invisibleRootItem()

        def collapse_recursive(item):
            if item.isExpanded():
                item.setExpanded(False)
            for i in range(item.childCount()):
                collapse_recursive(item.child(i))

        collapse_recursive(root)

    def rename_project_item(self, old_name, new_name):
        items = self.project_tree.findItems(old_name, Qt.MatchFlag.MatchExactly)
        if items:
            proj_item = items[0]
            proj_item.setText(0, new_name)

            old_proj_path = proj_item.data(0, Qt.ItemDataRole.UserRole)
            parent_dir = os.path.dirname(old_proj_path)
            new_proj_path = os.path.join(parent_dir, new_name)
            proj_item.setData(0, Qt.ItemDataRole.UserRole, new_proj_path)

            for i in range(proj_item.childCount()):
                child = proj_item.child(i)
                item_name = child.text(0)
                new_item_path = os.path.join(new_proj_path, item_name)
                child.setData(0, Qt.ItemDataRole.UserRole, new_item_path)
                self._watch_item_media(new_item_path, new_name, item_name)

    def rename_item_node(self, project_name, old_name, new_name):
        items = self.project_tree.findItems(project_name, Qt.MatchFlag.MatchExactly)
        if items:
            project_item = items[0]
            for i in range(project_item.childCount()):
                child = project_item.child(i)
                if child.text(0) == old_name:
                    child.setText(0, new_name)

                    project_path = project_item.data(0, Qt.ItemDataRole.UserRole)
                    new_path = os.path.join(project_path, new_name)
                    child.setData(0, Qt.ItemDataRole.UserRole, new_path)

                    self._watch_item_media(new_path, project_name, new_name)
                    break

    def get_current_project(self):
        root = self._get_project_root_of(self.project_tree.currentItem())
        return root.text(0) if root else None

    def get_current_selection_info(self):
        item = self.project_tree.currentItem()
        if not item:
            return None, None, None
        project_root = self._get_project_root_of(item)
        if not project_root:
            return None, None, None
        project_name = project_root.text(0)

        if item == project_root:
            return project_name, None, 'PROJECT'

        folder_node = item
        while folder_node.parent() != project_root:
            folder_node = folder_node.parent()
            if folder_node is None:
                return project_name, None, 'PROJECT'
        return project_name, folder_node.text(0), 'ITEM'

    def get_sidebar_order(self):
        """Return path-stable Project order and per-Project Item order."""
        project_paths = []
        item_orders = {}
        for project_index in range(self.project_tree.topLevelItemCount()):
            project_item = self.project_tree.topLevelItem(project_index)
            project_path = project_item.data(0, Qt.ItemDataRole.UserRole)
            if not isinstance(project_path, str) or not project_path.strip():
                continue
            project_paths.append(project_path)
            item_orders[project_path] = [
                project_item.child(item_index).text(0)
                for item_index in range(project_item.childCount())
            ]
        return {
            "projects": project_paths,
            "items": item_orders,
        }

    def get_expanded_paths(self):
        paths = []
        root = self.project_tree.invisibleRootItem()

        def traverse(item, parent_path):
            if item.isExpanded():
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data:
                    paths.append(data)
                else:
                    if item.text(0) in ["Image", "Video"] and parent_path:
                        paths.append(os.path.join(parent_path, item.text(0)))
            for i in range(item.childCount()):
                child = item.child(i)
                child_parent_path = None
                child_data = child.data(0, Qt.ItemDataRole.UserRole)
                if child_data:
                    child_parent_path = child_data
                elif parent_path and child.text(0) in ["Image", "Video"]:
                    child_parent_path = os.path.join(parent_path, child.text(0))
                else:
                    child_parent_path = parent_path
                traverse(child, child_parent_path)

        traverse(root, None)
        return paths

    def restore_expanded_paths(self, paths):
        expanded_set = set(os.path.normpath(p) for p in paths)
        self.collapse_all()

        def expand_node(item):
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data:
                norm_data = os.path.normpath(data)
                if norm_data in expanded_set:
                    self._expand_with_parents(item)
            parent = item.parent()
            if parent and item.text(0) in ["Image", "Video"]:
                parent_path = parent.data(0, Qt.ItemDataRole.UserRole)
                if parent_path:
                    media_path = os.path.normpath(os.path.join(parent_path, item.text(0)))
                    if media_path in expanded_set:
                        self._expand_with_parents(item)
            for i in range(item.childCount()):
                expand_node(item.child(i))

        root = self.project_tree.invisibleRootItem()
        expand_node(root)

    def _expand_with_parents(self, item):
        while item is not None:
            item.setExpanded(True)
            item = item.parent()

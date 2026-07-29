#############################################################################
# @file App/Presentation/Views/Widgets/FileEditorWorkspace/ImageCanvas.py
# Author: TRAN NGUYEN HIEN
# Email: trannguyenhien29085@gmail.com
#############################################################################
from PyQt6.QtCore import QPoint, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QSizePolicy, QWidget


class ImageCanvas(QWidget):
    """Lightweight Qt image viewport with millimetre axes, zoom and pan."""

    X_BOUNDS = (0.0, 5.0)
    Y_BOUNDS = (0.0, 3.0)
    MIN_RANGE = 0.1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap()
        self._xlim = self.X_BOUNDS
        self._ylim = self.Y_BOUNDS
        self._pan_position = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setMinimumSize(240, 160)

    def set_pixmap(self, pixmap):
        self._pixmap = QPixmap(pixmap) if pixmap is not None else QPixmap()
        self.reset_view()

    def clear(self):
        self._pixmap = QPixmap()
        self._pan_position = None
        self.update()

    def reset_view(self):
        self._xlim = self.X_BOUNDS
        self._ylim = self.Y_BOUNDS
        self.update()

    def _plot_rect(self):
        available = QRectF(self.rect()).adjusted(58.0, 18.0, -18.0, -48.0)
        if available.width() <= 0 or available.height() <= 0:
            return QRectF()

        x_span = self._xlim[1] - self._xlim[0]
        y_span = self._ylim[1] - self._ylim[0]
        desired_ratio = x_span / y_span
        if available.width() / available.height() > desired_ratio:
            width = available.height() * desired_ratio
            left = available.left() + (available.width() - width) / 2.0
            return QRectF(left, available.top(), width, available.height())

        height = available.width() / desired_ratio
        top = available.top() + (available.height() - height) / 2.0
        return QRectF(available.left(), top, available.width(), height)

    def _source_rect(self):
        if self._pixmap.isNull():
            return QRectF()
        width = float(self._pixmap.width())
        height = float(self._pixmap.height())
        x0 = self._xlim[0] / self.X_BOUNDS[1] * width
        x1 = self._xlim[1] / self.X_BOUNDS[1] * width
        top = (self.Y_BOUNDS[1] - self._ylim[1]) / self.Y_BOUNDS[1] * height
        bottom = (self.Y_BOUNDS[1] - self._ylim[0]) / self.Y_BOUNDS[1] * height
        return QRectF(x0, top, x1 - x0, bottom - top)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), QColor("#202124"))

        plot_rect = self._plot_rect()
        if plot_rect.isEmpty():
            return

        if self._pixmap.isNull():
            painter.setPen(QColor("#b0b0b0"))
            painter.drawText(
                plot_rect,
                Qt.AlignmentFlag.AlignCenter,
                "No image loaded",
            )
            return

        painter.drawPixmap(plot_rect, self._pixmap, self._source_rect())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor("#c7c7c7"), 1.0))
        painter.drawRect(plot_rect)
        self._draw_axes(painter, plot_rect)

    def _draw_axes(self, painter, plot_rect):
        painter.setPen(QColor("#d8d8d8"))
        font_metrics = painter.fontMetrics()

        for index in range(6):
            ratio = index / 5.0
            value = self._xlim[0] + ratio * (
                self._xlim[1] - self._xlim[0]
            )
            x = plot_rect.left() + ratio * plot_rect.width()
            painter.drawLine(
                QPoint(round(x), round(plot_rect.bottom())),
                QPoint(round(x), round(plot_rect.bottom() + 5)),
            )
            label = f"{value:.2g}"
            label_width = font_metrics.horizontalAdvance(label)
            painter.drawText(
                round(x - label_width / 2),
                round(plot_rect.bottom() + 20),
                label,
            )

        for index in range(4):
            ratio = index / 3.0
            value = self._ylim[0] + ratio * (
                self._ylim[1] - self._ylim[0]
            )
            y = plot_rect.bottom() - ratio * plot_rect.height()
            painter.drawLine(
                QPoint(round(plot_rect.left() - 5), round(y)),
                QPoint(round(plot_rect.left()), round(y)),
            )
            label = f"{value:.2g}"
            label_width = font_metrics.horizontalAdvance(label)
            painter.drawText(
                round(plot_rect.left() - label_width - 9),
                round(y + font_metrics.ascent() / 2),
                label,
            )

        x_label = "x [mm]"
        painter.drawText(
            round(plot_rect.center().x() - font_metrics.horizontalAdvance(x_label) / 2),
            round(plot_rect.bottom() + 40),
            x_label,
        )

        painter.save()
        painter.translate(16.0, plot_rect.center().y())
        painter.rotate(-90.0)
        y_label = "y [mm]"
        painter.drawText(
            round(-font_metrics.horizontalAdvance(y_label) / 2),
            0,
            y_label,
        )
        painter.restore()

    def _data_position(self, position):
        plot_rect = self._plot_rect()
        if plot_rect.isEmpty() or not plot_rect.contains(position):
            return None
        x_ratio = (position.x() - plot_rect.left()) / plot_rect.width()
        y_ratio = (plot_rect.bottom() - position.y()) / plot_rect.height()
        return (
            self._xlim[0] + x_ratio * (self._xlim[1] - self._xlim[0]),
            self._ylim[0] + y_ratio * (self._ylim[1] - self._ylim[0]),
        )

    @staticmethod
    def _clamp_range(lower, upper, bounds):
        span = min(
            max(upper - lower, ImageCanvas.MIN_RANGE),
            bounds[1] - bounds[0],
        )
        center = (lower + upper) / 2.0
        lower = center - span / 2.0
        upper = center + span / 2.0
        if lower < bounds[0]:
            lower = bounds[0]
            upper = lower + span
        if upper > bounds[1]:
            upper = bounds[1]
            lower = upper - span
        return lower, upper

    def wheelEvent(self, event):
        anchor = self._data_position(event.position())
        if anchor is None or self._pixmap.isNull():
            event.ignore()
            return

        factor = 0.8 if event.angleDelta().y() > 0 else 1.25
        x0, x1 = self._xlim
        y0, y1 = self._ylim
        new_xlim = (
            anchor[0] - (anchor[0] - x0) * factor,
            anchor[0] + (x1 - anchor[0]) * factor,
        )
        new_ylim = (
            anchor[1] - (anchor[1] - y0) * factor,
            anchor[1] + (y1 - anchor[1]) * factor,
        )
        self._xlim = self._clamp_range(*new_xlim, self.X_BOUNDS)
        self._ylim = self._clamp_range(*new_ylim, self.Y_BOUNDS)
        self.update()
        event.accept()

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.RightButton
            and self._plot_rect().contains(event.position())
        ):
            self._pan_position = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_position is None:
            super().mouseMoveEvent(event)
            return

        plot_rect = self._plot_rect()
        if plot_rect.isEmpty():
            return
        delta = event.position() - self._pan_position
        self._pan_position = event.position()
        x_shift = -delta.x() / plot_rect.width() * (
            self._xlim[1] - self._xlim[0]
        )
        y_shift = delta.y() / plot_rect.height() * (
            self._ylim[1] - self._ylim[0]
        )
        self._xlim = self._clamp_range(
            self._xlim[0] + x_shift,
            self._xlim[1] + x_shift,
            self.X_BOUNDS,
        )
        self._ylim = self._clamp_range(
            self._ylim[0] + y_shift,
            self._ylim[1] + y_shift,
            self.Y_BOUNDS,
        )
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._pan_position = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

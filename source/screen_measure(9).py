# screen_measure.py
# On-image calibration & measurement tool (PySide6)
# Features:
#  - Paste/Open image, zoom & pan (MMB or Space+LMB)
#  - Calibrate by 2 points + known real length (any units string)
#  - Measure Line and Polyline; items persist on canvas
#  - Labels at midpoint (line) and halfway along path (polyline)
#  - Outline (black) + inner (cyan) rendering for visibility
#  - Export measurements to CSV
#  - Export annotated image (PNG/JPG)
#  - Clear image+measurements, clear measurements, undo last (Ctrl+Z),
#    delete selected measurements
#  - Recalibration updates all existing measurements automatically
#  - Guides: H/V/45° toggles; anchored to last LMB point; dashed.
#    Thin when tool is selected but no points yet; thick while placing points.
#
# Install: pip install PySide6
# Run:     python screen_measure.py
#
from PySide6 import QtCore, QtGui, QtWidgets
import math, csv, datetime, os

# Импорт ресурсов
try:
    import resources_rc
except ImportError:
    # Если ресурсный файл не найден, создаем заглушку
    pass

class MeasureItem:
    def __init__(self, kind, points, length_units_str, length_value, units, timestamp=None):
        self.kind = kind                  # 'line' | 'polyline'
        self.points = points[:]           # list[QPointF] in image coordinates
        self.length_units_str = length_units_str
        self.length_value = float(length_value)
        self.units = units
        self.timestamp = timestamp or datetime.datetime.now()

class ImageView(QtWidgets.QWidget):
    statusMessage  = QtCore.Signal(str)
    measureAdded   = QtCore.Signal(object)  # MeasureItem
    historyChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

        # image & view state
        self.image = QtGui.QImage()
        self._zoom = 1.0
        self._pan  = QtCore.QPointF(0, 0)
        self._dragging = False
        self._drag_origin = QtCore.QPoint()
        self._pan_origin  = QtCore.QPointF(0, 0)
        self._space_down  = False

        # modes & temp
        self.mode = 'idle'         # 'idle'|'calibrate'|'line'|'polyline'
        self.temp_points = []      # list[QPointF] in image coords

        # calibration
        self.scale_units_per_px = 1.0
        self.units = 'px'

        # history
        self.history = []          # list[MeasureItem]

        # guides
        self.guide_anchor_img = None
        self.guides_diag_enabled = True
        self.guide_h_enabled = True
        self.guide_v_enabled = True

    # ---------- image management ----------
    def setImage(self, img: QtGui.QImage):
        self.image = img.copy()
        self._zoom = 1.0
        self._pan  = QtCore.QPointF(0, 0)
        self.temp_points.clear()
        self.guide_anchor_img = None
        self.update()
        if not self.image.isNull():
            self.statusMessage.emit(f"Image loaded: {self.image.width()}x{self.image.height()} px")

    def pasteFromClipboard(self):
        cb = QtGui.QGuiApplication.clipboard()
        img = cb.image()
        if img.isNull():
            pm = cb.pixmap()
            if not pm.isNull():
                img = pm.toImage()
        if not img.isNull():
            self.setImage(img)
            return True
        return False

    # ---------- coordinates ----------
    def viewToImage(self, p: QtCore.QPointF) -> QtCore.QPointF:
        inv = 1.0 / max(self._zoom, 1e-9)
        x = (p.x() - self._pan.x()) * inv
        y = (p.y() - self._pan.y()) * inv
        return QtCore.QPointF(x, y)

    def imageToView(self, p: QtCore.QPointF) -> QtCore.QPointF:
        x = p.x() * self._zoom + self._pan.x()
        y = p.y() * self._zoom + self._pan.y()
        return QtCore.QPointF(x, y)

    # ---------- helpers ----------
    def pxDistance(self, a: QtCore.QPointF, b: QtCore.QPointF) -> float:
        return math.hypot(a.x()-b.x(), a.y()-b.y())

    def unitsDistance(self, a: QtCore.QPointF, b: QtCore.QPointF) -> float:
        return self.pxDistance(a, b) * self.scale_units_per_px

    # ---------- painting ----------
    def paintEvent(self, e: QtGui.QPaintEvent):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor(30, 30, 30))

        if not self.image.isNull():
            target_rect = QtCore.QRectF(
                self._pan,
                QtCore.QSizeF(self.image.width()*self._zoom, self.image.height()*self._zoom)
            )
            p.drawImage(target_rect, self.image, QtCore.QRectF(self.image.rect()))

        # persisted measurements
        p.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.TextAntialiasing)
        for item in self.history:
            self._drawMeasuredItem(p, item)

        # temp items (with outline)
        pen_outline = QtGui.QPen(QtGui.QColor(0, 0, 0, 220), 4)
        pen_outline.setCosmetic(True)
        pen_temp = QtGui.QPen(QtGui.QColor(0, 200, 255), 2)
        pen_temp.setCosmetic(True)

        if self.temp_points:
            for i, pt in enumerate(self.temp_points):
                vpt = self.imageToView(pt)
                self._drawHandle(p, vpt, label=str(i+1))

            if self.mode in ('line', 'calibrate') and len(self.temp_points) == 2:
                a, b = self.temp_points
                p.setPen(pen_outline); self._drawSegment(p, a, b)
                p.setPen(pen_temp);    self._drawSegment(p, a, b)
                mid = (a + b) * 0.5
                length_units = self.unitsDistance(a, b)
                self._drawFloatingText(p, self.imageToView(mid) + QtCore.QPointF(6, -6), self._fmt_len(length_units))

            elif self.mode == 'polyline' and len(self.temp_points) >= 2:
                total = 0.0
                for i in range(len(self.temp_points)-1):
                    a, b = self.temp_points[i], self.temp_points[i+1]
                    p.setPen(pen_outline); self._drawSegment(p, a, b)
                    p.setPen(pen_temp);    self._drawSegment(p, a, b)
                    total += self.unitsDistance(a, b)
                self._drawFloatingText(p, self.imageToView(self.temp_points[-1]) + QtCore.QPointF(8, -8),
                                       self._fmt_len(total))

        # guides: only in active modes and if we have an anchor
        if self.mode in ('calibrate','line','polyline') and self.guide_anchor_img is not None:
            thick = len(self.temp_points) > 0  # thick while placing points
            self._drawGuides(p, self.imageToView(self.guide_anchor_img), thick)

    def _makeGuidePens(self, thick: bool):
        # base widths (thick mode = current look)
        outer_thick = 4.0
        inner_thick = 2.0
        if thick:
            outer_w, inner_w = outer_thick, inner_thick
        else:
            # 3x thinner
            outer_w, inner_w = max(1.0, outer_thick/3.0), max(0.7, inner_thick/3.0)
        dash = [6, 6]
        pen_outer = QtGui.QPen(QtGui.QColor(0,0,0,200))
        pen_outer.setCosmetic(True)
        pen_outer.setWidthF(outer_w)
        pen_outer.setDashPattern(dash)
        pen_inner = QtGui.QPen(QtGui.QColor(255,255,255,230))
        pen_inner.setCosmetic(True)
        pen_inner.setWidthF(inner_w)
        pen_inner.setDashPattern(dash)
        return pen_outer, pen_inner

    def _drawGuides(self, painter: QtGui.QPainter, anchor_view: QtCore.QPointF, thick: bool):
        pen_outer, pen_inner = self._makeGuidePens(thick)
        w, h = self.width(), self.height()

        # Horizontal
        if self.guide_h_enabled:
            painter.setPen(pen_outer); painter.drawLine(0, int(anchor_view.y()), w, int(anchor_view.y()))
            painter.setPen(pen_inner); painter.drawLine(0, int(anchor_view.y()), w, int(anchor_view.y()))
        # Vertical
        if self.guide_v_enabled:
            painter.setPen(pen_outer); painter.drawLine(int(anchor_view.x()), 0, int(anchor_view.x()), h)
            painter.setPen(pen_inner); painter.drawLine(int(anchor_view.x()), 0, int(anchor_view.x()), h)

        if self.guides_diag_enabled:
            L = max(w, h) * 2
            painter.setPen(pen_outer); painter.drawLine(int(anchor_view.x()-L), int(anchor_view.y()-L),
                                                        int(anchor_view.x()+L), int(anchor_view.y()+L))
            painter.setPen(pen_inner); painter.drawLine(int(anchor_view.x()-L), int(anchor_view.y()-L),
                                                        int(anchor_view.x()+L), int(anchor_view.y()+L))
            painter.setPen(pen_outer); painter.drawLine(int(anchor_view.x()-L), int(anchor_view.y()+L),
                                                        int(anchor_view.x()+L), int(anchor_view.y()-L))
            painter.setPen(pen_inner); painter.drawLine(int(anchor_view.x()-L), int(anchor_view.y()+L),
                                                        int(anchor_view.x()+L), int(anchor_view.y()-L))

    def _drawHandle(self, painter, view_pt: QtCore.QPointF, label=None):
        r = 5
        painter.setBrush(QtGui.QColor(0, 200, 255, 160))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(QtCore.QRectF(view_pt.x()-r, view_pt.y()-r, 2*r, 2*r))
        if label:
            self._drawFloatingText(painter, view_pt + QtCore.QPointF(8, -8), label)

    def _drawSegment(self, painter, a_img: QtCore.QPointF, b_img: QtCore.QPointF):
        a = self.imageToView(a_img)
        b = self.imageToView(b_img)
        painter.drawLine(QtCore.QLineF(a, b))

    def _drawMeasuredItem(self, painter, item: 'MeasureItem'):
        # double-pass outline (black) + inner (cyan) for visibility
        outline = QtGui.QPen(QtGui.QColor(0,0,0,220), 4)
        outline.setCosmetic(True)
        inner = QtGui.QPen(QtGui.QColor(0, 200, 255), 2)
        inner.setCosmetic(True)

        if item.kind == 'line' and len(item.points) == 2:
            a, b = item.points
            painter.setPen(outline); self._drawSegment(painter, a, b)
            painter.setPen(inner);   self._drawSegment(painter, a, b)
            mid = (a + b) * 0.5
            self._drawFloatingText(painter, self.imageToView(mid) + QtCore.QPointF(6, -6), item.length_units_str)

        elif item.kind == 'polyline' and len(item.points) >= 2:
            pts = item.points
            for i in range(len(pts)-1):
                a, b = pts[i], pts[i+1]
                painter.setPen(outline); self._drawSegment(painter, a, b)
                painter.setPen(inner);   self._drawSegment(painter, a, b)
            half_pt = self._polyline_halfway_point(pts)
            self._drawFloatingText(painter, self.imageToView(half_pt) + QtCore.QPointF(6, -6), item.length_units_str)

    def _polyline_halfway_point(self, pts):
        if len(pts) == 1:
            return pts[0]
        seglens = []
        total = 0.0
        for i in range(len(pts)-1):
            d = self.pxDistance(pts[i], pts[i+1])
            seglens.append(d)
            total += d
        if total <= 0.0:
            return (pts[0] + pts[-1]) * 0.5
        half = total / 2.0
        acc = 0.0
        for i in range(len(pts)-1):
            a, b = pts[i], pts[i+1]
            if acc + seglens[i] >= half:
                remain = half - acc
                t = remain / seglens[i] if seglens[i] > 0 else 0.5
                return QtCore.QPointF(a.x() + (b.x()-a.x())*t, a.y() + (b.y()-a.y())*t)
            acc += seglens[i]
        return (pts[0] + pts[-1]) * 0.5

    def _drawFloatingText(self, painter, view_pt: QtCore.QPointF, text: str):
        font = painter.font()
        font.setPointSizeF(10)
        painter.setFont(font)
        # shadow box
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(0,0,0,180))
        metrics = QtGui.QFontMetrics(font)
        w = metrics.horizontalAdvance(text) + 8
        h = metrics.height() + 2
        rect = QtCore.QRectF(view_pt.x(), view_pt.y()-h, w, h)
        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, 4, 4)
        painter.drawPath(path)
        painter.setPen(QtGui.QColor(255,255,255))
        painter.drawText(rect.adjusted(4, 0, -4, 0), QtCore.Qt.AlignmentFlag.AlignVCenter, text)

    def _fmt_len(self, value: float) -> str:
        if self.units == 'px':
            return f"{value:.1f} px"
        if value >= 100:
            return f"{value:.1f} {self.units}"
        elif value >= 10:
            return f"{value:.2f} {self.units}"
        else:
            return f"{value:.3f} {self.units}"

    # ---------- history ops ----------
    def clearHistory(self):
        if self.history:
            self.history.clear()
            self.temp_points = []
            self.guide_anchor_img = None
            self.update()
            self.statusMessage.emit("Measurements cleared")
            self.historyChanged.emit()

    def undoLast(self):
        if self.history:
            self.history.pop()
            self.update()
            self.statusMessage.emit("Last measurement undone")
            self.historyChanged.emit()

    def deleteByIndices(self, indices):
        if not indices:
            return
        for idx in sorted(set(indices), reverse=True):
            if 0 <= idx < len(self.history):
                self.history.pop(idx)
        self.update()
        self.statusMessage.emit("Selected measurement(s) deleted")
        self.historyChanged.emit()

    def clearImageAndHistory(self):
        self.image = QtGui.QImage()
        self._zoom = 1.0
        self._pan  = QtCore.QPointF(0,0)
        self.temp_points.clear()
        self.history.clear()
        self.guide_anchor_img = None
        self.update()
        self.statusMessage.emit("Image and measurements cleared")
        self.historyChanged.emit()

    def recalcHistoryAfterCalibration(self):
        """Recompute all history item lengths using current scale_units_per_px and units."""
        if not self.history:
            return
        for item in self.history:
            length_px = 0.0
            if item.kind == 'line' and len(item.points) == 2:
                length_px = self.pxDistance(item.points[0], item.points[1])
            elif item.kind == 'polyline' and len(item.points) >= 2:
                for i in range(len(item.points)-1):
                    length_px += self.pxDistance(item.points[i], item.points[i+1])
            length_units = length_px * self.scale_units_per_px
            item.length_value = length_units
            item.units = self.units
            item.length_units_str = self._fmt_len(length_units)
        self.historyChanged.emit()
        self.update()

    # ---------- export annotated image ----------
    def exportAnnotatedImage(self):
        if self.image.isNull():
            self.statusMessage.emit("Nothing to export: no image")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export annotated image",
                                                        "annotated.png", "PNG (*.png);;JPEG (*.jpg *.jpeg)")
        if not path:
            return

        annotated = QtGui.QImage(self.image)  # start with base image
        painter = QtGui.QPainter(annotated)
        painter.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.TextAntialiasing)

        # temporarily force identity transform for image-space drawing
        old_zoom, old_pan = self._zoom, self._pan
        self._zoom, self._pan = 1.0, QtCore.QPointF(0,0)

        # draw persisted measurements
        for item in self.history:
            self._drawMeasuredItem(painter, item)

        # draw current temp geometry (if any complete)
        pen_outline = QtGui.QPen(QtGui.QColor(0,0,0,220), 4); pen_outline.setCosmetic(True)
        pen_temp    = QtGui.QPen(QtGui.QColor(0,200,255), 2); pen_temp.setCosmetic(True)

        if self.temp_points:
            if self.mode in ('line','calibrate') and len(self.temp_points) == 2:
                a, b = self.temp_points
                painter.setPen(pen_outline); self._drawSegment(painter, a, b)
                painter.setPen(pen_temp);    self._drawSegment(painter, a, b)
                mid = (a + b) * 0.5
                length_units = self.unitsDistance(a, b)
                self._drawFloatingText(painter, mid + QtCore.QPointF(6, -6), self._fmt_len(length_units))
            elif self.mode == 'polyline' and len(self.temp_points) >= 2:
                total = 0.0
                for i in range(len(self.temp_points)-1):
                    a, b = self.temp_points[i], self.temp_points[i+1]
                    painter.setPen(pen_outline); self._drawSegment(painter, a, b)
                    painter.setPen(pen_temp);    self._drawSegment(painter, a, b)
                    total += self.unitsDistance(a, b)
                self._drawFloatingText(painter, self.temp_points[-1] + QtCore.QPointF(8, -8),
                                       self._fmt_len(total))

        # restore view transform
        self._zoom, self._pan = old_zoom, old_pan
        painter.end()
        ok = annotated.save(path)
        if ok:
            self.statusMessage.emit(f"Annotated image saved: {os.path.basename(path)}")
        else:
            self.statusMessage.emit("Failed to save annotated image")

    # ---------- interaction ----------
    def mousePressEvent(self, e: QtGui.QMouseEvent):
        if e.button() == QtCore.Qt.MouseButton.MiddleButton or (e.button()==QtCore.Qt.LeftButton and self._space_down):
            self._dragging = True
            self._drag_origin = e.position().toPoint()
            self._pan_origin  = QtCore.QPointF(self._pan)
            return

        if e.button() == QtCore.Qt.MouseButton.RightButton:
            if self.mode == 'polyline' and len(self.temp_points) >= 2:
                # finalize polyline
                total = 0.0
                for i in range(len(self.temp_points)-1):
                    total += self.unitsDistance(self.temp_points[i], self.temp_points[i+1])
                item = MeasureItem('polyline', self.temp_points, self._fmt_len(total), total, self.units)
                self.history.append(item)
                self.measureAdded.emit(item)
                self.historyChanged.emit()
                self.temp_points = []
                self.update()
                return
            # cancel
            self.temp_points = []
            self.mode = 'idle'
            self.update()
            return

        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            if self.image.isNull():
                return
            imgpt = self.viewToImage(e.position())
            if imgpt.x() < 0 or imgpt.y() < 0 or imgpt.x() >= self.image.width() or imgpt.y() >= self.image.height():
                return
            # update guide anchor on left-click in active modes
            if self.mode in ('calibrate','line','polyline'):
                self.guide_anchor_img = imgpt

            if self.mode in ('calibrate', 'line', 'polyline'):
                self.temp_points.append(imgpt)
                if self.mode in ('calibrate', 'line') and len(self.temp_points) == 2:
                    if self.mode == 'calibrate':
                        self.finishCalibration()
                    else:
                        a, b = self.temp_points
                        length_units = self.unitsDistance(a, b)
                        item = MeasureItem('line', [a, b], self._fmt_len(length_units), length_units, self.units)
                        self.history.append(item)
                        self.measureAdded.emit(item)
                        self.historyChanged.emit()
                        self.temp_points = []
                    self.update()
                else:
                    self.update()

    def mouseMoveEvent(self, e: QtGui.QMouseEvent):
        if self._dragging:
            delta = e.position().toPoint() - self._drag_origin
            self._pan = self._pan_origin + QtCore.QPointF(delta.x(), delta.y())
            self.update()
            return
        if not self.image.isNull():
            imgpt = self.viewToImage(e.position())
            self.statusMessage.emit(f"Cursor: {imgpt.x():.1f}, {imgpt.y():.1f} px | Scale: {self.scale_units_per_px:.6f} {self.units}/px")

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        if e.button() == QtCore.Qt.MouseButton.MiddleButton or (e.button()==QtCore.Qt.LeftButton and self._space_down):
            self._dragging = False

    def wheelEvent(self, e: QtGui.QWheelEvent):
        if self.image.isNull():
            return
        delta = e.angleDelta().y()
        if delta == 0:
            return
        factor = 1.25 if delta > 0 else 0.8
        new_zoom = max(0.05, min(40.0, self._zoom * factor))

        cursor_view = e.position()
        img_before = self.viewToImage(cursor_view)
        self._zoom = new_zoom
        cursor_view_after = self.imageToView(img_before)
        shift = cursor_view - cursor_view_after
        self._pan += shift
        self.update()

    def keyPressEvent(self, e: QtGui.QKeyEvent):
        key = e.key()
        mod = e.modifiers()

        if key == QtCore.Qt.Key.Key_Space:
            self._space_down = True
            return

        if key == QtCore.Qt.Key.Key_Escape:
            self.temp_points = []
            self.mode = 'idle'
            self.update()
            return

        if key == QtCore.Qt.Key.Key_R:
            self._zoom = 1.0
            self._pan  = QtCore.QPointF(0,0)
            self.update()
            return

        if key == QtCore.Qt.Key.Key_C:
            self.mode = 'calibrate'
            self.temp_points = []
            self.statusMessage.emit("Calibration: click two points, then enter known length")
            self.update()
            return

        if key == QtCore.Qt.Key.Key_L:
            self.mode = 'line'
            self.temp_points = []
            self.statusMessage.emit("Line: click two points to measure")
            self.update()
            return

        if key == QtCore.Qt.Key.Key_P:
            self.mode = 'polyline'
            self.temp_points = []
            self.statusMessage.emit("Polyline: click points; right-click to finish")
            self.update()
            return

        if (mod & QtCore.Qt.KeyboardModifier.ControlModifier) and key == QtCore.Qt.Key.Key_Z:
            self.undoLast()
            return

        if (mod & QtCore.Qt.KeyboardModifier.ControlModifier) and key == QtCore.Qt.Key.Key_V:
            if not self.pasteFromClipboard():
                self.statusMessage.emit("Clipboard does not contain an image")
            return

        if (mod & QtCore.Qt.KeyboardModifier.ControlModifier) and key == QtCore.Qt.Key.Key_O:
            self.openImageDialog()
            return

        if (mod & QtCore.Qt.KeyboardModifier.ControlModifier) and key == QtCore.Qt.Key.Key_E:
            self.exportCSV()
            return

        super().keyPressEvent(e)

    def keyReleaseEvent(self, e: QtGui.QKeyEvent):
        if e.key() == QtCore.Qt.Key.Key_Space:
            self._space_down = False
            return
        super().keyReleaseEvent(e)

    def finishCalibration(self):
        if len(self.temp_points) != 2:
            return
        a, b = self.temp_points
        dpx = self.pxDistance(a, b)
        if dpx <= 0.0:
            self.statusMessage.emit("Calibration failed: zero distance")
            self.temp_points = []
            self.mode = 'idle'
            return
        length, ok = QtWidgets.QInputDialog.getDouble(self, "Calibration", "Real length:", 100.0, 0.000001, 1e12, 6)
        if not ok:
            self.temp_points = []
            self.mode = 'idle'
            self.update()
            return
        units, ok2 = QtWidgets.QInputDialog.getText(self, "Calibration", "Units (e.g., mm, cm, m, in):", text=(self.units if self.units!='px' else 'mm'))
        if not ok2 or not units.strip():
            units = self.units if self.units!='px' else 'units'
        self.units = units.strip()
        self.scale_units_per_px = length / dpx
        self.statusMessage.emit(f"Calibrated: {self.scale_units_per_px:.6f} {self.units}/px (dpx={dpx:.2f})")
        # Recalculate existing measurements to new scale/units
        self.recalcHistoryAfterCalibration()
        self.temp_points = []
        self.mode = 'idle'
        self.update()

    def openImageDialog(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open image", "", "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)")
        if path:
            img = QtGui.QImage(path)
            if not img.isNull():
                self.setImage(img)
            else:
                self.statusMessage.emit("Failed to load image")

    def exportCSV(self):
        if not self.history:
            self.statusMessage.emit("Nothing to export")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export CSV", "measurements.csv", "CSV Files (*.csv)")
        if not path:
            return
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f, delimiter=';')
            w.writerow(["timestamp","kind","units","length_value","length_label","points"])
            for item in self.history:
                pts = "|".join([f"{p.x():.2f},{p.y():.2f}" for p in item.points])
                w.writerow([item.timestamp.isoformat(), item.kind, item.units, f"{item.length_value:.6f}", item.length_units_str, pts])
        self.statusMessage.emit(f"Exported {len(self.history)} items to {os.path.basename(path)}")

class SidePanel(QtWidgets.QWidget):
    def __init__(self, view: ImageView, parent=None):
        super().__init__(parent)
        self.view = view
        self.setFixedWidth(340)

        self.list = QtWidgets.QListWidget()
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)

        self.lblScale = QtWidgets.QLabel("Scale: 1.000000 units/px, units=px")
        self.lblHint  = QtWidgets.QLabel("Hotkeys: C/L/P, Ctrl+V/O/E, Ctrl+Z, R, Esc\nPan: MMB drag or hold Space + LMB\nRight-click to finish polyline.")
        self.lblHint.setStyleSheet("color: #aaa;")

        btnCal     = QtWidgets.QPushButton("Calibrate (C)")
        btnLine    = QtWidgets.QPushButton("Line (L)")
        btnPoly    = QtWidgets.QPushButton("Polyline (P)")
        btnPaste   = QtWidgets.QPushButton("Paste (Ctrl+V)")
        btnOpen    = QtWidgets.QPushButton("Open (Ctrl+O)")
        btnExport  = QtWidgets.QPushButton("Export CSV (Ctrl+E)")
        btnExportImg = QtWidgets.QPushButton("Export Annotated Image")
        btnReset   = QtWidgets.QPushButton("Reset View (R)")
        btnUndo    = QtWidgets.QPushButton("Undo last (Ctrl+Z)")
        btnDelSel  = QtWidgets.QPushButton("Delete selected")
        btnClearM  = QtWidgets.QPushButton("Clear measurements")
        btnClearAll= QtWidgets.QPushButton("Clear image + measurements")
        self.chkH  = QtWidgets.QCheckBox("Horizontal guide")
        self.chkV  = QtWidgets.QCheckBox("Vertical guide")
        self.chkDiag = QtWidgets.QCheckBox("45° guides")
        self.chkH.setChecked(True)
        self.chkV.setChecked(True)
        self.chkDiag.setChecked(True)

        btnCal.clicked.connect(lambda: self._emitKey(QtCore.Qt.Key.Key_C))
        btnLine.clicked.connect(lambda: self._emitKey(QtCore.Qt.Key.Key_L))
        btnPoly.clicked.connect(lambda: self._emitKey(QtCore.Qt.Key.Key_P))
        btnPaste.clicked.connect(lambda: self._emitKey(QtCore.Qt.Key.Key_V, ctrl=True))
        btnOpen.clicked.connect(lambda: self._emitKey(QtCore.Qt.Key.Key_O, ctrl=True))
        btnExport.clicked.connect(lambda: self._emitKey(QtCore.Qt.Key.Key_E, ctrl=True))
        btnExportImg.clicked.connect(self.view.exportAnnotatedImage)
        btnReset.clicked.connect(lambda: self._emitKey(QtCore.Qt.Key.Key_R))
        btnUndo.clicked.connect(self.onUndo)
        btnDelSel.clicked.connect(self.onDeleteSelected)
        btnClearM.clicked.connect(self.onClearMeasurements)
        btnClearAll.clicked.connect(self.onClearAll)
        self.chkH.stateChanged.connect(self.onGuidesChanged)
        self.chkV.stateChanged.connect(self.onGuidesChanged)
        self.chkDiag.stateChanged.connect(self.onGuidesChanged)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.lblScale)
        layout.addWidget(self.lblHint)
        layout.addWidget(btnCal)
        layout.addWidget(btnLine)
        layout.addWidget(btnPoly)
        layout.addSpacing(8)
        layout.addWidget(btnPaste)
        layout.addWidget(btnOpen)
        layout.addWidget(btnExport)
        layout.addWidget(btnExportImg)
        layout.addSpacing(8)
        layout.addWidget(btnReset)
        layout.addWidget(btnUndo)
        layout.addWidget(btnDelSel)
        layout.addSpacing(8)
        layout.addWidget(btnClearM)
        layout.addWidget(btnClearAll)
        layout.addSpacing(8)
        layout.addWidget(self.chkH)
        layout.addWidget(self.chkV)
        layout.addWidget(self.chkDiag)
        layout.addSpacing(8)
        layout.addWidget(QtWidgets.QLabel("History:"))
        layout.addWidget(self.list, 1)

        # signals
        self.view.measureAdded.connect(self.onMeasureAdded)
        self.view.historyChanged.connect(self.refreshListFromHistory)
        self.view.statusMessage.connect(self.onStatus)

        # periodic scale label update
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.refreshScale)
        self._timer.start(300)

        QtCore.QTimer.singleShot(0, self.refreshListFromHistory)

        # allow Delete key on the list to remove selected
        self.list.keyPressEvent = self._listKeyPressWrap(self.list.keyPressEvent)

    def _listKeyPressWrap(self, orig):
        def handler(e: QtGui.QKeyEvent):
            if e.key() in (QtCore.Qt.Key.Key_Delete, QtCore.Qt.Key.Key_Backspace):
                self.onDeleteSelected()
                return
            return orig(e)
        return handler

    def _emitKey(self, key, ctrl=False):
        ev = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, key,
                             (QtCore.Qt.KeyboardModifier.ControlModifier if ctrl else QtCore.Qt.KeyboardModifier.NoModifier))
        QtWidgets.QApplication.postEvent(self.view, ev)

    def onGuidesChanged(self, state):
        self.view.guide_h_enabled = self.chkH.isChecked()
        self.view.guide_v_enabled = self.chkV.isChecked()
        self.view.guides_diag_enabled = self.chkDiag.isChecked()
        self.view.update()

    def refreshListFromHistory(self):
        self.list.clear()
        for item in self.view.history:
            ts = item.timestamp.strftime("%H:%M:%S")
            text = f"[{ts}] {item.kind}: {item.length_units_str} ({len(item.points)} pts)"
            self.list.addItem(text)

    def onUndo(self):
        self.view.undoLast()

    def onDeleteSelected(self):
        rows = sorted({i.row() for i in self.list.selectedIndexes()})
        if rows:
            self.view.deleteByIndices(rows)

    def onClearMeasurements(self):
        self.view.clearHistory()

    def onClearAll(self):
        self.view.clearImageAndHistory()

    def onMeasureAdded(self, item: MeasureItem):
        # keep list indices aligned with history by full refresh
        self.refreshListFromHistory()

    def onStatus(self, msg: str):
        self.lblHint.setText(msg)

    def refreshScale(self):
        self.lblScale.setText(f"Scale: {self.view.scale_units_per_px:.6f} {self.view.units}/px, units={self.view.units}")

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ScreenMeasure - Calibrate & Measure on Image")
        self.resize(1200, 800)
        
        # Установка иконки окна
        try:
            # Сначала пробуем загрузить из ресурсов
            self.setWindowIcon(QtGui.QIcon(":/icon2.ico"))
        except:
            # Если не удалось, пробуем загрузить из файла
            icon_path = "icon2.ico"
            if os.path.exists(icon_path):
                self.setWindowIcon(QtGui.QIcon(icon_path))
        self.view = ImageView()
        self.side = SidePanel(self.view)
        w = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(w)
        lay.setContentsMargins(0,0,0,0)
        lay.addWidget(self.view, 1)
        lay.addWidget(self.side)
        self.setCentralWidget(w)
        self.status = self.statusBar()
        self.view.statusMessage.connect(self.status.showMessage)

        # Auto-paste from clipboard on start
        QtCore.QTimer.singleShot(100, self.tryAutoPaste)

    def tryAutoPaste(self):
        if not self.view.pasteFromClipboard():
            self.status.showMessage("Tip: Copy a screenshot (Win+Shift+S), then press Ctrl+V here. Or use Ctrl+O to open a file.")

def main():
    import sys
    app = QtWidgets.QApplication(sys.argv)
    
    # Установка иконки для всего приложения
    try:
        # Сначала пробуем загрузить из ресурсов
        app.setWindowIcon(QtGui.QIcon(":/icon2.ico"))
    except:
        # Если не удалось, пробуем загрузить из файла
        icon_path = "icon2.ico"
        if os.path.exists(icon_path):
            app.setWindowIcon(QtGui.QIcon(icon_path))
    
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

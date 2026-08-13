from __future__ import annotations
import sys
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPushButton, QSplitter, QStatusBar, QToolBar, QVBoxLayout, QWidget)

from .models import SPECIAL_TYPES
from .services import CaseStore, copy_evidence, create_writing, human_size, open_file, prepare

KINDS = ["Escrito libre", "Acompaña documental", "Solicita", "Manifiesta", "Recurso", "Demanda", "Contestación"]

class DropList(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.setAcceptDrops(True); self.setDragDropMode(self.DragDropMode.InternalMove)
        self.setToolTip("Arrastre archivos aquí. También puede reordenarlos.")
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
        else: super().dragEnterEvent(e)
    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
        else: super().dragMoveEvent(e)
    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            self.window().add_evidence_paths([Path(u.toLocalFile()) for u in e.mimeData().urls()]); e.acceptProposedAction()
        else: super().dropEvent(e)

class NewWritingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Nuevo escrito")
        layout=QFormLayout(self); self.kind=QComboBox(); self.kind.addItems(KINDS)
        layout.addRow("Tipo de escrito", self.kind)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel|QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addRow(buttons)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.store=CaseStore(); self.case=None; self.current_kind="Escrito libre"
        self.setWindowTitle("Delivery para SISFE"); self.resize(1080, 680); self._build(); self.reload_cases()

    def _build(self):
        bar=QToolBar(); bar.setMovable(False); self.addToolBar(bar)
        for text, fn in [("Crear caso", self.create_case), ("Vincular carpeta", self.attach_case), ("Abrir carpeta del caso", self.open_case_folder)]:
            a=QAction(text,self); a.triggered.connect(fn); bar.addAction(a)
        root=QWidget(); outer=QVBoxLayout(root)
        header=QHBoxLayout(); header.addWidget(QLabel("Caso:")); self.case_combo=QComboBox(); self.case_combo.currentIndexChanged.connect(self.case_changed); header.addWidget(self.case_combo,1)
        outer.addLayout(header)
        actions=QHBoxLayout(); self.new_btn=QPushButton("+ NUEVO ESCRITO"); self.new_btn.clicked.connect(self.new_writing)
        self.add_btn=QPushButton("+ AGREGAR DOCUMENTAL"); self.add_btn.clicked.connect(self.pick_evidence)
        self.prepare_btn=QPushButton("PREPARAR PARA SISFE"); self.prepare_btn.setObjectName("primary"); self.prepare_btn.clicked.connect(self.do_prepare)
        for b in (self.new_btn,self.add_btn,self.prepare_btn): actions.addWidget(b)
        outer.addLayout(actions)
        split=QSplitter(); left=QWidget(); ll=QVBoxLayout(left); ll.addWidget(QLabel("Escritos del caso")); self.writings=QListWidget(); self.writings.itemDoubleClicked.connect(lambda i: open_file(Path(i.data(Qt.ItemDataRole.UserRole))))
        ll.addWidget(self.writings); self.open_writing=QPushButton("Abrir en Word"); self.open_writing.clicked.connect(self.open_selected_writing); ll.addWidget(self.open_writing)
        right=QWidget(); rl=QVBoxLayout(right); rl.addWidget(QLabel("Documental (arrastre y ordene)")); self.evidence=DropList(); rl.addWidget(self.evidence)
        row=QHBoxLayout(); remove=QPushButton("Quitar"); remove.clicked.connect(lambda: [self.evidence.takeItem(self.evidence.row(i)) for i in self.evidence.selectedItems()]); clear=QPushButton("Limpiar lista"); clear.clicked.connect(self.evidence.clear); row.addWidget(remove); row.addWidget(clear); rl.addLayout(row)
        split.addWidget(left); split.addWidget(right); split.setSizes([430,600]); outer.addWidget(split)
        hint=QLabel("Doble clic abre un escrito. La preparación convierte, unifica y controla automáticamente 3 MB (común) o 6 MB (demanda/contestación).")
        hint.setWordWrap(True); outer.addWidget(hint); self.setCentralWidget(root); self.setStatusBar(QStatusBar())
        self.setStyleSheet("""QMainWindow{background:#f4f6f8} QWidget{font-size:14px} QPushButton{padding:10px 14px} QPushButton#primary{background:#1769aa;color:white;font-weight:700;border-radius:4px} QListWidget{background:white;border:1px solid #ccd3da;padding:6px} QToolBar{background:white;spacing:8px;padding:5px}""")

    def reload_cases(self, select=None):
        self.case_combo.blockSignals(True); self.case_combo.clear()
        for c in self.store.cases: self.case_combo.addItem(c.name, c)
        if select:
            for i in range(self.case_combo.count()):
                if self.case_combo.itemData(i).path == select.path: self.case_combo.setCurrentIndex(i)
        self.case_combo.blockSignals(False); self.case_changed()
    def case_changed(self):
        self.case=self.case_combo.currentData(); self.refresh()
    def refresh(self):
        self.writings.clear(); self.evidence.clear()
        if not self.case: return
        self.case.ensure()
        for p in sorted(self.case.writings.glob("*.doc*"), reverse=True):
            item=QListWidgetItem(f"🟡  {p.name}"); item.setData(Qt.ItemDataRole.UserRole,str(p)); self.writings.addItem(item)
        for p in sorted(self.case.evidence.iterdir()):
            if p.is_file(): self._add_evidence_item(p)
    def create_case(self):
        name,ok=QInputDialog.getText(self,"Crear caso","Nombre del caso (por ejemplo, Gómez c/ SIJAM):")
        if not ok or not name.strip(): return
        root=QFileDialog.getExistingDirectory(self,"Elegir carpeta raíz para los casos")
        if root: self.reload_cases(self.store.add(name,Path(root)))
    def attach_case(self):
        folder=QFileDialog.getExistingDirectory(self,"Elegir carpeta existente del caso")
        if folder: self.reload_cases(self.store.attach(Path(folder)))
    def open_case_folder(self):
        if self.require_case(): open_file(self.case.path)
    def require_case(self):
        if self.case: return True
        QMessageBox.information(self,"Sin caso","Primero cree o vincule un caso."); return False
    def new_writing(self):
        if not self.require_case(): return
        d=NewWritingDialog(self)
        if d.exec():
            self.current_kind=d.kind.currentText()
            try: path=create_writing(self.case,self.current_kind); self.refresh(); open_file(path)
            except Exception as e: QMessageBox.critical(self,"No se pudo crear",str(e))
    def open_selected_writing(self):
        item=self.writings.currentItem()
        if item: open_file(Path(item.data(Qt.ItemDataRole.UserRole)))
    def pick_evidence(self):
        if not self.require_case(): return
        files=QFileDialog.getOpenFileNames(self,"Agregar documental","","Documentos (*.pdf *.doc *.docx *.odt *.rtf *.jpg *.jpeg *.png *.tif *.tiff *.bmp);;Todos (*.*)")[0]
        self.add_evidence_paths([Path(p) for p in files])
    def add_evidence_paths(self, paths):
        if not self.require_case(): return
        try:
            for p in copy_evidence(self.case,paths): self._add_evidence_item(p)
        except Exception as e: QMessageBox.critical(self,"No se pudo agregar",str(e))
    def _add_evidence_item(self,p):
        for i in range(self.evidence.count()):
            if self.evidence.item(i).data(Qt.ItemDataRole.UserRole)==str(p): return
        item=QListWidgetItem(p.name); item.setData(Qt.ItemDataRole.UserRole,str(p)); self.evidence.addItem(item)
    def do_prepare(self):
        if not self.require_case(): return
        item=self.writings.currentItem()
        if not item: QMessageBox.information(self,"Falta el escrito","Seleccione el escrito que desea presentar."); return
        writing=Path(item.data(Qt.ItemDataRole.UserRole)); docs=[Path(self.evidence.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.evidence.count())]
        kind,ok=QInputDialog.getItem(self,"Tipo y límite","Tipo de presentación:",KINDS,KINDS.index(self.current_kind) if self.current_kind in KINDS else 0,False)
        if not ok:return
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            files,notes=prepare(self.case,writing,docs,kind,lambda s:(self.statusBar().showMessage(s),QApplication.processEvents()))
        except Exception as e:
            QMessageBox.critical(self,"No se pudo preparar",str(e)); return
        finally: QApplication.restoreOverrideCursor()
        limit="6 MB" if kind in SPECIAL_TYPES else "3 MB"
        lines=[f"✓ {p.name} — {human_size(p.stat().st_size)}" for p in files]
        QMessageBox.information(self,"Presentación preparada",f"Archivos listos (límite {limit}):\n\n"+"\n".join(lines+notes)+"\n\nSe abrirá PARA PRESENTAR. Firme allí con Xólido y luego súbalos manualmente a SISFE.")
        open_file(self.case.output); self.statusBar().showMessage("Presentación lista para firma",5000)

def main():
    app=QApplication(sys.argv); app.setApplicationName("Delivery para SISFE")
    icon = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "preparador-sisfe.ico"
    if icon.exists(): app.setWindowIcon(QIcon(str(icon)))
    win=MainWindow(); win.show(); return app.exec()

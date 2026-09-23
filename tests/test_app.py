import os
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QMimeData, Qt, QUrl
from PyQt6.QtGui import QPalette
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QInputDialog, QMessageBox, QPushButton
from pypdf import PdfWriter

from gestor_documental.app import (
    ADD_PROFESSIONAL_LABEL,
    ExtendedMetadataDialog,
    HeirPickerDialog,
    ImportFileDialog,
    MainWindow,
    ModelPickerDialog,
    PATH_ROLE,
)
from gestor_documental.compilation_draft import load_compilation_history
from gestor_documental.case_spreadsheet_import import ImportOutcome, ImportRow, import_rows
from gestor_documental.ui.roles import ACTIVITY_ROLE, MOVEMENT_ROLE
from gestor_documental.services import (
    CompilationCancelled,
    SettingsStore,
    create_case,
    read_case_metadata,
    save_case_metadata,
    study_library_path,
)
from gestor_documental.study_database import StudyDatabase, study_database_path
from gestor_documental.sisfe_downloads import SisfeDownloadRegistry
from gestor_documental.ui.operation_status import OperationState
from gestor_documental.long_tasks import LongTask, TaskState
from gestor_documental.icons import ui_icon


class AppSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_main_window_starts_with_study_tree_and_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            case = create_case(study, "Gómez c/ SIJAM")
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            self.app.processEvents()
            self.assertEqual(window.windowTitle(), "FORO")
            self.assertEqual(
                [button.text() for button in window.limit_buttons.values()],
                ["1 MB", "3 MB", "6 MB", "20 MB"],
            )
            # El límite habitual se conserva; volver a tocarlo deja la
            # presentación sin compresión, al tamaño natural.
            self.assertTrue(window.limit_buttons[3 * 1024 * 1024].isChecked())
            window.choose_presentation_limit(3 * 1024 * 1024)
            self.assertEqual(window.selected_presentation_limit(), 0)
            self.assertFalse(
                any(button.isChecked() for button in window.limit_buttons.values())
            )
            window.choose_presentation_limit(3 * 1024 * 1024)
            self.assertEqual(
                window.metadata_edits["CUIJ"].placeholderText(),
                "Número de expediente",
            )
            self.assertEqual(
                tuple(window.metadata_edits),
                ("Actor", "Demandado", "Causa", "CUIJ", "Radicación"),
            )
            self.assertEqual(window.professional_combo.itemText(0), ADD_PROFESSIONAL_LABEL)
            self.assertEqual(
                window.professional_combo.currentText(),
                ADD_PROFESSIONAL_LABEL,
            )
            self.assertFalse(window.professional_settings_button.icon().isNull())
            settings_actions = [action.text() for action in window.professional_settings_button.menu().actions()]
            self.assertEqual(settings_actions, [
                "Configuración",
                "Crear copia de seguridad del Estudio",
                "Restaurar copia de seguridad del Estudio",
                "Importar casos",
                "Sincronizar todos los expedientes",
            ])
            self.assertEqual(window.work_tabs.count(), 2)
            self.assertEqual(window.work_tabs.tabText(window.files_tab_index), "Archivos")
            self.assertEqual(window.activity_tab_index, -1)
            self.assertEqual(
                window.work_tabs.tabText(window.portal_tab_index),
                "Expediente · 0",
            )
            self.assertEqual(window.pending_tab_index, -1)
            self.assertIs(window.compilation_card.parentWidget(), window.presentation_column)
            self.assertIs(window.presentation_column.parentWidget(), window.workspace_splitter)
            self.assertIs(window.workspace_splitter.widget(0), window.work_tabs)
            self.assertEqual(window.presentation_column.minimumWidth(), 250)
            self.assertGreaterEqual(window._visible_workspace_sizes[1], 400)
            self.assertEqual(window.compilation_count.text(), "0 elementos")
            self.assertEqual(window.sisfe_status.state, OperationState.IDLE)
            self.assertIn("expediente", window.search.placeholderText().lower())
            self.assertEqual(window.case_tree.topLevelItem(0).childCount(), 1)
            self.assertFalse(window.case_tree.topLevelItem(0).child(0).icon(0).isNull())
            self.assertNotEqual(
                window.case_tree.topLevelItem(0).icon(0).cacheKey(),
                window.case_tree.topLevelItem(0).child(0).icon(0).cacheKey(),
            )
            self.assertEqual(
                window.case_tree.palette().color(QPalette.ColorRole.Highlight).alpha(),
                0,
            )
            icon_controls = [
                button
                for button in window.findChildren(QPushButton)
                if button.objectName() in {"iconOnly", "iconQuiet"}
            ]
            self.assertGreaterEqual(len(icon_controls), 6)
            self.assertTrue(all(button.accessibleName() for button in icon_controls))
            self.assertTrue(window.quick_access.isEnabled())
            self.assertEqual(window.quick_access.__class__.__module__, "gestor_documental.ui.case_files")
            self.assertEqual(window.case_files.__class__.__module__, "gestor_documental.ui.case_files")
            # Documentos frecuentes vive en un panel flotante y pequeño.
            self.assertFalse(window.quick_panel.isVisible())
            window.toggle_quick_access()
            self.assertTrue(window.quick_panel.isVisible())
            window.toggle_quick_access()
            self.assertFalse(window.quick_panel.isVisible())
            self.assertTrue(study_library_path(study).is_dir())
            window.reload_cases(case.path)
            self.assertEqual(window.case_title.text(), case.name)
            window.close()

    def test_activity_tab_unifies_sources_and_navigates_to_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            case = create_case(study, "Pérez c/ Aseguradora")
            save_case_metadata(
                case,
                {
                    "Documentación pendiente": "DNI\nRecibo de sueldo",
                    "Documentación recibida": "DNI",
                },
            )
            with StudyDatabase(study_database_path(study)) as database:
                expediente = database.import_case(case)
                database.add_movement(
                    expediente.id,
                    "Audiencia fijada para el 18/09/2026 a las 09:30",
                    source="sisfe",
                    external_id="audiencia-1",
                )
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            store.add_professional("Dra. Ana Pérez")
            window = MainWindow(store)
            window.set_case(case)

            self.assertEqual(window.activity_list.count(), 2)
            self.assertEqual(window.work_tabs.count(), 2)
            pending_item = next(
                window.activity_list.item(index)
                for index in range(window.activity_list.count())
                if window.activity_list.item(index).data(ACTIVITY_ROLE)["target"] == "pending"
            )
            window.activity_list.setCurrentItem(pending_item)
            window.open_selected_activity()
            self.assertEqual(window.work_tabs.currentIndex(), window.files_tab_index)
            self.assertEqual(window.pending_documents_list.currentItem().text(), "Recibo de sueldo")

            portal_item = next(
                window.activity_list.item(index)
                for index in range(window.activity_list.count())
                if window.activity_list.item(index).data(ACTIVITY_ROLE)["target"] == "portal"
            )
            window.activity_list.setCurrentItem(portal_item)
            window.open_selected_activity()
            self.assertEqual(window.work_tabs.currentIndex(), window.portal_tab_index)
            self.assertEqual(
                window.novedades_list.currentItem().data(MOVEMENT_ROLE)["external_id"],
                "audiencia-1",
            )
            window.work_tabs.setCurrentIndex(window.activity_tab_index)
            window.activity_list.setCurrentItem(portal_item)
            self.assertTrue(window.confirm_activity_button.isEnabled())
            with patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ):
                window.confirm_selected_activity()
            confirmed_item = next(
                window.activity_list.item(index)
                for index in range(window.activity_list.count())
                if window.activity_list.item(index).data(ACTIVITY_ROLE)["target"] == "portal"
            )
            self.assertTrue(confirmed_item.data(ACTIVITY_ROLE)["confirmed"])
            window.activity_list.setCurrentItem(confirmed_item)
            self.assertTrue(window.confirm_activity_button.isEnabled())
            self.assertEqual(window.confirm_activity_button.text(), "Marcar completada")
            with patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ):
                window.confirm_selected_activity()
            self.assertEqual(window.activity_list.count(), 1)
            with StudyDatabase(study_database_path(study)) as database:
                expediente = database.find_expediente_by_folder(case.path)
                tasks = database.list_tasks(expediente.id)
                self.assertEqual(len(tasks), 1)
                self.assertEqual(tasks[0].status, "completada")
            window.close()

    def test_study_activity_collects_cases_and_opens_selected_expediente(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            first = create_case(study, "Alfa")
            second = create_case(study, "Beta")
            save_case_metadata(first, {"Documentación pendiente": "DNI"})
            save_case_metadata(second, {"Documentación pendiente": "Partida"})
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            entries = window.study_activity_entries()
            self.assertEqual({case.name for case, _ in entries}, {"Alfa", "Beta"})
            selected_case, selected_activity = next(entry for entry in entries if entry[0].name == "Beta")
            selected_data = {
                "case_path": str(selected_case.path),
                "target": selected_activity.target,
                "title": selected_activity.title,
                "external_id": selected_activity.external_id,
                "task_id": selected_activity.task_id,
                "file_path": selected_activity.file_path,
            }
            with patch("gestor_documental.app.StudyActivityDialog") as dialog_class:
                dialog_class.return_value.exec.return_value = 1
                dialog_class.return_value.selected_data.return_value = selected_data
                window.open_study_activity()
            self.assertEqual(window.case.path, second.path)
            self.assertEqual(window.work_tabs.currentIndex(), window.files_tab_index)
            window.close()

    def test_activity_suggests_matching_pending_file_and_opens_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            save_case_metadata(case, {"Documentación pendiente": "Recibo de sueldo"})
            document = case.path / "Documental" / "RECIBO SUELDO agosto.pdf"
            document.parent.mkdir()
            document.write_bytes(b"%PDF-1.4")
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.set_case(case)

            activity = window.activity_list.item(0)
            self.assertEqual(activity.data(ACTIVITY_ROLE)["target"], "files")
            self.assertIn("POSIBLE RECEPCIÓN", activity.text())
            window.activity_list.setCurrentItem(activity)
            self.assertEqual(window.confirm_activity_button.text(), "Marcar recibido")
            window.activity_list.setCurrentItem(activity)
            window.open_selected_activity()
            self.assertEqual(window.work_tabs.currentIndex(), window.files_tab_index)
            self.assertEqual(Path(window.case_files.currentItem().data(PATH_ROLE)), document)
            self.assertEqual(
                read_case_metadata(case)["Documentación pendiente"],
                "Recibo de sueldo",
            )
            window.work_tabs.setCurrentIndex(window.activity_tab_index)
            window.activity_list.setCurrentItem(window.activity_list.item(0))
            with patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Yes,
            ):
                window.confirm_selected_activity()
            self.assertEqual(window.activity_list.count(), 0)
            self.assertEqual(
                read_case_metadata(case)["Documentación recibida"],
                "Recibo de sueldo",
            )
            self.assertEqual(window.pending_documents_list.count(), 1)
            self.assertEqual(
                window.pending_documents_list.item(0).checkState(),
                Qt.CheckState.Checked,
            )
            window.close()

    def test_manual_task_is_created_and_completed_from_activity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            store.add_professional("Profesional")
            window = MainWindow(store)
            window.set_case(case)
            with patch.object(
                QInputDialog,
                "getText",
                side_effect=[("Llamar al cliente", True), ("18/09/2026 10:30", True)],
            ):
                window.create_manual_activity_task()
            self.assertEqual(window.activity_list.count(), 1)
            item = window.activity_list.item(0)
            self.assertEqual(item.data(ACTIVITY_ROLE)["target"], "task")
            window.activity_list.setCurrentItem(item)
            self.assertTrue(window.edit_activity_task_button.isEnabled())
            with patch.object(
                QInputDialog,
                "getText",
                side_effect=[("Llamar mañana", True), ("19/09/2026 11:00", True)],
            ):
                window.edit_manual_activity_task()
            item = window.activity_list.item(0)
            self.assertIn("Llamar mañana", item.text())
            window.activity_list.setCurrentItem(item)
            self.assertEqual(window.confirm_activity_button.text(), "Marcar completada")
            with patch.object(
                QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
            ):
                window.confirm_selected_activity()
            self.assertEqual(window.activity_list.count(), 0)
            window.show_completed_tasks.setChecked(True)
            self.assertEqual(window.activity_list.count(), 1)
            completed_item = window.activity_list.item(0)
            self.assertTrue(completed_item.data(ACTIVITY_ROLE)["completed"])
            window.activity_list.setCurrentItem(completed_item)
            self.assertFalse(window.confirm_activity_button.isEnabled())
            window.close()

    def test_selecting_case_registers_expediente_without_changing_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            case = create_case(study, "Rosales c/ Provincia")
            metadata = {"Actor": "Pablo Rosales", "CUIJ": "21-12345678-9"}
            save_case_metadata(case, metadata)
            json_before = (case.path / ".gestor-caso.json").read_bytes()
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)

            window = MainWindow(store)
            window.reload_cases(case.path)
            with StudyDatabase(study_database_path(study)) as database:
                row = database.connection.execute(
                    "SELECT title, client_name, case_number FROM expedientes"
                ).fetchone()

            self.assertEqual(tuple(row), (case.name, "Pablo Rosales", "21-12345678-9"))
            stored = read_case_metadata(case)
            self.assertEqual({key: stored[key] for key in metadata}, metadata)
            self.assertIn("Identificación interna del expediente", stored)
            self.assertNotEqual((case.path / ".gestor-caso.json").read_bytes(), json_before)
            window.close()

    def test_selected_case_shows_its_integrated_novedades(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            with StudyDatabase(study_database_path(study)) as database:
                expediente = database.import_case(case)
                database.add_movement(
                    expediente.id,
                    "Se fija audiencia para el 15/09/2026 a las 09:30",
                    source="sisfe",
                    external_id="mov-1",
                )
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)

            self.assertEqual(window.novedades_list.count(), 1)
            self.assertIn("Se fija audiencia", window.novedades_list.item(0).text())
            self.assertNotIn("DETECCIÓN", window.novedades_list.item(0).text())
            self.assertEqual(window.novedades_count.text(), "1 novedad")
            self.assertGreaterEqual(window.novedades_list.minimumHeight(), 200)
            self.assertEqual(
                window.work_tabs.tabText(window.portal_tab_index),
                "Expediente · 1",
            )
            window.novedades_list.setCurrentRow(0)
            self.app.processEvents()
            self.assertIsNotNone(window.selected_novedad_data())
            window.close()

    def test_expediente_timeline_groups_dates_and_hides_internal_classification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            save_case_metadata(case, {"Ubicación actual SISFE": "TRÁMITE INTERNO"})
            with StudyDatabase(study_database_path(study)) as database:
                expediente = database.import_case(case)
                database.add_movement(
                    expediente.id,
                    "Contestación de demanda",
                    occurred_at=datetime(2026, 9, 22, 18, 45),
                    source="sisfe",
                    external_id="timeline-1",
                    movement_kind="parte",
                    document_available=True,
                    observation="Contesta demanda y ofrece prueba",
                    presenter="SIJAM S.A.",
                    cargo_number="12345678",
                )
                database.add_movement(
                    expediente.id,
                    "Decreto",
                    occurred_at=datetime(2026, 9, 22, 9, 30),
                    source="sisfe",
                    external_id="timeline-2",
                    movement_kind="judicial",
                )
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)

            texts = [window.novedades_list.item(index).text() for index in range(2)]
            combined = "\n".join(texts)
            self.assertEqual(combined.count("22 SEP 2026"), 1)
            self.assertNotIn("18:45", combined)
            self.assertNotIn("09:30", combined)
            self.assertNotIn("ESCRITO DE PARTE", combined)
            self.assertNotIn("ACTUACIÓN JUDICIAL", combined)
            self.assertIn("Contesta demanda y ofrece prueba", combined)
            self.assertIn("SIJAM S.A.", combined)
            self.assertIn("CARGO 12345678", combined)
            self.assertEqual(window.portal_case_status.text(), "UBICACIÓN ACTUAL · TRÁMITE INTERNO")

            party_item = next(
                window.novedades_list.item(index)
                for index in range(2)
                if "Contestación" in window.novedades_list.item(index).text()
            )
            judicial_item = next(
                window.novedades_list.item(index)
                for index in range(2)
                if "Decreto" in window.novedades_list.item(index).text()
            )
            self.assertEqual(
                party_item.icon().cacheKey(), ui_icon("party-filing", "#C9493C").cacheKey()
            )
            self.assertEqual(
                judicial_item.icon().cacheKey(), ui_icon("judicial", "#768681").cacheKey()
            )
            self.assertFalse(hasattr(window, "task_pause_button"))
            self.assertEqual(window.task_stop_button.toolTip(), "Detener sincronización")
            window.show()
            self.app.processEvents()
            self.assertLess(window.sync_all_button.x(), window.sisfe_indicator.x())
            window.close()

    def test_layout_can_collapse_restore_and_persist_per_computer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            store.add_professional("Profesional")
            window = MainWindow(store)
            window.show()
            self.app.processEvents()
            window.body_splitter.setSizes([225, 1225])
            window.workspace_splitter.setSizes([1000, 300])
            window.presentation_column.setSizes([500, 260])
            window.set_compilation_panel_visible(False)
            window.save_layout_state()

            self.assertTrue(window.presentation_column.isHidden())
            self.assertFalse(store.settings.layout_state["compilation_visible"])
            self.assertEqual(len(store.settings.layout_state["body"]), 2)
            self.assertEqual(
                store.settings.layout_state["sidebar_by_professional"][
                    store.settings.current_professional
                ],
                window.body_splitter.sizes()[0],
            )
            window.close()

            reopened_store = SettingsStore(root / "appdata")
            reopened = MainWindow(reopened_store)
            self.assertTrue(reopened.presentation_column.isHidden())
            reopened.toggle_compilation_panel()
            self.assertFalse(reopened.presentation_column.isHidden())
            reopened.reset_layout()
            self.assertFalse(reopened.presentation_column.isHidden())
            self.assertTrue(reopened_store.settings.layout_state["compilation_visible"])
            reopened.close()

    def test_portal_tab_shows_more_than_the_previous_twenty_movement_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            with StudyDatabase(study_database_path(study)) as database:
                expediente = database.import_case(case)
                for index in range(25):
                    database.add_movement(
                        expediente.id,
                        f"Movimiento {index + 1}",
                        source="sisfe",
                        external_id=f"mov-{index + 1}",
                    )
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)

            self.assertEqual(window.novedades_list.count(), 25)
            self.assertEqual(window.work_tabs.tabText(window.portal_tab_index), "Expediente · 25")
            window.close()

    def test_pending_documents_have_an_operational_case_tab(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            save_case_metadata(
                case,
                {"Documentación pendiente": "DNI del cliente\nRecibo de sueldo"},
            )
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)

            self.assertEqual(window.pending_documents_list.count(), 2)
            self.assertEqual(window.pending_tab_index, -1)
            with patch(
                "gestor_documental.app.QInputDialog.getText",
                return_value=("Partida de nacimiento", True),
            ):
                window.add_pending_document()
            self.assertEqual(window.pending_documents_list.count(), 3)
            self.assertIn(
                "Partida de nacimiento",
                read_case_metadata(case)["Documentación pendiente"],
            )

            window.pending_documents_list.setCurrentRow(1)
            with patch(
                "gestor_documental.app.QInputDialog.getText",
                return_value=("18/09/2026", True),
            ):
                window.set_pending_document_due_date()
            self.assertIn(
                "2026-09-18T00:00:00",
                read_case_metadata(case)["Fechas de documentación pendiente"],
            )
            self.assertIn(
                "recordatorio para el 18/09/2026",
                window.pending_documents_list.item(1).toolTip(),
            )

            window.pending_documents_list.setCurrentRow(0)
            window.complete_pending_documents()
            self.assertIn(
                "DNI del cliente",
                read_case_metadata(case)["Documentación pendiente"],
            )
            self.assertIn(
                "DNI del cliente",
                read_case_metadata(case)["Documentación recibida"],
            )
            self.assertEqual(window.pending_documents_list.count(), 3)
            self.assertEqual(window.pending_documents_list.item(0).checkState(), Qt.CheckState.Checked)

            window.pending_documents_list.setCurrentRow(2)
            window.move_pending_document(-1)
            self.assertEqual(window.pending_documents_list.item(1).text(), "Partida de nacimiento")
            window.pending_documents_list.setCurrentRow(1)
            with patch(
                "gestor_documental.app.QInputDialog.getText",
                return_value=("Partida actualizada", True),
            ):
                window.rename_pending_document()
            self.assertIn("Partida actualizada", read_case_metadata(case)["Documentación pendiente"])
            window.pending_documents_list.setCurrentRow(1)
            with patch(
                "gestor_documental.app.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ):
                window.delete_pending_documents()
            self.assertNotIn("Partida actualizada", read_case_metadata(case)["Documentación pendiente"])
            window.close()

    def test_manual_sisfe_session_is_confirmed_without_storing_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            store.add_professional("Profesional")
            store.set_sisfe_profile("Profesional", "Rosario", "Abogados", "12345", "clave")
            window = MainWindow(store)
            window.reload_cases(case.path)
            with patch("gestor_documental.app.SisfeLoginDialog") as dialog_class:
                dialog = dialog_class.return_value

                def confirm_session():
                    window.sisfe_session.mark_portal_opened()
                    window.sisfe_session.confirm_manual_login()
                    return 1

                dialog.exec.side_effect = confirm_session
                window.open_sisfe_session()

            self.assertTrue(window.sisfe_session.active)
            self.assertEqual(window.sisfe_status.text(), "SISFE conectado")
            self.assertEqual(window.sisfe_status.state, OperationState.SUCCESS)
            self.assertNotIn("password", vars(window.sisfe_session))
            dialog_class.assert_called_once_with(
                window.sisfe_session,
                window,
                credentials={
                    "circumscription": "Rosario", "college": "Abogados",
                    "license": "12345", "password": "clave",
                },
                profile_dir=store.app_dir / "SISFE" / "BrowserProfile",
            )
            window.close()

    def test_official_sisfe_download_receives_the_selected_movement_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)
            window._sisfe_login_dialog = MagicMock()
            detail = {
                "movement_id": "mov-20",
                "title": "Decreto",
                "page_number": 2,
                "row_number": 3,
                "has_primary_document": True,
            }

            with patch("gestor_documental.app.SisfeCaseBrowserDialog") as dialog_class:
                dialog = dialog_class.return_value
                window.open_sisfe_case(
                    "exp-7",
                    movement_detail=detail,
                    auto_download=True,
                )

            dialog_class.assert_called_once_with(
                window._sisfe_login_dialog.profile,
                "exp-7",
                case,
                window,
                movement_detail=detail,
                auto_download=True,
            )
            dialog.documentSaved.connect.assert_called_once_with(window.sisfe_document_saved)
            dialog.show.assert_called_once()
            window.close()

    def test_downloaded_sisfe_pdf_continues_directly_to_cedula_when_requested(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            pdf = case.path / "Documentos SISFE" / "cedula.pdf"
            pdf.parent.mkdir()
            pdf.write_bytes(b"%PDF-1.4 test")
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)
            context = window.capture_sisfe_context()
            window._sisfe_download_request = (
                "remote-1",
                {
                    "movement_id": "mov-10",
                    "_gestor_context": context,
                    "_generate_cedula": True,
                },
            )
            second = create_case(study, "Otro caso")
            window.set_case(second)

            with patch.object(window, "generate_cedula_from_pdf") as generate:
                window.sisfe_document_saved(str(pdf), False)
                self.app.processEvents()

            self.assertEqual(generate.call_args.args, (pdf,))
            self.assertEqual(generate.call_args.kwargs["context"]["case"], case)
            self.assertEqual(generate.call_args.kwargs["context"]["professional"], context["professional"])
            self.assertNotIn("_generate_cedula", window._sisfe_download_request[1])
            window.close()

    def test_sisfe_sync_keeps_original_case_after_navigation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = create_case(root / "Estudio", "Primero")
            second = create_case(root / "Estudio", "Segundo")
            save_case_metadata(first, {"CUIJ": "21-12345678-9"})
            store = SettingsStore(root / "appdata")
            store.set_study_root(first.path.parent)
            window = MainWindow(store)
            window.set_case(first)
            window.sisfe_session.mark_portal_opened()
            window.sisfe_session.confirm_manual_login()
            window._sisfe_login_dialog = MagicMock()
            window.sync_sisfe()
            callback = window._sisfe_login_dialog.request_snapshot.call_args.args[1]
            window.set_case(second)
            snapshot = object()
            with patch.object(window.sisfe_portal, "import_snapshot") as importer:
                callback(snapshot, None)
                importer.assert_called_once_with(first, snapshot, first.path / "Documentos SISFE")
            self.assertEqual(window.case, second)
            window.close()

    def test_download_queue_keeps_each_case_and_continues_after_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = create_case(root / "Estudio", "Primero")
            second = create_case(root / "Estudio", "Segundo")
            store = SettingsStore(root / "appdata")
            store.set_study_root(first.path.parent)
            window = MainWindow(store)
            window.set_case(first)
            window._sisfe_login_dialog = MagicMock()
            with patch("gestor_documental.app.SisfeCaseBrowserDialog") as factory:
                window.start_sisfe_download("remote-1", {"movement_id": "mov-1"})
                window.set_case(second)
                window.start_sisfe_download("remote-2", {"movement_id": "mov-2"})
                self.assertEqual(factory.call_count, 1)
                self.assertEqual(len(window._sisfe_download_queue), 1)
                queued = window.sisfe_download_key(second, "mov-2")
                self.assertEqual(window._sisfe_download_states[queued][0], "queued")
                event = MagicMock()
                window.closeEvent(event)
                event.ignore.assert_called_once()

                window.sisfe_download_finished(True, "Primera lista")
                self.app.processEvents()
                self.assertEqual(factory.call_count, 2)
                self.assertTrue(window._sisfe_download_active)
                self.assertEqual(window._sisfe_download_request[0], "remote-2")
                self.assertEqual(
                    window._sisfe_download_request[1]["_gestor_context"]["case"], second
                )

                window.sisfe_download_finished(False, "SISFE no respondió")
                self.assertFalse(window._sisfe_download_active)
                self.assertEqual(window._sisfe_download_states[queued][0], "failed")
                self.assertFalse(window.sisfe_retry_button.isHidden())
                window.retry_sisfe_download()
                self.assertEqual(factory.call_count, 3)
                self.assertEqual(factory.call_args.args[2], second)
                self.assertEqual(window._sisfe_download_request[0], "remote-2")
                window.sisfe_download_finished(True, "Listo")
            window.close()

    def test_ui_rename_keeps_compilation_and_portal_document_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = create_case(root / "Estudio", "Caso")
            source = case.path / "decreto.pdf"
            source.write_bytes(b"document")
            store = SettingsStore(root / "appdata")
            store.set_study_root(case.path.parent)
            window = MainWindow(store)
            window.set_case(case)
            with StudyDatabase(study_database_path(case.path.parent)) as database:
                expediente = database.import_case(case)
                movement = database.add_movement(expediente.id, "Decreto", source="sisfe", external_id="rename-1")
                document = database.add_document(expediente.id, Path(source.name), category="judicial")
                database.link_document_to_movement(movement.id, document.id)
            window.reload_case_files(source)
            window.add_compilation_path(source)
            with patch("gestor_documental.app.QInputDialog.getText", return_value=("Renombrado", True)):
                window.rename_selected_file()
            target = case.path / "Renombrado.pdf"
            self.assertEqual(window.compilation_paths(), [target])
            self.assertEqual(window.movement_local_documents("rename-1", "sisfe"), [target])
            window.close()

    def test_recovery_worker_keeps_original_case_after_navigation(self):
        from threading import Event
        from gestor_documental.case_documents import RecoveryResult

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = create_case(root / "Estudio", "Primero")
            second = create_case(root / "Estudio", "Segundo")
            store = SettingsStore(root / "appdata")
            store.set_study_root(first.path.parent)
            window = MainWindow(store)
            window.set_case(first)
            release = Event()

            def recover(case):
                release.wait(5)
                self.assertEqual(case, first)
                return RecoveryResult(((first.path / "old.pdf", first.path / "new.pdf"),), 0)

            with patch("gestor_documental.ui.document_recovery.recover_document_links", side_effect=recover), patch.object(QMessageBox, "information"), patch.object(window, "replace_path_everywhere") as replace:
                window.recover_case_document_links()
                event = MagicMock()
                window.closeEvent(event)
                event.ignore.assert_called_once()
                window.set_case(second)
                release.set()
                for _ in range(300):
                    self.app.processEvents()
                    if window._recovery_thread is None:
                        break
                    QTest.qWait(10)
                self.assertIsNone(window._recovery_thread)
                replace.assert_not_called()
                self.assertEqual(window.case, second)
            window.close()

    def test_closing_waits_for_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(SettingsStore(Path(directory)))
            window._cedula_thread = MagicMock()
            event = MagicMock()
            window.closeEvent(event)
            event.ignore.assert_called_once()
            window._cedula_thread = None
            window.close()

    def test_professional_selector_starts_with_add_action_and_keeps_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)

            with patch("gestor_documental.app.ProfessionalProfileDialog") as dialog_class:
                dialog = dialog_class.return_value
                dialog.exec.return_value = True
                dialog.values.return_value = {
                    "name": "Dra. Ana Pérez",
                    "dni": "30111222",
                    "license_santa_fe": "L 123 F 45",
                }
                window.add_professional()

            self.assertEqual(window.professional_combo.itemText(0), "Dra. Ana Pérez")
            self.assertEqual(window.professional_combo.itemText(1), ADD_PROFESSIONAL_LABEL)
            self.assertEqual(window.professional_combo.currentText(), "Dra. Ana Pérez")
            self.assertEqual(store.settings.current_professional, "Dra. Ana Pérez")
            self.assertEqual(
                store.settings.professional_profiles["Dra. Ana Pérez"]["dni"],
                "30111222",
            )
            self.assertEqual(
                window.professional_template_values()["PROFESIONAL_MATRICULA_SANTA_FE"],
                "L 123 F 45",
            )
            self.assertGreaterEqual(len(window.professional_settings_button.menu().actions()), 4)
            window.close()

    def test_metadata_is_read_only_until_explicit_edit_and_save(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            case = create_case(study, "Daños y perjuicios")
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)
            window.show()
            self.app.processEvents()

            self.assertTrue(window.metadata_edits["Actor"].isReadOnly())
            window.begin_metadata_edit()
            self.assertFalse(window.metadata_edits["Actor"].isReadOnly())
            window.metadata_edits["Actor"].setText("Juan Pérez")
            window.metadata_edits["Actor"].setFocus()
            QTest.keyClick(window.metadata_edits["Actor"], Qt.Key.Key_Tab)
            self.app.processEvents()

            cause = window.metadata_edits["Causa"]
            cause.setText("DAÑOS Y PERJUICIOS")
            cause.setFocus()
            QTest.keyClick(cause, Qt.Key.Key_Tab)
            self.app.processEvents()

            self.assertTrue(window.isVisible())
            before_save = read_case_metadata(case)
            self.assertNotIn("Actor", before_save)
            self.assertNotIn("Causa", before_save)
            self.assertIn("Identificación interna del expediente", before_save)
            window.commit_metadata()
            self.assertEqual(read_case_metadata(case)["Causa"], "DAÑOS Y PERJUICIOS")
            self.assertTrue(window.metadata_edits["Actor"].isReadOnly())
            window.close()

    def test_basic_edit_preserves_extended_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            case = create_case(study, "Caso")
            save_case_metadata(
                case,
                {
                    "Jurisdicción": "Santa Fe",
                    "Campo propio": "Valor",
                    "Expediente SRT": "12345/26",
                },
            )
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)

            window.begin_metadata_edit()
            window.metadata_edits["Actor"].setText("Ana Pérez")
            self.assertTrue(window.commit_metadata())

            metadata = read_case_metadata(case)
            self.assertEqual(metadata["Actor"], "Ana Pérez")
            self.assertEqual(metadata["Jurisdicción"], "Santa Fe")
            self.assertEqual(metadata["Campo propio"], "Valor")
            self.assertEqual(metadata["Expediente SRT"], "12345/26")
            self.assertIn("2", window.more_metadata_button.text())
            window.close()

    def test_extended_metadata_and_model_picker_are_modern_single_step_dialogs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "Apelación.docx"
            second = root / "Cédula LABVC.docx"
            first.touch()
            second.touch()

            metadata_dialog = ExtendedMetadataDialog({"Jurisdicción": "Santa Fe"})
            self.assertEqual(metadata_dialog.tabs.count(), 4)
            self.assertEqual(metadata_dialog.tabs.tabText(0), "Datos generales")
            self.assertIn("Datos del caso", metadata_dialog.tabs.tabText(1))
            self.assertEqual(metadata_dialog.tabs.tabText(2), "Datos procesales")
            self.assertIn("RAEO", metadata_dialog.tabs.tabText(3))
            metadata_dialog.add_custom_row("Mediador", "María López")
            values = metadata_dialog.values()
            self.assertEqual(values["Jurisdicción"], "Santa Fe")
            self.assertEqual(values["Mediador"], "María López")
            self.assertIn("Identificación interna del expediente", values)
            requested = []
            metadata_dialog.documentRequested.connect(
                lambda action, payload: requested.append((action, payload))
            )
            metadata_dialog.interview_document_buttons["ficha"].click()
            self.assertEqual(requested[0][0], "ficha")
            self.assertEqual(requested[0][1]["Jurisdicción"], "Santa Fe")
            metadata_dialog.close()

            process_dialog = ExtendedMetadataDialog(
                {
                    "Actor": "Pérez, Ana",
                    "Demandado": "Empresa SA",
                    "Causa": "Despido",
                    "CUIJ": "21-123",
                    "Domicilio demandado": "Calle anterior 10",
                }
            )
            for duplicated in ("Actor", "Demandado", "Causa", "CUIJ"):
                self.assertNotIn(duplicated, process_dialog.edits)
            self.assertIn("Pérez, Ana", process_dialog.process_summary.text())
            self.assertEqual(
                process_dialog.edits["Domicilio del demandado"].text(),
                "Calle anterior 10",
            )
            process_dialog.edits["Portal jurídico asociado"].setCurrentText("SISFE")
            process_dialog.edits["Radicación segunda instancia"].setText("Sala II")
            process_values = process_dialog.values()
            self.assertEqual(process_values["Portal jurídico asociado"], "SISFE")
            self.assertEqual(process_values["Radicación segunda instancia"], "Sala II")
            process_dialog.close()

            metadata_dialog = ExtendedMetadataDialog({"Tipo de caso": "Responsabilidad Civil"})
            self.assertIn("Responsable civil", metadata_dialog.edits)
            self.assertNotIn("Nombre del causante", metadata_dialog.edits)
            metadata_dialog.edits["Responsable civil"].setText("Aseguradora SA")
            type_combo = metadata_dialog.edits["Tipo de caso"]
            type_combo.setCurrentText("Sucesiones")
            self.app.processEvents()
            self.assertIn("Nombre del causante", metadata_dialog.edits)
            self.assertNotIn("Responsable civil", metadata_dialog.edits)
            type_combo.setCurrentText("Responsabilidad Civil")
            self.app.processEvents()
            self.assertEqual(metadata_dialog.edits["Responsable civil"].text(), "Aseguradora SA")
            metadata_dialog.edits["Nombre completo"].setText("Pérez, Ana")
            self.assertEqual(metadata_dialog.values()["Actor"], "Pérez, Ana")
            metadata_dialog.close()

            lrt_dialog = ExtendedMetadataDialog({"Tipo de caso": "Accidente laboral"})
            lrt_type_combo = lrt_dialog.edits["Tipo de caso"]
            lrt_type_combo.setCurrentText("Sucesiones")
            self.app.processEvents()
            self.assertEqual(lrt_dialog.values()["Tipo de caso"], "Sucesiones")
            self.assertIn("Clave fiscal (ARCA)", lrt_dialog.edits)
            self.assertIn("Clave de Seguridad Social (ANSES)", lrt_dialog.edits)
            self.assertNotIn("Estado de acceso ARCA/AFIP", lrt_dialog.edits)
            self.assertNotIn("Estado de acceso ANSES", lrt_dialog.edits)
            lrt_dialog.edits["Clave fiscal (ARCA)"].setText("clave copiable")
            self.assertEqual(lrt_dialog.values()["Clave fiscal (ARCA)"], "clave copiable")
            lrt_dialog.close()

            picker = ModelPickerDialog([first, second])
            self.assertEqual(picker.list.count(), 2)
            picker.search.setText("cédula")
            self.assertEqual(picker.list.count(), 1)
            self.assertEqual(picker.selected_model, second)
            self.assertEqual(picker.title, "Cédula LABVC")
            picker.clear_selection()
            self.assertEqual(picker.search.text(), "")
            self.assertIsNone(picker.selected_model)
            self.assertEqual(picker.title, "")
            picker.close()

            third = root / "Poder sucesorio.docx"
            catalog = [first, second]
            dynamic_picker = ModelPickerDialog(
                catalog,
                model_provider=lambda: list(catalog),
            )
            third.touch()
            catalog.append(third)
            dynamic_picker.refresh_models(third)
            self.assertEqual(dynamic_picker.list.count(), 3)
            self.assertEqual(dynamic_picker.selected_model, third)
            dynamic_picker.close()

            heir_picker = HeirPickerDialog(
                [["Ana Pérez", "1", "20-1", "Calle 1", "Hija"], ["Juan Pérez", "2", "20-2", "Calle 2", "Hijo"]]
            )
            heir_picker.list.item(0).setSelected(True)
            heir_picker.list.item(1).setSelected(True)
            self.assertEqual(len(heir_picker.selected_rows), 2)
            self.assertEqual(heir_picker.selected_rows[1][0], "Juan Pérez")
            heir_picker.close()

    def test_new_case_immediately_becomes_the_active_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            with patch(
                "gestor_documental.app.QInputDialog.getText",
                return_value=("Caso nuevo", True),
            ):
                window.new_case_in_root(study)
            self.assertIsNotNone(window.case)
            self.assertEqual(window.case.path, study / "Caso nuevo")
            self.assertEqual(window.case_directory, study / "Caso nuevo")
            self.assertEqual(
                Path(window.case_tree.currentItem().data(0, PATH_ROLE)),
                study / "Caso nuevo",
            )
            window.close()

    def test_imported_cases_appear_in_case_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            outcome = import_rows(study, [ImportRow(2, "Maccey, Sandra")])[0]
            window.reload_cases(outcome.case.path)
            current = window.case_tree.currentItem()
            self.assertIsNotNone(current)
            self.assertEqual(Path(current.data(0, PATH_ROLE)), outcome.case.path)
            window.close()

    def test_case_files_can_be_copied_cut_pasted_and_refresh_from_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            source = root / "documento.txt"
            source.write_text("original", encoding="utf-8")
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)

            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(source))])
            QApplication.clipboard().setMimeData(mime)
            window.paste_case_files()
            copied = case.path / source.name
            self.assertTrue(copied.is_file())

            destination = case.path / "Subcarpeta"
            destination.mkdir()
            window.case_directory = destination
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(copied))])
            QApplication.clipboard().setMimeData(mime)
            window._cut_paths = [copied.resolve()]
            window.paste_case_files()
            self.assertFalse(copied.exists())
            self.assertTrue((destination / source.name).is_file())

            external_change = destination / "pegado desde afuera.txt"
            external_change.write_text("nuevo", encoding="utf-8")
            QTest.qWait(650)
            self.app.processEvents()
            names = {
                Path(window.case_files.item(index).data(PATH_ROLE)).name
                for index in range(window.case_files.count())
            }
            self.assertIn(external_change.name, names)
            window.close()

    def test_case_folder_icon_is_the_traffic_light_without_separate_dots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            recent = create_case(study, "Caso al dia")
            stale = create_case(study, "Caso atrasado")
            (recent.path / "nota.txt").write_text("hoy", encoding="utf-8")
            old_file = stale.path / "nota.txt"
            old_file.write_text("viejo", encoding="utf-8")
            old = time.time() - 400 * 24 * 3600
            os.utime(old_file, (old, old))
            os.utime(stale.path, (old, old))
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            self.app.processEvents()

            location = window.case_tree.topLevelItem(0)
            items = [location.child(index) for index in range(location.childCount())]
            by_name = {item.text(0): item for item in items}
            # El nombre del caso no lleva ningún punto ni círculo de estado:
            # el color vive en el propio ícono de carpeta.
            self.assertEqual(set(by_name), {"Caso al dia", "Caso atrasado"})
            self.assertNotEqual(
                by_name["Caso al dia"].icon(0).cacheKey(),
                by_name["Caso atrasado"].icon(0).cacheKey(),
            )
            self.assertNotIn("●", by_name["Caso atrasado"].text(0))
            window.close()

    def test_case_header_shows_caption_five_fields_and_explicit_case_data_action(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Carpeta interna")
            save_case_metadata(
                case,
                {
                    "Actor": "Juarez, Maria Jose",
                    "Demandado": "Prevención ART S.A.",
                    "Causa": "Accidente de trabajo",
                    "CUIJ": "21-27299634-9",
                    "Radicación": "Juzgado Laboral de Villa Constitución",
                },
            )
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)

            self.assertIn("JUAREZ, MARIA JOSE", window.case_title.text())
            self.assertIn("PREVENCIÓN ART S.A.", window.case_title.text())
            # La ruta física no compite con la información jurídica.
            self.assertNotIn(str(case.path), window.case_title.text())
            self.assertEqual(window.more_metadata_button.text().split(" ·")[0], "Datos del caso")
            self.assertTrue(window.metadata_edits["Actor"].isReadOnly())
            window.begin_metadata_edit()
            self.assertFalse(window.metadata_edits["Actor"].isReadOnly())
            # TAB recorre los cinco campos en su orden natural de lectura.
            edits = list(window.metadata_edits.values())
            widget = window.metadata_edits["Actor"]
            for _ in range(12):
                widget = widget.nextInFocusChain()
                if widget in edits:
                    break
            self.assertIs(widget, window.metadata_edits["Demandado"])
            self.assertIsNotNone(window.metadata_edits["Radicación"].completer())
            window.cancel_metadata_edit()
            window.close()

    def test_files_tab_sorts_by_column_header_and_filters_without_touching_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            small = case.path / "alfa.txt"
            big = case.path / "zeta.txt"
            small.write_text("a", encoding="utf-8")
            big.write_text("b" * 500, encoding="utf-8")
            before = {path.name: path.read_bytes() for path in (small, big)}
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)

            window.sort_case_files_by("size")
            self.assertEqual(window.files_sort_combo.currentData(), "size_desc")
            self.assertEqual(
                [
                    Path(window.case_files.item(index).data(PATH_ROLE)).name
                    for index in range(window.case_files.count())
                ],
                ["zeta.txt", "alfa.txt"],
            )
            window.sort_case_files_by("size")
            self.assertEqual(window.files_sort_combo.currentData(), "size_asc")

            window.files_search.setText("zeta")
            self.app.processEvents()
            self.assertEqual(
                [
                    Path(window.case_files.item(index).data(PATH_ROLE)).name
                    for index in range(window.case_files.count())
                ],
                ["zeta.txt"],
            )
            self.assertEqual({path.name: path.read_bytes() for path in (small, big)}, before)
            window.close()

    def test_presentation_limit_can_be_cleared_and_is_remembered_per_professional(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            store.add_professional("Profesional")
            window = MainWindow(store)

            window.choose_presentation_limit(20 * 1024 * 1024)
            self.assertEqual(window.selected_presentation_limit(), 20 * 1024 * 1024)
            self.assertTrue(window.limit_buttons[20 * 1024 * 1024].isChecked())
            window.choose_presentation_limit(20 * 1024 * 1024)
            self.assertEqual(window.selected_presentation_limit(), 0)
            self.assertIn("natural", window.limit_hint.text().casefold())
            window.choose_presentation_limit(1 * 1024 * 1024)
            window.close()

            reopened = MainWindow(SettingsStore(root / "appdata"))
            self.assertEqual(reopened.selected_presentation_limit(), 1 * 1024 * 1024)
            reopened.close()

    def test_status_bar_reports_sisfe_validation_and_expediente_synchronisation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)

            self.assertEqual(window.sisfe_status.state, OperationState.IDLE)
            self.assertIn("sin confirmar", window.sisfe_indicator.toolTip().casefold())
            self.assertEqual(window.sync_all_button.text(), "Sincronizar todos")
            self.assertEqual(
                window.sync_all_button.toolTip(), "Sincronizar todos los expedientes"
            )
            self.assertEqual(window.sisfe_sync_button.text(), "")
            self.assertEqual(window.sisfe_sync_button.toolTip(), "Sincronizar expediente")
            self.assertFalse(hasattr(window, "novedad_detail_button"))
            self.assertEqual(window.case_sync_label.text(), "Expediente sin sincronizar")
            window.update_sisfe_indicator(OperationState.SUCCESS, "Sesión SISFE validada")
            self.assertEqual(window.sisfe_status.state, OperationState.SUCCESS)
            self.assertIn("validada", window.sisfe_indicator.toolTip())
            window.update_case_sync_label("Sincronizando…")
            self.assertEqual(window.case_sync_label.text(), "Sincronizando…")
            window.close()

    def test_unseen_sisfe_badge_persists_until_expediente_is_viewed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)
            window.work_tabs.setCurrentIndex(window.files_tab_index)

            window.record_unseen_sisfe(case, 4)
            self.assertEqual(read_case_metadata(case)["Novedades SISFE sin ver"], "4")
            window.work_tabs.setCurrentIndex(window.portal_tab_index)
            self.app.processEvents()
            self.assertNotIn("Novedades SISFE sin ver", read_case_metadata(case))
            window.close()

    def test_mass_sync_is_sequential_and_continues_after_individual_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            first = create_case(study, "Primero")
            second = create_case(study, "Segundo")
            save_case_metadata(first, {"CUIJ": "21-1"})
            save_case_metadata(second, {"CUIJ": "21-2"})
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.sisfe_session.mark_portal_opened()
            window.sisfe_session.confirm_manual_login()
            portal = MagicMock()
            portal.ready_for_sync = True
            window._sisfe_login_dialog = portal
            result = SimpleNamespace(movements_registered=2, documents_registered=1)

            with (
                patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes),
                patch.object(window.sisfe_portal, "import_snapshot", return_value=result),
                patch("gestor_documental.app.SisfeCaseBrowserDialog") as case_browser,
            ):
                window.sync_all_expedientes()
                task = window._long_task
                portal.prepare_background_sync.assert_called_once_with()
                self.assertFalse(window.status_activity.isHidden())
                self.assertEqual(portal.request_snapshot.call_count, 1)
                callback = portal.request_snapshot.call_args.args[1]
                callback(object(), None)
                for _ in range(200):
                    self.app.processEvents()
                    if portal.request_snapshot.call_count == 2:
                        break
                    QTest.qWait(5)
                self.assertEqual(portal.request_snapshot.call_count, 2)
                portal.request_snapshot.call_args.args[1](None, RuntimeError("no encontrado"))
                self.app.processEvents()
                self.app.processEvents()
                case_browser.assert_not_called()
                self.assertFalse(hasattr(window, "task_pause_button"))

            self.assertEqual(task.state, TaskState.COMPLETED)
            self.assertEqual(task.current, 2)
            self.assertEqual([detail.result for detail in task.details], ["ok", "error"])
            self.assertEqual(read_case_metadata(first)["Novedades SISFE sin ver"], "2")
            window.close()

    def test_only_one_long_task_and_close_requests_safe_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            task = LongTask("Importando casos", 2)
            window.begin_long_task(task, "import")
            task.start()

            with patch.object(QMessageBox, "information") as information:
                window.import_cases_from_spreadsheet()
                information.assert_called_once()
                self.assertIn("proceso en curso", information.call_args.args[2].casefold())

            event = MagicMock()
            with patch.object(window, "confirm_stop_long_task_and_exit", return_value=True):
                window.closeEvent(event)
            event.ignore.assert_called_once()
            self.assertEqual(task.state, TaskState.CANCELLING)
            self.assertTrue(window._close_after_long_task)
            task.cancelled()
            self.app.processEvents()

    def test_mass_import_runs_in_background_without_per_case_dialogs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            row = ImportRow(2, "Caso en segundo plano")
            started = Event()
            release = Event()

            def slow_import(_root, rows, **_kwargs):
                started.set()
                release.wait(2)
                return [ImportOutcome(rows[0], case=create_case(study, rows[0].actor))]

            with (
                patch("gestor_documental.app.CaseSpreadsheetImportDialog") as dialog_class,
                patch("gestor_documental.app.import_rows", side_effect=slow_import),
                patch.object(QMessageBox, "exec") as popup_exec,
            ):
                dialog = dialog_class.return_value
                dialog.exec.return_value = QDialog.DialogCode.Accepted
                dialog.rows = [row]
                window.import_cases_from_spreadsheet()
                self.assertTrue(started.wait(1))
                self.assertTrue(window.long_task_active())
                self.assertTrue(window.isEnabled())
                popup_exec.assert_not_called()
                release.set()
                for _ in range(200):
                    self.app.processEvents()
                    if window._long_task is None and window._long_task_thread is None:
                        break
                    QTest.qWait(5)

            self.assertIsNone(window._long_task)
            self.assertIsNone(window._long_task_thread)
            self.assertTrue((study / "Caso en segundo plano").is_dir())
            window.close()

    def test_case_badges_use_each_case_metadata_and_can_all_be_marked_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            first = create_case(study, "Primero")
            second = create_case(study, "Segundo")
            save_case_metadata(first, {"Novedades SISFE sin ver": "120"})
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            counts = []

            def capture(name, color, count, size=24):
                counts.append(count)
                from gestor_documental.icons import ui_icon
                return ui_icon(name, color, size)

            with patch("gestor_documental.app.badged_icon", side_effect=capture):
                window = MainWindow(store)
            self.assertEqual(sorted(counts), [0, 120])
            window.mark_all_sisfe_news_read()
            self.assertNotIn("Novedades SISFE sin ver", read_case_metadata(first))
            self.assertNotIn("Novedades SISFE sin ver", read_case_metadata(second))
            window.close()

    def test_sisfe_movement_shows_its_existing_local_document_without_copying_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            local_pdf = case.path / "Documento SISFE.pdf"
            local_pdf.write_bytes(b"%PDF-1.4 local")
            with StudyDatabase(study_database_path(study)) as database:
                expediente = database.import_case(case)
                database.add_movement(
                    expediente.id, "Cédula electrónica", source="sisfe", external_id="mov-local"
                )
            SisfeDownloadRegistry().register(case, local_pdf, movement_external_id="mov-local")
            before = local_pdf.read_bytes()
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)

            data = window.novedades_list.item(0).data(MOVEMENT_ROLE)
            self.assertIn("PDF disponible localmente", window.novedades_list.item(0).text())
            self.assertEqual(data["local_documents"], [str(local_pdf.resolve())])
            self.assertEqual(local_pdf.read_bytes(), before)
            window.close()

    def test_portal_shows_queued_and_failed_download_states_per_movement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            with StudyDatabase(study_database_path(study)) as database:
                expediente = database.import_case(case)
                database.add_movement(
                    expediente.id,
                    "Resolución para descargar",
                    source="sisfe",
                    external_id="mov-state",
                )
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)
            key = window.sisfe_download_key(case, "mov-state")

            window._sisfe_download_states[key] = ("queued", "En espera · posición 1")
            window.reload_novedades()
            queued_item = window.novedades_list.item(0)
            self.assertIn("EN COLA", queued_item.text())
            self.assertEqual(queued_item.data(MOVEMENT_ROLE)["download_state"], "queued")

            window._sisfe_download_states[key] = ("failed", "SISFE no respondió")
            window.reload_novedades()
            failed_item = window.novedades_list.item(0)
            self.assertIn("ERROR", failed_item.text())
            self.assertIn("SISFE no respondió", failed_item.toolTip())
            self.assertFalse(any(case.path.glob("Documentos SISFE/*")))
            window.close()

    def test_case_files_can_be_ordered_visually_without_changing_the_case(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            older = case.path / "zeta.txt"
            newer = case.path / "alfa.txt"
            older.write_text("conservar", encoding="utf-8")
            newer.write_text("conservar", encoding="utf-8")
            os.utime(older, (100, 100))
            os.utime(newer, (200, 200))
            before = {path.name: path.read_bytes() for path in (older, newer)}
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)

            window.files_sort_combo.setCurrentIndex(
                window.files_sort_combo.findData("modified_desc")
            )
            displayed = [
                Path(window.case_files.item(index).data(PATH_ROLE)).name
                for index in range(window.case_files.count())
            ]

            self.assertEqual(displayed, ["alfa.txt", "zeta.txt"])
            self.assertEqual({path.name: path.read_bytes() for path in (older, newer)}, before)
            self.assertEqual(store.settings.layout_state["files_sort"], "modified_desc")
            window.close()

    def test_extended_metadata_keeps_repeated_rows_and_reuses_case_data_for_raeo(self):
        dialog = ExtendedMetadataDialog(
            {
                "Actor": "Pérez, Juan",
                "Demandado": "Empresa SA",
                "Causa": "Accidente laboral",
                "CUIJ": "21-123",
                "Posibles testigos": "Ana | 341 111\nLuis | 341 222",
            },
            case_name="Pérez c/ Empresa",
            professional="Dra. Ana López",
        )
        self.assertEqual(len(dialog.repeated["Posibles testigos"].rows), 2)
        values = dialog.values()
        self.assertEqual(values["Actor"], "Pérez, Juan")
        self.assertEqual(values["CUIJ"], "21-123")
        self.assertEqual(
            values["Posibles testigos"],
            "Ana | 341 111\nLuis | 341 222",
        )
        self.assertIn("PÉREZ, JUAN C/ EMPRESA SA", dialog.system_summary.text())
        self.assertEqual(values["Profesional creador"], "Dra. Ana López")
        dialog.close()

    def test_multiple_study_locations_appear_as_roots_and_search_together(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root / "Estudio local"
            shared = root / "Google Drive compartido"
            local.mkdir()
            shared.mkdir()
            local_case = create_case(local, "Pérez c/ Local")
            shared_case = create_case(shared, "Gómez c/ Compartida")
            store = SettingsStore(root / "appdata")
            store.add_study_root(local)
            store.add_study_root(shared)
            window = MainWindow(store)
            self.app.processEvents()

            self.assertEqual(window.case_tree.topLevelItemCount(), 2)
            roots = {
                window.case_tree.topLevelItem(i).text(0): window.case_tree.topLevelItem(i)
                for i in range(window.case_tree.topLevelItemCount())
            }
            self.assertEqual(roots[local.name].childCount(), 1)
            self.assertEqual(roots[shared.name].childCount(), 1)
            self.assertFalse(roots[local.name].icon(0).isNull())
            self.assertFalse(roots[shared.name].icon(0).isNull())

            local_item = roots[local.name].child(0)
            window.case_tree.setCurrentItem(local_item)
            self.app.processEvents()
            self.assertEqual(window.case.path, local_case.path)
            self.assertEqual(store.settings.study_root, local)
            self.assertIn(local.name.upper(), window.quick_label.text())

            window.search.setText("Gómez")
            self.app.processEvents()
            self.assertEqual(window.case_tree.topLevelItem(0).childCount(), 0)
            self.assertEqual(window.case_tree.topLevelItem(1).childCount(), 1)
            self.assertEqual(
                Path(window.case_tree.topLevelItem(1).child(0).data(0, PATH_ROLE)),
                shared_case.path,
            )
            window.close()

    def test_same_client_with_multiple_cases_is_grouped_visually_without_moving_folders(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            first = create_case(study, "Pérez c/ ART")
            second = create_case(study, "Pérez c/ Empleador")
            save_case_metadata(first, {"Actor": "PÉREZ, JUAN", "DNI del actor": "30123456"})
            save_case_metadata(second, {"Actor": "Pérez, Juan", "DNI del actor": "30.123.456"})
            paths_before = {first.path, second.path}
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(first.path)

            root_item = window.case_tree.topLevelItem(0)
            client_item = root_item.child(0)
            self.assertIn("2 casos", client_item.text(0))
            self.assertEqual(client_item.childCount(), 2)
            self.assertEqual(
                {Path(client_item.child(index).data(0, PATH_ROLE)) for index in range(2)},
                paths_before,
            )
            self.assertFalse(window.client_cases_button.isHidden())
            self.assertEqual(window.client_cases_button.text(), "2 casos del cliente")
            self.assertEqual(len(window.client_cases_for_current_case()), 2)
            self.assertEqual({first.path, second.path}, paths_before)

            other_item = next(
                client_item.child(index)
                for index in range(client_item.childCount())
                if Path(client_item.child(index).data(0, PATH_ROLE)) == second.path
            )
            window.case_tree.blockSignals(True)
            window.case_tree.setCurrentItem(other_item)
            window.case_tree.blockSignals(False)
            window.restore_case_tree_selection()
            self.assertEqual(
                Path(window.case_tree.currentItem().data(0, PATH_ROLE)),
                first.path,
            )
            window.close()

    def test_missing_personal_fields_are_prefilled_from_the_shared_client(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            first = create_case(study, "Pérez c ART")
            second = create_case(study, "Pérez c empleador")
            save_case_metadata(
                first,
                {
                    "Actor": "Juan Pérez",
                    "DNI del actor": "30111222",
                    "Teléfono del actor": "3415550101",
                    "Correo electrónico del actor": "juan@example.com",
                },
            )
            save_case_metadata(
                second,
                {"Actor": "Juan Pérez", "DNI del actor": "30111222"},
            )
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.set_case(first)
            window.set_case(second)

            defaults = window.with_shared_client_defaults(read_case_metadata(second))

            self.assertEqual(defaults["Teléfono del actor"], "3415550101")
            self.assertEqual(defaults["Correo electrónico del actor"], "juan@example.com")
            self.assertNotIn("Teléfono del actor", read_case_metadata(second))
            window.close()

    def test_import_dialog_leaves_pdf_conversion_unselected_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "documento.docx"
            source.touch()
            dialog = ImportFileDialog(source)
            self.assertFalse(dialog.convert_to_pdf)
            dialog.convert.setChecked(True)
            dialog.close()
            self.assertTrue(dialog.convert_to_pdf)

    def test_image_import_options_only_appear_when_conversion_is_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "foto.png"
            source.touch()
            dialog = ImportFileDialog(source)
            self.assertFalse(dialog.image_mode.isVisible())
            dialog.show()
            dialog.convert.setChecked(True)
            self.app.processEvents()
            self.assertTrue(dialog.image_mode.isVisible())
            dialog.image_mode.setCurrentIndex(2)
            self.assertEqual(dialog.selected_image_mode, "black_white")
            dialog.close()

    def test_compilation_order_can_move_and_delete_with_keyboard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            case = create_case(study, "Caso")
            first = case.path / "primero.pdf"
            second = case.path / "escrito.pdf"
            first.touch()
            second.touch()
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)
            window.add_compilation_path(first)
            window.add_compilation_path(second, "writing")

            window.compilation.setCurrentRow(1)
            window.move_compilation_item(-1)
            self.assertEqual(Path(window.compilation.item(0).data(PATH_ROLE)), second)
            QTest.keyClick(window.compilation, Qt.Key.Key_Delete)
            self.assertEqual(window.compilation.count(), 1)
            window.close()

    def test_nested_user_folder_is_visible_and_its_files_can_be_compiled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            case = create_case(study, "Caso")
            folder = case.path / "Informes"
            folder.mkdir()
            pdf = folder / "Informe.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=595, height=842)
            with pdf.open("wb") as stream:
                writer.write(stream)
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)

            paths = [Path(window.case_files.item(i).data(PATH_ROLE)) for i in range(window.case_files.count())]
            self.assertIn(folder, paths)
            self.assertNotIn(pdf, paths)
            folder_item = next(
                window.case_files.item(i)
                for i in range(window.case_files.count())
                if Path(window.case_files.item(i).data(PATH_ROLE)) == folder
            )
            self.assertFalse(folder_item.icon().isNull())
            window.case_files.setCurrentItem(folder_item)
            window.open_selected_file()
            self.assertEqual(window.case_directory, folder)
            self.assertEqual(window.files_location.text(), "Informes")
            self.assertEqual(window.case_files.count(), 1)
            self.assertEqual(
                Path(window.case_files.item(0).data(PATH_ROLE)),
                pdf,
            )
            self.assertFalse(window.case_files.item(0).icon().isNull())
            window.set_document_category(pdf, "judicial")
            self.assertIn("JUDICIAL", window.case_files.item(0).text())
            window.go_up_case_folder()
            self.assertEqual(window.case_directory, case.path)

            folder_item = next(
                window.case_files.item(i)
                for i in range(window.case_files.count())
                if Path(window.case_files.item(i).data(PATH_ROLE)) == folder
            )
            folder_item.setSelected(True)
            window.add_selected_to_compilation()
            self.assertEqual(window.compilation.count(), 1)
            self.assertEqual(Path(window.compilation.item(0).data(PATH_ROLE)), pdf)
            self.assertEqual(window.work_tabs.currentIndex(), window.files_tab_index)
            self.assertIn("1 elemento · 1 página PDF", window.compilation_count.text())
            window.close()

    def test_compilation_draft_survives_case_switch_and_window_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            first_case = create_case(study, "Caso uno")
            second_case = create_case(study, "Caso dos")
            documentary = first_case.path / "documental.pdf"
            writing = first_case.path / "escrito.docx"
            other = second_case.path / "otro.pdf"
            documentary.touch()
            writing.touch()
            other.touch()
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)

            window = MainWindow(store)
            window.set_case(first_case)
            window.add_compilation_path(documentary)
            window.set_current_writing(writing)
            special_profile = "SISFE demanda/contestación · 6 MB"
            window.limit_combo.setCurrentIndex(window.limit_combo.findText(special_profile))
            window.set_case(second_case)
            self.assertEqual(window.compilation.count(), 0)
            window.add_compilation_path(other)
            window.set_case(first_case)

            self.assertEqual(window.compilation.count(), 2)
            self.assertEqual(
                [Path(window.compilation.item(index).data(PATH_ROLE)) for index in range(2)],
                [documentary, writing],
            )
            self.assertEqual(window.current_writing, writing)
            self.assertEqual(window.limit_combo.currentText(), special_profile)
            window.close()

            reopened = MainWindow(store)
            reopened.set_case(first_case)
            self.assertEqual(reopened.compilation.count(), 2)
            self.assertEqual(reopened.current_writing, writing)
            self.assertEqual(reopened.limit_combo.currentText(), special_profile)
            reopened.close()

    def test_renaming_case_preserves_portable_compilation_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            case = create_case(study, "Nombre anterior")
            pdf = case.path / "documental.pdf"
            pdf.touch()
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.set_case(case)
            window.add_compilation_path(pdf)

            with patch(
                "gestor_documental.app.QInputDialog.getText",
                return_value=("Nombre nuevo", True),
            ):
                window.rename_case_folder(case)

            renamed_pdf = study / "Nombre nuevo" / pdf.name
            self.assertEqual(window.case.path, study / "Nombre nuevo")
            self.assertEqual(Path(window.compilation.item(0).data(PATH_ROLE)), renamed_pdf)
            window.close()

            reopened = MainWindow(store)
            reopened.set_case(create_case(study, "Caso temporal"))
            reopened.set_case(type(case)(study / "Nombre nuevo"))
            self.assertEqual(Path(reopened.compilation.item(0).data(PATH_ROLE)), renamed_pdf)
            reopened.close()

    def test_primary_sign_button_uses_selected_or_last_compiled_pdf(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            case = create_case(study, "Caso")
            pdf = case.path / "presentación.pdf"
            pdf.touch()
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.set_case(case)
            window.last_compiled = pdf

            with patch.object(window, "sign_with_token") as sign:
                window.sign_current_pdf()

            sign.assert_called_once_with(pdf)
            self.assertEqual(window.sign_options_button.accessibleName(), "Otras opciones de firma")
            window.close()

    def test_external_signer_output_is_recovered_into_the_case(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            output_dir = root / "Firmados"
            output_dir.mkdir()
            source = case.path / "PEREZ_DEMANDA.pdf"
            signed = output_dir / "PEREZ_DEMANDA_firmado.pdf"
            for path in (source, signed):
                writer = PdfWriter()
                writer.add_blank_page(width=595, height=842)
                with path.open("wb") as stream:
                    writer.write(stream)
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            store.set_signer_output_dir(output_dir)
            window = MainWindow(store)
            window.set_case(case)
            window._external_sign_source = source
            window._external_sign_started_at = time.time() - 1

            with patch("gestor_documental.app.QMessageBox.information"):
                window.check_external_signer_output()
                window.check_external_signer_output()

            recovered = case.path / signed.name
            self.assertTrue(recovered.is_file())
            self.assertEqual(window.last_signed, recovered)
            window.close()

    def test_close_cancels_background_compilation_and_then_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            case = create_case(study, "Caso")
            source = case.path / "documental.pdf"
            source.touch()
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)
            window.add_compilation_path(source)
            window.show()

            def waits_for_cancel(*args, **kwargs):
                cancelled = kwargs.get("cancelled") or args[5]
                while not cancelled():
                    time.sleep(0.005)
                raise CompilationCancelled()

            with (
                patch("gestor_documental.background_workers.compile_documents", side_effect=waits_for_cancel),
                patch.object(
                    window,
                    "prompt_compilation_name",
                    return_value=("Compilado.pdf", False),
                ),
                patch.object(
                    QMessageBox,
                    "question",
                    return_value=QMessageBox.StandardButton.Yes,
                ),
            ):
                window.compile_pdf()
                self.app.processEvents()
                window.close()
                for _ in range(250):
                    self.app.processEvents()
                    if window._compile_thread is None and not window.isVisible():
                        break
                    QTest.qWait(5)

            self.assertIsNone(window._compile_thread)
            self.assertFalse(window.isVisible())

    def test_compile_runs_in_background_and_finishes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            case = create_case(study, "Caso")
            source = case.path / "documental.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=595, height=842)
            with source.open("wb") as stream:
                writer.write(stream)
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)
            window.add_compilation_path(source)

            with (
                patch.object(
                    window,
                    "prompt_compilation_name",
                    return_value=("Compilado.pdf", False),
                ),
                patch.object(
                    QMessageBox,
                    "information",
                    return_value=QMessageBox.StandardButton.Ok,
                ),
            ):
                window.compile_pdf()
                for _ in range(250):
                    self.app.processEvents()
                    if window._compile_thread is None:
                        break
                    QTest.qWait(10)

            self.assertIsNone(window._compile_thread)
            self.assertIsNotNone(window.last_compiled)
            self.assertTrue(window.last_compiled.is_file())
            self.assertTrue(source.is_file())
            self.assertEqual(window.compilation.count(), 0)
            self.assertIsNone(window.current_writing)
            self.assertEqual(window.compilation_count.text(), "0 elementos")
            history = load_compilation_history(case)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0].items[0].path, source)
            saved_result = window.last_compiled
            window.close()

            reopened = MainWindow(store)
            reopened.reload_cases(case.path)
            self.assertEqual(reopened.compilation.count(), 0)
            self.assertIsNone(reopened.current_writing)
            self.assertEqual(reopened.last_compiled, saved_result)
            reopened.close()


if __name__ == "__main__":
    unittest.main()

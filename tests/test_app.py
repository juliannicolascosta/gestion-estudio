import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QMimeData, Qt, QUrl
from PyQt6.QtGui import QPalette
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton
from pypdf import PdfWriter

from gestor_documental.app import (
    ADD_PROFESSIONAL_LABEL,
    ExtendedMetadataDialog,
    ImportFileDialog,
    MainWindow,
    ModelPickerDialog,
    PATH_ROLE,
)
from gestor_documental.services import (
    CompilationCancelled,
    SettingsStore,
    create_case,
    read_case_metadata,
    save_case_metadata,
    study_library_path,
)
from gestor_documental.study_database import StudyDatabase, study_database_path
from gestor_documental.ui.operation_status import OperationState


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
            self.assertEqual(window.windowTitle(), "Gestor de documental")
            self.assertEqual(window.limit_combo.count(), 4)
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
                store.settings.current_professional,
            )
            self.assertFalse(window.professional_settings_button.icon().isNull())
            self.assertEqual(window.work_tabs.count(), 3)
            self.assertEqual(window.work_tabs.tabText(window.files_tab_index), "Archivos")
            self.assertEqual(
                window.work_tabs.tabText(window.portal_tab_index),
                "Portal · 0",
            )
            self.assertEqual(
                window.work_tabs.tabText(window.pending_tab_index),
                "Pendientes · 0",
            )
            self.assertIs(window.compilation_card.parentWidget(), window.presentation_column)
            self.assertIs(window.presentation_column.parentWidget(), window.workspace_splitter)
            self.assertIs(window.workspace_splitter.widget(0), window.information_column)
            self.assertEqual(window.presentation_column.minimumWidth(), 240)
            self.assertLess(window._visible_workspace_sizes[1], 350)
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
            self.assertFalse(window.quick_access.isHidden())
            window.toggle_quick_access()
            self.assertTrue(window.quick_access.isHidden())
            window.toggle_quick_access()
            self.assertFalse(window.quick_access.isHidden())
            window.toggle_directory_expanded()
            self.assertTrue(window.quick_label.isHidden())
            self.assertTrue(window.quick_access.isHidden())
            window.toggle_directory_expanded()
            self.assertFalse(window.quick_label.isHidden())
            self.assertFalse(window.quick_access.isHidden())
            self.assertTrue(study_library_path(study).is_dir())
            window.reload_cases(case.path)
            self.assertEqual(window.case_title.text(), case.name)
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
            self.assertEqual((case.path / ".gestor-caso.json").read_bytes(), json_before)
            window.close()

    def test_selected_case_shows_its_integrated_novedades(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            with StudyDatabase(study_database_path(study)) as database:
                expediente = database.import_case(case)
                database.add_movement(
                    expediente.id, "Cédula electrónica", source="sisfe", external_id="mov-1"
                )
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.reload_cases(case.path)

            self.assertEqual(window.novedades_list.count(), 1)
            self.assertIn("Cédula electrónica", window.novedades_list.item(0).text())
            self.assertEqual(window.novedades_count.text(), "1 novedad")
            self.assertGreaterEqual(window.novedades_list.minimumHeight(), 220)
            self.assertEqual(
                window.work_tabs.tabText(window.portal_tab_index),
                "Portal · 1",
            )
            self.assertFalse(window.novedad_detail_button.isEnabled())
            window.novedades_list.setCurrentRow(0)
            self.app.processEvents()
            self.assertTrue(window.novedad_detail_button.isEnabled())
            window.close()

    def test_layout_can_collapse_restore_and_persist_per_computer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)
            window.show()
            self.app.processEvents()
            window.body_splitter.setSizes([225, 1225])
            window.workspace_splitter.setSizes([1000, 300])
            window.information_column.setSizes([175, 700])
            window.presentation_column.setSizes([500, 260])
            window.set_compilation_panel_visible(False)
            window.save_layout_state()

            self.assertTrue(window.presentation_column.isHidden())
            self.assertFalse(store.settings.layout_state["compilation_visible"])
            self.assertEqual(len(store.settings.layout_state["body"]), 2)
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
            self.assertEqual(window.work_tabs.tabText(window.portal_tab_index), "Portal · 25")
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
            self.assertEqual(
                window.work_tabs.tabText(window.pending_tab_index),
                "Pendientes · 2",
            )
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
            self.assertEqual(window.work_tabs.tabText(window.pending_tab_index), "Pendientes · 2")
            window.close()

    def test_manual_sisfe_session_is_confirmed_without_storing_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            case = create_case(study, "Caso")
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
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
            self.assertIn("preparando", window.sisfe_status.text().lower())
            self.assertEqual(window.sisfe_status.state, OperationState.RUNNING)
            self.assertNotIn("password", vars(window.sisfe_session))
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

    def test_professional_selector_starts_with_add_action_and_keeps_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study = root / "Estudio"
            study.mkdir()
            store = SettingsStore(root / "appdata")
            store.set_study_root(study)
            window = MainWindow(store)

            with patch(
                "gestor_documental.app.QInputDialog.getText",
                return_value=("Dra. Ana Pérez", True),
            ):
                window.professional_combo.setCurrentIndex(0)

            self.assertEqual(window.professional_combo.itemText(0), ADD_PROFESSIONAL_LABEL)
            self.assertEqual(window.professional_combo.currentText(), "Dra. Ana Pérez")
            self.assertEqual(store.settings.current_professional, "Dra. Ana Pérez")
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
            self.assertEqual(read_case_metadata(case), {})
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
            self.assertEqual(metadata_dialog.tabs.count(), 3)
            self.assertEqual(metadata_dialog.tabs.tabText(0), "Datos generales")
            self.assertEqual(metadata_dialog.tabs.tabText(1), "Entrevista inicial")
            self.assertIn("RAEO", metadata_dialog.tabs.tabText(2))
            metadata_dialog.add_custom_row("Mediador", "María López")
            values = metadata_dialog.values()
            self.assertEqual(values["Jurisdicción"], "Santa Fe")
            self.assertEqual(values["Mediador"], "María López")
            self.assertIn("Identificación interna del expediente", values)
            metadata_dialog.close()

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
            self.assertEqual(window.compilation_count.text(), "1 elemento")
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
                patch("gestor_documental.app.compile_documents", side_effect=waits_for_cancel),
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
            window.close()


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton
from pypdf import PdfWriter

from gestor_documental.app import (
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
            self.assertIn("lista", window.sisfe_status.text().lower())
            self.assertNotIn("password", vars(window.sisfe_session))
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
            save_case_metadata(case, {"Jurisdicción": "Santa Fe", "Campo propio": "Valor"})
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
            picker.close()

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

    def test_import_dialog_keeps_pdf_conversion_selected_after_close(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "documento.docx"
            source.touch()
            dialog = ImportFileDialog(source)
            dialog.convert.setChecked(True)
            dialog.close()
            self.assertTrue(dialog.convert_to_pdf)

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

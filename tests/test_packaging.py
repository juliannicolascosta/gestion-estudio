import re
import unittest
from pathlib import Path

import gestor_documental


ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_installer_uses_the_application_version_as_single_source(self):
        build = (ROOT / "packaging" / "build_installer.ps1").read_text(encoding="utf-8-sig")
        install = (ROOT / "packaging" / "install.ps1").read_text(encoding="utf-8-sig")
        bootstrapper = (ROOT / "packaging" / "installer_bootstrapper.cs").read_text(encoding="utf-8-sig")
        self.assertIn("gestor_documental\\__init__.py", build)
        self.assertIn('@@VERSION@@', install)
        self.assertIn('@@VERSION@@', bootstrapper)
        self.assertIn('@@ASSEMBLY_VERSION@@', bootstrapper)
        self.assertNotRegex(bootstrapper, r"Gestor de documental 0\.\d+")
        self.assertIn("InstallDestinationForm", bootstrapper)
        self.assertIn("FolderBrowserDialog", bootstrapper)
        self.assertIn("ProgressBar", bootstrapper)
        self.assertIn("Preparando archivos", bootstrapper)
        self.assertIn("Instalando FORO", bootstrapper)
        self.assertNotIn("instalarÃ", bootstrapper)
        self.assertRegex(gestor_documental.__version__, r"^\d+\.\d+\.\d+$")
        self.assertFalse((ROOT / "gestor_documental" / "version_info.txt").exists())

    def test_portable_build_is_self_contained_and_shares_the_version(self):
        portable = (ROOT / "packaging" / "build_portable.ps1").read_text(encoding="utf-8-sig")
        launcher = (ROOT / "packaging" / "portable_launcher.cs").read_text(encoding="utf-8-sig")
        smoke = (ROOT / "packaging" / "smoke_portable.py").read_text(encoding="utf-8")
        self.assertIn("gestor_documental\\__init__.py", portable)
        self.assertIn("FORO.exe", portable)
        self.assertIn("foro.ico", portable)
        self.assertIn("smoke_portable.py", portable)
        # El portable no instala ni deja rastros fuera de su carpeta.
        self.assertNotIn("Registry", portable)
        self.assertNotIn("StartMenu", portable)
        self.assertIn('EnvironmentVariables["FORO_DATA_DIR"]', launcher)
        self.assertIn('@@ASSEMBLY_VERSION@@', launcher)
        self.assertIn('window.windowTitle() == "FORO"', smoke)

    def test_installer_does_not_delete_application_data(self):
        install = (ROOT / "packaging" / "install.ps1").read_text(encoding="utf-8-sig")
        uninstall = (ROOT / "packaging" / "uninstall.ps1").read_text(encoding="utf-8-sig")
        for script in (install, uninstall):
            self.assertNotIn('GestorDocumental" -Recurse', script)
            self.assertNotRegex(script, re.compile(r"APPDATA.*Remove-Item", re.IGNORECASE))

    def test_update_is_staged_and_keeps_a_rollback_copy(self):
        install = (ROOT / "packaging" / "install.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("$StagingDir", install)
        self.assertIn("$BackupDir", install)
        self.assertIn("Move-WithRetry $InstallDir $BackupDir", install)
        self.assertIn("Move-WithRetry $StagingDir $InstallDir", install)

    def test_installer_validates_shortcuts_before_finishing(self):
        install = (ROOT / "packaging" / "install.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("$created = $shell.CreateShortcut($ShortcutPath)", install)
        self.assertIn("[string]::IsNullOrWhiteSpace($created.TargetPath)", install)
        self.assertIn("No se pudo crear correctamente el acceso directo", install)


if __name__ == "__main__":
    unittest.main()

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
        self.assertRegex(gestor_documental.__version__, r"^\d+\.\d+\.\d+$")

    def test_installer_does_not_delete_application_data(self):
        install = (ROOT / "packaging" / "install.ps1").read_text(encoding="utf-8-sig")
        uninstall = (ROOT / "packaging" / "uninstall.ps1").read_text(encoding="utf-8-sig")
        for script in (install, uninstall):
            self.assertNotIn('GestorDocumental" -Recurse', script)
            self.assertNotRegex(script, re.compile(r"APPDATA.*Remove-Item", re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()

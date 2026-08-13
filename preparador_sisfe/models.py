from dataclasses import dataclass
from pathlib import Path

COMMON_LIMIT = 3 * 1024 * 1024
SPECIAL_LIMIT = 6 * 1024 * 1024
SPECIAL_TYPES = {"Demanda", "Contestación"}

@dataclass(frozen=True)
class Case:
    name: str
    path: Path

    @property
    def writings(self) -> Path:
        return self.path / "01 Escritos"

    @property
    def evidence(self) -> Path:
        return self.path / "02 Documental"

    @property
    def output(self) -> Path:
        return self.path / "PARA PRESENTAR"

    def ensure(self):
        for folder in (self.writings, self.evidence, self.output):
            folder.mkdir(parents=True, exist_ok=True)


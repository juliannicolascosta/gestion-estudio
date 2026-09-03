import tempfile
import unittest
from datetime import date
from pathlib import Path

from gestor_documental.case_data import (
    build_case_caption,
    case_suggestions,
    computed_values,
    ensure_system_metadata,
    person_name_parts,
    person_name_variants,
    process_sections,
    raeo_effective_values,
    raeo_missing_fields,
)
from gestor_documental.services import create_case, read_case_metadata, save_case_metadata


class CaseDataTests(unittest.TestCase):
    def test_process_fields_reuse_identity_and_cover_both_parties(self):
        keys = {
            field.key
            for section in process_sections()
            for field in section.fields
        }
        self.assertFalse({"Actor", "Demandado", "Causa", "CUIJ"} & keys)
        self.assertTrue(
            {
                "Portal jurídico asociado",
                "Radicación",
                "Radicación segunda instancia",
                "Domicilio legal",
                "Domicilio electrónico",
                "Domicilio del demandado",
                "Abogado de la contraparte",
                "Domicilio procesal de la contraparte",
                "Domicilio electrónico de la contraparte",
            }.issubset(keys)
        )

    def test_one_name_entry_supports_comma_and_natural_order(self):
        self.assertEqual(
            person_name_parts("PÉREZ, JUAN CARLOS"),
            ("PÉREZ", "JUAN CARLOS"),
        )
        self.assertEqual(
            person_name_parts("Juan Carlos Pérez"),
            ("Pérez", "Juan Carlos"),
        )
        variants = person_name_variants("Juan Carlos Pérez")
        self.assertEqual(variants["Nombre y apellido"], "Juan Carlos Pérez")
        self.assertEqual(variants["Apellido y nombres"], "Pérez, Juan Carlos")

    def test_system_data_and_caption_are_derived_without_duplicate_fields(self):
        source = {
            "Apellido del actor": "Pérez",
            "Nombres del actor": "Juan Carlos",
            "Demandado": "Empresa SA",
            "Causa": "Despido",
            "CUIJ": "21-12345678-9",
        }
        first = ensure_system_metadata(
            source,
            professional="Dra. Ana López",
            today=date(2026, 8, 21),
        )
        second = ensure_system_metadata(
            first,
            professional="Otro profesional",
            today=date(2026, 8, 22),
        )

        self.assertEqual(first["Actor"], "Pérez, Juan Carlos")
        self.assertEqual(first["Nombre y apellido"], "Juan Carlos Pérez")
        self.assertEqual(first["Apellido del actor"], "Pérez")
        self.assertEqual(first["Nombres del actor"], "Juan Carlos")
        self.assertEqual(first["Nombre completo"], "Pérez, Juan Carlos")
        self.assertEqual(
            build_case_caption(first),
            "PÉREZ, JUAN CARLOS C/ EMPRESA SA S/ DESPIDO",
        )
        self.assertEqual(first["Identificación interna del expediente"], second["Identificación interna del expediente"])
        self.assertEqual(first["Fecha de creación del registro"], "2026-08-21")
        self.assertEqual(second["Profesional creador"], "Dra. Ana López")
        self.assertNotIn("Carátula", first)

    def test_calculations_cover_age_seniority_dates_and_remuneration(self):
        values = computed_values(
            {
                "Fecha de nacimiento": "22/08/1990",
                "Fecha de ingreso": "15/01/2020",
                "Fecha del accidente": "21/08/2026",
                "Fecha de denuncia ante ART": "25/08/2026",
                "Fecha de alta médica": "30/08/2026",
                "Fecha de reingreso laboral": "02/09/2026",
                "Remuneración percibida": "10.000,00",
                "Periodicidad de la remuneración": "Diaria",
                "Remuneración conforme CCT": "300.000,00",
            },
            today=date(2026, 8, 21),
        )

        self.assertEqual(values["EDAD_RAEO"], "35")
        self.assertEqual(values["ANTIGUEDAD_LABORAL"], "6 años y 7 meses")
        self.assertEqual(values["DIAS_ACCIDENTE_DENUNCIA_ART"], "4")
        self.assertEqual(values["DIAS_ACCIDENTE_ALTA_MEDICA"], "9")
        self.assertEqual(values["DIAS_ALTA_REINGRESO"], "3")
        self.assertEqual(values["REMUNERACION_MENSUAL_ESTIMADA"], "250.000,00")
        self.assertEqual(values["DIFERENCIA_REMUNERACION_CONVENIO"], "50.000,00")

    def test_raeo_reuses_case_and_interview_data(self):
        metadata = {
            "Actor": "Pérez, Juan",
            "DNI del actor": "12345678",
            "Domicilio real": "Calle 1",
            "Localidad del actor": "Rosario",
            "Puesto o categoría real": "Operario",
            "Fecha de ingreso": "01/02/2020",
            "Fecha del accidente": "01/02/2026",
            "Localidad de ocurrencia": "Rosario",
            "Relato del accidente": "Cayó durante la jornada",
            "Lesiones denunciadas": "Fractura",
            "Empleador principal": "Empresa SA",
            "Demandado": "Empresa SA",
            "Causa": "Accidente laboral",
            "CUIJ": "21-1",
            "Juzgado o tribunal": "Juzgado Laboral 1",
            "Localidad del juzgado": "Rosario",
            "Fecha de inicio de la causa": "10/03/2026",
        }
        effective = raeo_effective_values(metadata)
        missing = raeo_missing_fields(metadata)

        self.assertEqual(effective["Circunstancias"], "Cayó durante la jornada")
        self.assertEqual(effective["Responsable principal"], "Empresa SA")
        self.assertEqual(effective["CUIJ"], "21-1")
        self.assertNotIn("Carátula", missing)
        self.assertIn("Monto reclamado", missing)

    def test_suggestions_cover_lrt_registration_and_medical_data(self):
        suggestions = case_suggestions(
            {
                "Tipo de proceso": "Accidente laboral",
                "ART": "Aseguradora",
                "Modalidad de registración": "Defectuosa",
                "Responsables solidarios": "Empresa B | Rosario",
                "Lesiones denunciadas": "Lesión lumbar",
            }
        )
        joined = " ".join(suggestions).casefold()
        self.assertIn("raeo", joined)
        self.assertIn("contrato srt", joined)
        self.assertIn("registración", joined)
        self.assertIn("solidarios", joined)
        self.assertIn("incapacidad", joined)

    def test_repeated_metadata_preserves_one_record_per_line(self):
        with tempfile.TemporaryDirectory() as directory:
            study = Path(directory)
            case = create_case(study, "Caso")
            save_case_metadata(
                case,
                {
                    "Posibles testigos": "Ana Pérez | 341 111\nLuis Gómez | 341 222",
                    "Actor": "Juan Pérez",
                },
            )
            saved = read_case_metadata(case)
            self.assertEqual(
                saved["Posibles testigos"],
                "Ana Pérez | 341 111\nLuis Gómez | 341 222",
            )


if __name__ == "__main__":
    unittest.main()

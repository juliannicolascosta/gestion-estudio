import datetime as dt
import tempfile
import unittest
from pathlib import Path

from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import signers
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko_certvalidator import ValidationContext
from pypdf import PdfWriter

from gestor_documental.signing import (
    DigitalSignatureSession,
    SigningCertificate,
    VisibleSignature,
    select_current_certificates,
    signed_output_path,
    visible_signature_box,
)


class FakeTokenSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def make_software_signer(directory: Path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = dt.datetime.now(dt.timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Firma temporal de prueba")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=5))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    key_path = directory / "key.pem"
    certificate_path = directory / "certificate.pem"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return signers.SimpleSigner.load(key_path, certificate_path), certificate


class SigningTests(unittest.TestCase):
    def test_signed_output_uses_clear_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "PEREZ_2026-08-21_DEMANDA.pdf"
            source.touch()
            first = signed_output_path(source)
            self.assertEqual(first.name, "PEREZ_2026-08-21_DEMANDA_FIRMADO.pdf")
            first.touch()
            self.assertEqual(
                signed_output_path(source).name,
                "PEREZ_2026-08-21_DEMANDA_FIRMADO_V2.pdf",
            )

    def test_current_certificate_filter_excludes_expired(self):
        now = dt.datetime.now(dt.timezone.utc)
        common = dict(
            module_path=Path("token.dll"),
            token_label="Token",
            certificate_id=b"1",
            subject="Profesional",
            issuer="Autoridad",
            der_bytes=b"certificate",
        )
        valid = SigningCertificate(
            **common,
            valid_from=now - dt.timedelta(days=1),
            valid_until=now + dt.timedelta(days=1),
        )
        expired = SigningCertificate(
            **{**common, "certificate_id": b"2"},
            valid_from=now - dt.timedelta(days=3),
            valid_until=now - dt.timedelta(days=1),
        )
        self.assertEqual(select_current_certificates([expired, valid]), [valid])

    def test_pades_signature_is_valid_and_session_can_sign_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            signer, certificate = make_software_signer(root)
            source = root / "documento.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=595, height=842)
            with source.open("wb") as stream:
                writer.write(stream)

            token_session = FakeTokenSession()
            session = DigitalSignatureSession()
            session._session = token_session
            session._signer = signer
            first = session.sign_pdf(
                source,
                visible_signature=VisibleSignature(True, -1, "bottom_right"),
            )
            second = session.sign_pdf(first)

            with second.open("rb") as stream:
                reader = PdfFileReader(stream)
                self.assertEqual(len(reader.embedded_signatures), 2)
                rectangle = reader.embedded_signatures[0].sig_field.get("/Rect")
                self.assertEqual(len(rectangle), 4)
                self.assertGreater(float(rectangle[2]) - float(rectangle[0]), 0)
                self.assertEqual(
                    str(reader.embedded_signatures[-1].sig_object.get("/SubFilter")),
                    "/ETSI.CAdES.detached",
                )
                validation_context = ValidationContext(
                    trust_roots=[asn1_x509.Certificate.load(certificate.public_bytes(serialization.Encoding.DER))],
                    allow_fetching=False,
                    revocation_mode="soft-fail",
                )
                statuses = [
                    validate_pdf_signature(
                        embedded,
                        signer_validation_context=validation_context,
                        skip_diff=True,
                    )
                    for embedded in reader.embedded_signatures
                ]
                self.assertTrue(all(status.intact and status.valid for status in statuses))

            self.assertTrue(session.active)
            session.close()
            self.assertTrue(token_session.closed)
            self.assertFalse(session.active)

    def test_visible_signature_positions_stay_inside_the_page(self):
        for position in (
            "bottom_right", "bottom_left", "middle_right",
            "middle_left", "top_right", "top_left",
        ):
            x1, y1, x2, y2 = visible_signature_box(595, 842, position)
            self.assertGreaterEqual(x1, 0)
            self.assertGreaterEqual(y1, 0)
            self.assertLessEqual(x2, 595)
            self.assertLessEqual(y2, 842)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


class SigningUnavailable(RuntimeError):
    """Raised when the local digital-signature components are unavailable."""


class SigningError(RuntimeError):
    """Raised when a token session or PDF signature cannot be completed."""


@dataclass(frozen=True)
class SigningCertificate:
    module_path: Path
    token_label: str
    certificate_id: bytes
    subject: str
    issuer: str
    valid_from: datetime
    valid_until: datetime
    der_bytes: bytes = field(repr=False)

    def is_valid_at(self, moment: datetime | None = None) -> bool:
        moment = moment or datetime.now(timezone.utc)
        start = self.valid_from
        end = self.valid_until
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return start <= moment <= end

    @property
    def summary(self) -> str:
        return f"{self.subject} · vence {self.valid_until.strftime('%d/%m/%Y')}"


@dataclass(frozen=True)
class VisibleSignature:
    enabled: bool = False
    page: int = -1
    position: str = "bottom_right"


def visible_signature_box(
    page_width: float,
    page_height: float,
    position: str = "bottom_right",
) -> tuple[int, int, int, int]:
    width = min(190, max(120, int(page_width * 0.34)))
    height = min(72, max(48, int(page_height * 0.09)))
    margin = 24
    horizontal = "left" if position.endswith("left") else "right"
    vertical = position.removesuffix("_left").removesuffix("_right")
    x1 = margin if horizontal == "left" else int(page_width) - margin - width
    if vertical == "top":
        y1 = int(page_height) - margin - height
    elif vertical == "middle":
        y1 = (int(page_height) - height) // 2
    else:
        y1 = margin
    return x1, y1, x1 + width, y1 + height


DEFAULT_PKCS11_MODULES = (
    Path(r"C:\Windows\System32\eTPKCS11.dll"),
    Path(r"C:\Windows\SysWOW64\eTPKCS11.dll"),
)


def find_pkcs11_module(candidates: tuple[Path, ...] = DEFAULT_PKCS11_MODULES) -> Path:
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SigningUnavailable(
        "No encontramos el controlador del token de firma. Instalá o repará "
        "SafeNet Authentication Client y volvé a conectar el token."
    )


def _signing_imports():
    try:
        import pkcs11
        from cryptography import x509
        from cryptography.x509.oid import NameOID
    except ImportError as error:
        raise SigningUnavailable(
            "La función de firma digital todavía no está instalada en esta copia del Gestor. "
            "Podés seguir usando Xólido mientras se actualiza la aplicación."
        ) from error
    return pkcs11, x509, NameOID


def discover_signing_certificates(module_path: Path | None = None) -> list[SigningCertificate]:
    """Read public token certificates without logging in or requesting a PIN."""
    pkcs11, crypto_x509, name_oid = _signing_imports()
    module = Path(module_path) if module_path else find_pkcs11_module()
    try:
        library = pkcs11.lib(str(module))
        slots = library.get_slots(token_present=True)
    except Exception as error:
        raise SigningError(_friendly_pkcs11_error(error, "No pudimos consultar el token.")) from error
    result: list[SigningCertificate] = []
    for slot in slots:
        try:
            token = slot.get_token()
            session = token.open()
            try:
                objects = session.get_objects(
                    {pkcs11.Attribute.CLASS: pkcs11.ObjectClass.CERTIFICATE}
                )
                for obj in objects:
                    try:
                        der = bytes(obj[pkcs11.Attribute.VALUE])
                        cert_id = bytes(obj[pkcs11.Attribute.ID])
                        certificate = crypto_x509.load_der_x509_certificate(der)
                        names = certificate.subject.get_attributes_for_oid(name_oid.COMMON_NAME)
                        issuers = certificate.issuer.get_attributes_for_oid(name_oid.COMMON_NAME)
                        subject = names[0].value if names else certificate.subject.rfc4514_string()
                        issuer = issuers[0].value if issuers else certificate.issuer.rfc4514_string()
                        if hasattr(certificate, "not_valid_before_utc"):
                            valid_from = certificate.not_valid_before_utc
                            valid_until = certificate.not_valid_after_utc
                        else:
                            valid_from = certificate.not_valid_before.replace(tzinfo=timezone.utc)
                            valid_until = certificate.not_valid_after.replace(tzinfo=timezone.utc)
                        result.append(
                            SigningCertificate(
                                module_path=module,
                                token_label=str(token.label).strip(),
                                certificate_id=cert_id,
                                subject=subject,
                                issuer=issuer,
                                valid_from=valid_from,
                                valid_until=valid_until,
                                der_bytes=der,
                            )
                        )
                    except (KeyError, ValueError):
                        continue
            finally:
                session.close()
        except Exception:
            continue
    result.sort(
        key=lambda cert: (cert.is_valid_at(), cert.valid_until),
        reverse=True,
    )
    if not result:
        raise SigningUnavailable(
            "No encontramos certificados públicos en el token. Verificá que esté conectado "
            "y visible en SafeNet Authentication Client."
        )
    return result


def select_current_certificates(certificates: list[SigningCertificate]) -> list[SigningCertificate]:
    return [certificate for certificate in certificates if certificate.is_valid_at()]


def signed_output_path(source: Path) -> Path:
    source = Path(source)
    stem = source.stem
    if stem.upper().endswith("_FIRMADO"):
        stem = stem[: -len("_FIRMADO")]
    requested = source.with_name(f"{stem}_FIRMADO.pdf")
    if not requested.exists():
        return requested
    number = 2
    while True:
        candidate = source.with_name(f"{stem}_FIRMADO_V{number}.pdf")
        if not candidate.exists():
            return candidate
        number += 1


class DigitalSignatureSession:
    """Keep a PKCS#11 login alive only for the lifetime of this app process."""

    def __init__(self):
        self._session = None
        self._signer = None
        self._certificate: SigningCertificate | None = None

    @property
    def active(self) -> bool:
        return self._session is not None and self._signer is not None

    @property
    def certificate(self) -> SigningCertificate | None:
        return self._certificate

    def open(self, certificate: SigningCertificate, pin: str) -> None:
        if not pin:
            raise SigningError("Ingresá el PIN del token para iniciar la sesión de firma.")
        try:
            import pkcs11
            from asn1crypto import x509 as asn1_x509
            from pyhanko.sign.pkcs11 import PKCS11Signer, open_pkcs11_session
        except ImportError as error:
            raise SigningUnavailable(
                "La función de firma digital todavía no está instalada en esta copia del Gestor."
            ) from error

        self.close()
        try:
            session = open_pkcs11_session(
                str(certificate.module_path),
                token_label=certificate.token_label,
                user_pin=pin,
            )
            matching_keys = list(
                session.get_objects(
                    {
                        pkcs11.Attribute.CLASS: pkcs11.ObjectClass.PRIVATE_KEY,
                        pkcs11.Attribute.ID: certificate.certificate_id,
                    }
                )
            )
            if not matching_keys:
                session.close()
                raise SigningError(
                    "El certificado elegido no tiene una clave privada disponible en el token."
                )
            signer = PKCS11Signer(
                session,
                signing_cert=asn1_x509.Certificate.load(certificate.der_bytes),
                cert_id=certificate.certificate_id,
                key_id=certificate.certificate_id,
                bulk_fetch=False,
                embed_roots=False,
                prefer_pss=False,
            )
        except SigningError:
            raise
        except Exception as error:
            raise SigningError(
                _friendly_pkcs11_error(error, "No pudimos iniciar la sesión de firma.")
            ) from error
        self._session = session
        self._signer = signer
        self._certificate = certificate

    def sign_pdf(
        self,
        source: Path,
        output: Path | None = None,
        *,
        reason: str = "Presentación judicial",
        location: str = "Argentina",
        visible_signature: VisibleSignature | None = None,
    ) -> Path:
        if not self.active:
            raise SigningError("La sesión de firma no está iniciada.")
        source = Path(source)
        if not source.is_file() or source.suffix.casefold() != ".pdf":
            raise SigningError("Elegí un archivo PDF existente para firmar.")
        target = Path(output) if output else signed_output_path(source)
        if target.resolve() == source.resolve():
            raise SigningError("El archivo firmado debe conservarse con un nombre diferente.")
        if target.exists():
            raise FileExistsError(f"Ya existe un archivo llamado “{target.name}”.")
        temporary = target.with_name(f".{target.name}.firmando-{uuid.uuid4().hex}.tmp")
        try:
            from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
            from pyhanko.pdf_utils.reader import PdfFileReader
            from pyhanko.sign import signers
            from pyhanko.sign.fields import SigFieldSpec, SigSeedSubFilter
            from pyhanko.sign.validation import validate_pdf_signature
            from pyhanko_certvalidator import ValidationContext
            from pyhanko.stamp import TextStampStyle

            with source.open("rb") as input_stream, temporary.open("wb") as output_stream:
                writer = IncrementalPdfFileWriter(input_stream)
                field_name = f"Firma_Gestor_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
                metadata = signers.PdfSignatureMetadata(
                    field_name=field_name,
                    md_algorithm="sha256",
                    subfilter=SigSeedSubFilter.PADES,
                    reason=reason.strip() or None,
                    location=location.strip() or None,
                )
                field_spec = None
                stamp_style = None
                if visible_signature and visible_signature.enabled:
                    page_count = int(writer.root["/Pages"]["/Count"])
                    page_index = visible_signature.page if visible_signature.page >= 0 else page_count - 1
                    page_index = max(0, min(page_index, page_count - 1))
                    page_ref, _ = writer.find_page_for_modification(page_index)
                    page_object = page_ref.get_object()
                    while "/MediaBox" not in page_object:
                        page_object = page_object["/Parent"].get_object()
                    media_box = page_object["/MediaBox"]
                    page_width = float(media_box[2]) - float(media_box[0])
                    page_height = float(media_box[3]) - float(media_box[1])
                    field_spec = SigFieldSpec(
                        field_name,
                        on_page=page_index,
                        box=visible_signature_box(page_width, page_height, visible_signature.position),
                    )
                    stamp_style = TextStampStyle(
                        border_width=1,
                        stamp_text="Firmado digitalmente por\n%(signer)s\n%(ts)s",
                        timestamp_format="%d/%m/%Y %H:%M:%S",
                    )
                pdf_signer = signers.PdfSigner(
                    metadata,
                    signer=self._signer,
                    stamp_style=stamp_style,
                    new_field_spec=field_spec,
                )
                pdf_signer.sign_pdf(writer, output=output_stream)
                output_stream.flush()
                os.fsync(output_stream.fileno())

            with temporary.open("rb") as validation_stream:
                reader = PdfFileReader(validation_stream)
                if not reader.embedded_signatures:
                    raise SigningError("El PDF resultante no contiene una firma digital.")
                # This is an immediate integrity check, not a legal trust-chain
                # determination. Treat the signing certificate as the local
                # trust anchor to avoid network and Windows-store dependencies.
                validation_context = ValidationContext(
                    trust_roots=[self._signer.signing_cert],
                    allow_fetching=False,
                    revocation_mode="soft-fail",
                )
                status = validate_pdf_signature(
                    reader.embedded_signatures[-1],
                    signer_validation_context=validation_context,
                    skip_diff=True,
                )
                if not status.intact or not status.valid:
                    raise SigningError("La firma fue generada, pero no superó la validación de integridad.")
            os.replace(temporary, target)
            return target
        except SigningError:
            self.close()
            raise
        except Exception as error:
            self.close()
            raise SigningError(
                _friendly_pkcs11_error(error, "No pudimos firmar el PDF.")
            ) from error
        finally:
            if temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass

    def close(self) -> None:
        session, self._session = self._session, None
        self._signer = None
        self._certificate = None
        if session is not None:
            try:
                session.close()
            except Exception:
                pass


def _friendly_pkcs11_error(error: Exception, prefix: str) -> str:
    detail = str(error).strip()
    normalized = detail.upper()
    if "PIN_INCORRECT" in normalized or "CKR_PIN_INCORRECT" in normalized:
        return "El PIN no es correcto. La sesión de firma no se inició."
    if "PIN_LOCKED" in normalized or "CKR_PIN_LOCKED" in normalized:
        return "El PIN del token está bloqueado. No sigas intentando y revisalo con el emisor."
    if any(marker in normalized for marker in ("DEVICE_REMOVED", "TOKEN_NOT_PRESENT", "NO TOKEN")):
        return "El token fue retirado o dejó de estar disponible. Volvé a conectarlo."
    if "USER_ALREADY_LOGGED_IN" in normalized:
        return "El token ya tiene una sesión iniciada. Cerrá la sesión anterior y volvé a intentar."
    return f"{prefix}\n\nDetalle: {detail}" if detail else prefix

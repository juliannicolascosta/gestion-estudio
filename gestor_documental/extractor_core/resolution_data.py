from dataclasses import dataclass


@dataclass
class ResolutionData:
    cuij: str = ""
    barcode: str = ""
    caratula: str = ""
    por: str = ""
    contra: str = ""
    sobre: str = ""
    tribunal_detectado: str = ""
    localidad_detectada: str = ""
    fecha: str = ""
    firmantes: str = ""
    tipo_interno: str = ""
    texto: str = ""

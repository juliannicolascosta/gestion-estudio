# Delivery para SISFE — MVP para Windows

**Delivery para SISFE** es una aplicación de escritorio pequeña para trabajar por caso: crear escritos Word, reunir documental, ordenarla, convertirla a PDF y dejar una presentación controlada en `PARA PRESENTAR`.

## Qué incluye

- Crear un caso nuevo o vincular una carpeta existente.
- Estructura simple: `01 Escritos`, `02 Documental`, `PARA PRESENTAR`.
- `+ NUEVO ESCRITO`: genera un `.docx` nombrado por fecha y tipo, y lo abre en Word.
- Documental por selector o *drag & drop*, con ordenamiento en pantalla.
- Conversión de imágenes, PDF y documentos de Word/LibreOffice.
- Unificación de documental según el orden visible.
- Control de **3 MB** para escritos comunes y **6 MB** para demanda/contestación.
- Compresión automática y, si todavía excede, división por páginas.
- Apertura de `PARA PRESENTAR` para firmar con Xólido y subir manualmente a SISFE.

No incluye agenda, clientes, expedientes ni gestión jurídica. SISFE y Xólido no se automatizan: el MVP prepara y abre la carpeta final.

## Instalación rápida

Requiere Windows 10/11 y Python 3.11 o posterior. En PowerShell, dentro de esta carpeta:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python run.py
```

Para convertir `.doc`/`.docx`, debe estar instalado Microsoft Word o LibreOffice. Con Word, instale además la integración opcional:

```powershell
.venv\Scripts\python -m pip install pywin32
```

## Crear un `.exe`

```powershell
.venv\Scripts\python -m pip install pyinstaller
.venv\Scripts\pyinstaller --noconfirm --windowed --name "Preparador SISFE" run.py
```

El ejecutable queda en `dist\Preparador SISFE\Preparador SISFE.exe`. Las conversiones Word siguen requiriendo Word o LibreOffice instalado.

## Uso

1. Pulse **Crear caso** o **Vincular carpeta**.
2. Pulse **+ NUEVO ESCRITO**, elija el tipo y edítelo en Word.
3. Agregue documental y arrástrela para ordenar.
4. Seleccione el escrito y pulse **PREPARAR PARA SISFE**.
5. Revise los archivos finales, firme el escrito con Xólido y súbalos a SISFE.

## Arquitectura e integración futura

- `models.py`: contrato mínimo de caso y límites.
- `services.py`: almacenamiento, conversión y preparación; no depende de la interfaz.
- `app.py`: interfaz PyQt6.

El núcleo recibe rutas y devuelve archivos finales, de modo que el futuro Gestor Jurídico puede reutilizarlo como servicio sin incorporar esta ventana. La configuración de casos se guarda en `%APPDATA%\PreparadorSISFE\config.json`.

## Precauciones del MVP

- La compresión rasteriza el PDF: revise legibilidad y firmas antes de subir.
- Una página individual excepcionalmente pesada puede seguir excediendo el límite; la app lo advierte.
- Cada preparación reemplaza solamente los PDF que la propia aplicación registró como generados; no borra otros archivos ni modifica los originales de `01 Escritos` o `02 Documental`.

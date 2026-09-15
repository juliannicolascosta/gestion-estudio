# Hoja de ruta

## Base del nuevo flujo

- [x] Carpeta de Estudio, árbol y buscador.
- [x] Varias Ubicaciones del Estudio con búsqueda conjunta.
- [x] Carpetas locales, de red o sincronizadas por Google Drive para escritorio.
- [x] Ubicación activa y desconexión segura sin borrar casos.
- [x] Casos nuevos sin subcarpetas automáticas y reconocimiento de carpetas internas existentes.
- [x] Datos del caso.
- [x] Drag & drop de archivos hacia dentro y fuera.
- [x] Copiar, cortar y pegar archivos o carpetas con actualización automática de la vista.
- [x] Normalización y conversión al importar.
- [x] Conversión a PDF optativa y desmarcada de forma predeterminada.
- [x] Tratamiento opcional de imágenes en color, escala de grises o blanco y negro al convertirlas a PDF.
- [x] Escritos base y desde modelos.
- [x] Compilación ordenada en PDF único.
- [x] Límites, compresión y división confirmada.
- [x] Profesional seleccionable.
- [x] Integración externa configurable de firma.
- [x] Renombrado de carpetas de caso.
- [x] Modelo base externo con Español (Argentina).
- [x] Apertura y eliminación recuperable mediante teclado.
- [x] Compilación en segundo plano con progreso.
- [x] Flujo de arrastre asistido a una sesión existente de Xólido.
- [x] Biblioteca del Estudio permanentemente visible y apta para arrastre en ambas direcciones.
- [x] Conversión Word aislada, limitada y reutilizable mediante caché.
- [x] Optimización PDF sin rasterización indiscriminada.
- [x] Cancelación segura de compilaciones y cierre posterior.
- [x] Variables de caso y profesional dentro de modelos Word.
- [x] Modelo oficio provisto por el usuario como base editable.
- [x] Navegación interna por carpetas e iconos reales por tipo de archivo.
- [x] Guía y ejemplo de campos automáticos para modelos precargados.
- [x] Modelo Cedula LABVC con metadatos y fecha extensa.
- [x] Número de expediente como denominación general, conservando compatibilidad con CUIJ.
- [x] Iconografía vectorial moderna y controles secundarios compactos.
- [x] Selección de casos sin artefactos visuales nativos de Windows.
- [x] Liberación inmediata de archivos PDF después de compilar o dividir.
- [x] Nombre inteligente y editable de PDF `ACTOR_FECHA_TÍTULO`, con reemplazo o versiones `_V2`.
- [x] Metadatos protegidos, ficha ampliada y campos personalizados para modelos.
- [x] Selector buscable de modelos con título en el mismo paso.
- [x] Generación contextual de ficha inicial, pacto y poder con catálogo dinámico y ranking por tipo de caso.
- [x] Semáforo configurable del directorio con actividad real, archivado reversible y filtros de visibilidad.
- [x] Estado de trámite interno SISFE e interpretación auditable inicial de audiencias, traslados y vencimientos explícitos.
- [x] Estados visuales para Word editable, PDF para firmar y archivo firmado.
- [x] Ficha ampliada en pestañas para datos generales, entrevista inicial y RAEO.
- [x] Campos repetibles y cálculos determinísticos de edad, antigüedad, días y remuneraciones.
- [x] Validación de datos faltantes y sugerencias contextuales para casos LRT/RAEO.
- [x] Firma PAdES con token SafeNet/PKCS#11 y sesión autenticada reutilizable sin persistir el PIN.
- [x] Firma PAdES visible opcional con selección de página, posición y vista previa.
- [x] Validación inmediata de integridad y control de tamaño posterior a la firma.
- [x] Portal jurídico como contexto propio dentro del caso.
- [x] Checklist operativo de documentación pendiente compartido con la entrevista.
- [x] Sincronización incremental de la proyección SQLite al editar o renombrar casos.
- [x] Portal jurídico con lista expansible de altura completa.
- [x] Ficha cotidiana reducida a los cinco metadatos solicitados.
- [x] Directorio y biblioteca ampliables o contraíbles.
- [x] Alta de profesional desde el selector y engranaje de configuración rápida.
- [x] Perfil completo por profesional y variables Word para identidad, contacto, matrículas y banco.
- [x] Compilación permanente a la derecha, visible al mismo tiempo que los archivos del caso.
- [x] Columnas y secciones verticales redimensionables, persistentes y con Compilación contraíble.
- [x] Indicador visual común para tareas SISFE en espera, ejecución, éxito o error.
- [x] Borrador de compilación portátil y persistente por expediente.
- [x] Resumen de páginas y peso de la preparación, con limpieza de referencias internas al compilar correctamente sin tocar originales.
- [x] Clientes vinculados a múltiples casos con agrupación visual y precarga conservadora de datos personales conocidos.
- [x] Bandeja del Portal sin el recorte anterior de veinte movimientos.
- [x] Servicio único de aplicación para importar la información obtenida en el navegador SISFE.
- [x] Centro de actividad por expediente con navegación al origen y sin duplicar novedades ni pendientes.
- [x] Confirmación profesional de detecciones como tareas internas, sin agenda automática.
- [x] Finalización auditable de tareas confirmadas y retiro de la bandeja activa.
- [x] Alta y finalización de tareas manuales con fecha objetivo opcional.
- [x] Edición auditable de descripción y fecha de tareas manuales activas.
- [x] Consulta opcional de tareas completadas fuera de la bandeja activa.
- [x] Recordatorios locales visibles por vencimiento, día, próxima semana y fecha futura.
- [x] Bandeja transversal de actividad para todos los expedientes y Ubicaciones del Estudio.

## Próxima iteración

- [x] Separación suficiente de `app.py` para esta etapa: componentes y tareas en segundo plano de compilación, extracción y respaldo, paneles de archivos/acceso rápido y diálogos de configuración y SISFE extraídos sin cambiar el flujo probado.
- [x] Automatizar la acción oficial de descarga dentro del navegador SISFE y vincular cada archivo con su movimiento.
- [x] Ejecutar las descargas SISFE en una cola oculta y reflejar check, error y reintento en el Portal.
- [ ] Retirar el transporte HTTP SISFE heredado cuando existan pruebas de aceptación suficientes del flujo de navegador.
- [x] Pantalla completa de configuración: profesionales, modelos y firmador.
- [ ] Vincular carpeta externa como caso mediante copia normalizada y vista previa.
- [ ] Reglas avanzadas configurables de nomenclatura para quienes no usen el formato recomendado.
- [ ] Detección configurable de la carpeta de salida del firmador para recuperar automáticamente el PDF firmado.
- [x] Sugerir recepción cuando ingrese un archivo que coincida con documentación pendiente.
- [x] Confirmar la recepción sugerida desde Actividad manteniendo el historial del checklist.
- [x] Fecha objetivo opcional para cada documento pendiente, integrada con Actividad.
- [ ] Recordatorios confirmados por el profesional para documentación todavía pendiente.

## Robustez

- [x] Cancelación segura de conversiones en segundo plano.
- [x] Compresión que preserve texto vectorial cuando sea posible.
- [x] Conservación del armado vigente por expediente.
- [ ] Historial versionado de compilaciones anteriores y repetición de un armado histórico.
- [ ] Instalador firmado y actualización controlada.

## Fuera de alcance hasta decisión expresa

- Carga automática en SRT, SISFE o portales de Provincia.
- Agenda y gestión jurídica integral.
- Oficio y formulario RAEO mediante un flujo automático fijo; se generarán desde modelos editables.
- Regla asistida para monto reclamado, postergada hasta definir el criterio profesional.
- Sellado de tiempo y validación PAdES-LT/LTA, no necesarios en esta etapa.
- Vista previa visual de páginas, descartada para el alcance actual.

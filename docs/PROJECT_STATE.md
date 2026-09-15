# Estado del proyecto

## Identidad portable del expediente

Cada caso recibe al registrarse una identificación interna estable en `.gestor-caso.json`. SQLite la conserva separada de la ruta absoluta. Si toda la Ubicación del Estudio —incluida su base— se mueve a otra unidad o computadora, abrir el caso actualiza la ruta y reutiliza el expediente, movimientos, documentos y tareas existentes. Si la ruta anterior todavía existe, una segunda carpeta con la misma identidad se rechaza como copia ambigua y no toma el historial. La migración a esquema 7 es incremental.

El engranaje permite crear un respaldo ZIP autocontenido de la Ubicación activa. La base SQLite se incorpora mediante una instantánea coherente y el manifiesto registra ruta, tamaño y SHA-256 de cada archivo. La restauración verifica íntegramente el contenido antes de escribir, rechaza rutas inseguras o archivos alterados, sólo admite una carpeta nueva o vacía y agrega la ubicación recuperada al Gestor.

## Recuperación de vínculos tras cambios externos

El menú contextual de Archivos ofrece **Recuperar vínculos de documentos**. Busca en segundo plano dentro del caso y recupera registros cuya ruta falta sólo si tienen SHA-256 previo y un único archivo coincidente no ocupado por otro registro. No mueve archivos ni elige entre duplicados. Conserva identidad, categoría y relaciones SISFE; informa cuántos vínculos no pudo resolver. Archivos sin hash histórico, cambios de contenido y traslados fuera del caso requieren otro tratamiento. La búsqueda se solicita explícitamente para evitar recorrer todo el caso en cada actualización de pantalla.

## Identidad documental al renombrar

Renombrar un archivo o una carpeta interna desde Archivos actualiza las rutas SQLite sin cambiar los identificadores documentales, categorías, hashes ni vínculos con movimientos SISFE. El armado y el Portal se refrescan con el nuevo nombre. Ante un error del registro se intenta restaurar el nombre original; los conflictos no sobrescriben registros existentes. No requiere migración de esquema. La reconciliación de cambios realizados desde el Explorador y el traslado completo entre computadoras quedan pendientes.

## Consolidación de operaciones por expediente

Las consultas SISFE conservan el expediente de origen aunque cambie la selección. Las descargas y sus reintentos conservan también el profesional y sus variables para generar cédulas. Una descarga activa no se reemplaza por un segundo pedido; el cierre espera a que terminen descargas o extracción. La cédula se guarda en el caso de origen sin incorporarse al armado de otro caso seleccionado. La cola de múltiples descargas sigue pendiente. Estas garantías se verifican con pruebas de navegación durante operaciones y cierre.

Actualizado: 14 de septiembre de 2026

Ubicación canónica: `C:\Proyectos\Gestor de documental`

## Decisión de producto vigente

La aplicación dejó de organizar cada caso mediante subcarpetas automáticas. El concepto principal es **Ubicación del Estudio**: puede configurarse una o varias carpetas cuyas hijas directas son los casos. Pueden ser locales, de red o estar sincronizadas por Google Drive para escritorio. Cada caso nace vacío y autosuficiente. Las carpetas internas son opcionales y sólo existen si el usuario las crea o las importa.

Esta decisión responde al objetivo de reducir navegación sin desconocer estructuras existentes. Los nombres normalizados y los metadatos son la opción principal, pero el panel muestra también las carpetas y los archivos anidados.

## Implementado

- Varias Ubicaciones del Estudio configurables, con migración automática de la configuración anterior de una sola carpeta.
- Árbol con una raíz azul por ubicación y buscador inteligente que consulta todos los casos en conjunto.
- Selección del árbol sin el bloque azul nativo de Windows e iconografía vectorial coherente con la paleta del producto.
- Botones secundarios compactos basados en iconos con texto de ayuda accesible; las acciones críticas mantienen etiquetas explícitas.
- Ubicación activa para decidir dónde crear casos y qué biblioteca cotidiana mostrar.
- Desconexión segura de ubicaciones sin eliminar archivos y estado visible para unidades temporalmente no disponibles.
- Acceso rápido almacenado en `00 - ACCESO RÁPIDO` dentro de cada ubicación activa y excluido del árbol de casos, con contracción independiente y expansión temporal del Directorio.
- Entrada con normalización/conversión, arrastre al caso y salida hacia correo u otras aplicaciones desde Acceso rápido.
- Creación y renombrado contextual de casos.
- Metadatos básicos protegidos en modo lectura, con edición explícita, Guardar/Cancelar y confirmación al cambiar de caso o cerrar.
- Ficha principal reducida a Actor, Demandado, Causa, Número de expediente y Radicación; la ficha ampliada se organiza por uso en **Datos generales**, **Entrevista inicial** y **RAEO**.
- Datos procesales organizados por portal/radicación, representación propia y contraparte; Actor, Demandado, Causa y expediente se reutilizan como referencia sin volver a cargarlos.
- Datos personales, laborales, procesales, médicos y probatorios, con filas repetibles para testigos, documentación, responsables, antecedentes LRT, afecciones, atenciones y estudios.
- Carátula y número de expediente derivados de los datos ya existentes; identificación interna, fecha de creación y profesional creador generados por el sistema.
- Cálculos de edad, antigüedad, intervalos entre hitos y remuneraciones, más alertas contextuales y control de datos faltantes para RAEO.
- Por decisión operativa posterior, la ficha admite guardar claves ARCA/AFIP y ANSES como texto dentro de los metadatos locales del caso; no las utiliza para iniciar sesiones automáticamente.
- Indicador visible de ubicación y estado de carga de datos del caso actual.
- Archivos del caso con drag & drop de entrada y salida.
- Copiar, cortar y pegar archivos o carpetas desde el menú contextual o con `Ctrl+C`, `Ctrl+X` y `Ctrl+V`; la carpeta visible se actualiza cuando Windows detecta cambios externos.
- Reconocimiento recursivo, importación, apertura, renombrado y eliminación recuperable de carpetas creadas por el usuario.
- Navegación dentro de subcarpetas sin salir del panel, con ubicación visible y botón Atrás.
- Iconos de Windows por tipo de archivo en el caso y en Acceso rápido.
- Incorporación ordenada a la compilación de todos los archivos compatibles contenidos en una carpeta.
- Cuadro de normalización al importar y conversión opcional a PDF.
- Apertura por doble clic o `Enter`, renombrado directo y envío a Papelera con `Supr`.
- Escritos base o desde modelos Word; el selector de modelos usa una lista buscable y permite definir el título en el mismo cuadro.
- Acciones contextuales de Ficha inicial, Pacto de cuota litis y Poder desde la entrevista, con catálogo Word dinámico, ranking por tipo de caso y selección múltiple de herederos para poderes sucesorios.
- Semáforo configurable en el directorio según la última actividad verificable del caso (archivos, metadatos o movimientos), con archivado reversible y filtros para recientes y archivados.
- Modelo base editable externamente en `%APPDATA%\GestorDocumental\Modelos\Modelo base - Escrito nuevo.docx`.
- Modelo base oficio derivado de `Escrito.dotx`, con la geometría, los márgenes y el formato del original preservados.
- Campos automáticos en modelos Word para profesional, carátula, CUIJ, actor, demandado, causa, radicación, abogado, contraparte, título y fecha.
- Campo visible **Número de expediente**, compatible con la clave histórica CUIJ y utilizable en distintas jurisdicciones.
- Variable `{{FECHA_EXTENSA}}` en castellano y alias `{{NUMERO_EXPEDIENTE}}`.
- Modelo incorporado **Cedula LABVC**, con fecha, Actor, Demandado, Causa y Número de expediente automáticos; conserva los campos manuales de destinatario, domicilio, localidad y proveído.
- Instalación inicial no destructiva de modelos incluidos: nunca reemplaza modelos que el usuario ya modificó.
- `{{PROFESIONAL}}` y `{{ABOGADO}}` priorizan el metadato Abogado, lo convierten a mayúsculas y eliminan Dr./Dra.; si está vacío usan el profesional superior.
- Español (Argentina) configurado en el modelo base.
- Biblioteca de modelos en `%APPDATA%\GestorDocumental\Modelos`.
- Compilación ordenada en un único PDF dentro del caso, con control explícito de la posición del escrito.
- Compilación y acciones finales visibles simultáneamente junto a Archivos, Portal y Pendientes.
- Directorio, información del expediente y Compilación distribuidos mediante divisores ajustables; la columna derecha parte de un ancho compacto, puede ocultarse y recuerda tamaños por computadora.
- Acción **Restablecer distribución** disponible en el engranaje para recuperar proporciones seguras.
- Borrador portátil por caso en `.gestor-compilacion.json`: conserva una preparación inconclusa mediante rutas relativas, incluso al cambiar de computadora. La bandeja informa cantidad, páginas PDF y peso total; una compilación exitosa cierra ese borrador sin tocar originales y conserva el último PDF para abrirlo o firmarlo.
- Nombre de salida propuesto al compilar como `ACTOR_FECHA_TÍTULO.pdf`, con Actor abreviado configurable y confirmación editable.
- Recompilación mediante reemplazo recuperable del PDF anterior o versiones legibles `_V2`, `_V3`, sin sufijos ambiguos `(2)`.
- Identificación visual de Word editable, PDF para firmar y PDF firmado sin crear nuevas subcarpetas.
- Conversión a PDF al importar corregida para Word e imágenes.
- Tratamiento opcional de imágenes en color, escala de grises o blanco y negro, visible sólo al activar la conversión a PDF.
- Compilación en un hilo de trabajo con progreso visible y procesos auxiliares ocultos.
- Botón de cancelación y cierre seguro: detiene el proceso auxiliar, no produce un PDF parcial y cierra al terminar la limpieza.
- Automatización de Word fuera del proceso principal, con límite de 45 segundos por conversión.
- Caché invalidable por tamaño y fecha para reutilizar PDFs de Word sin cambios.
- Optimización de imágenes PDF sin rasterizar páginas completas ni perder texto seleccionable.
- Compresión y pregunta antes de dividir si continúa excedido.
- Límites de 1, 3, 6 y 20 MB.
- Selección ampliable de profesionales.
- Firma PAdES interna mediante token SafeNet y PKCS#11, con SHA-256, validación inmediata y conservación del PDF original.
- Apariencia visible opcional integrada al campo PAdES, con página y posición configurables y vista previa antes de firmar; el estándar propuesto es última página, abajo a la derecha.
- Inicio de sesión del token una sola vez por ejecución: el PIN no se persiste y la sesión puede cerrarse manualmente desde el menú Firmar.
- Portal jurídico separado del área cotidiana de archivos, con contador propio, lista de altura completa y acceso a los movimientos integrados.
- Centro de actividad derivado: reúne detecciones procesales y documental pendiente, ordena lo urgente y conserva navegación al dato de origen sin crear tareas automáticas dudosas.
- Confirmación profesional e idempotente de detecciones como tareas internas, conservando responsable, fecha y vínculo lógico con el movimiento que las originó.
- Cierre explícito de tareas confirmadas: las completadas dejan la bandeja activa sin perder su registro histórico ni el profesional que ejecutó la acción.
- Sugerencia conservadora de recepción documental por coincidencia de nombre, navegable al archivo y sin modificar automáticamente el checklist.
- Vista transversal de Actividad del Estudio, calculada bajo demanda sobre todas las ubicaciones y navegable al expediente de origen.
- Indicador visual reutilizable para estados del Portal: espera, proceso, resultado correcto y error; será alimentado por el gestor de descargas en segundo plano.
- La bandeja del Portal muestra todos los movimientos guardados; ya no recorta silenciosamente la vista a los últimos veinte.
- El flujo operativo de SISFE entra por un único servicio de aplicación y usa el navegador autenticado; el antiguo transporte HTTP queda fuera de la selección normal.
- El detalle de una novedad ofrece descarga automática mediante los controles renderizados por SISFE: selecciona la página oficial, acciona el documento principal y recorre los adjuntos adicionales sin copiar credenciales ni reproducir los endpoints de descarga.
- El encabezado operativo del expediente usa la ubicación actual o trámite interno informado por SISFE y su vigencia. Los movimientos tienen una primera interpretación determinística para audiencias, traslados y vencimientos explícitos, mostrando fecha extraída, texto de origen y advertencias sin crear eventos automáticamente.
- El núcleo fuente estable de Extractor SISFE (`90e3de3`) fue integrado como módulo interno `gestor_documental.extractor_core`, junto con su catálogo público. La generación de cédulas importa este módulo directamente; no modifica `sys.path`, no ejecuta otro programa y se verifica dentro del instalador autocontenido.
- Cada PDF descargado se registra por hash y queda relacionado en SQLite con el movimiento SISFE exacto y su rol (principal o adicional); la relación y la deduplicación son idempotentes.
- Las descargas SISFE se ejecutan secuencialmente en una cola oculta que conserva caso, movimiento y profesional. El Portal refleja espera, ejecución y error por movimiento, continúa con el pedido siguiente ante un fallo y permite reintentar el movimiento afectado.
- Los diálogos SISFE, la lista ordenable de compilación y los roles de interfaz ya viven en módulos propios, primer corte efectivo para reducir `app.py` sin modificar el flujo visible.
- Selector de profesionales con acción de alta incorporada y menú de configuración rápida en el engranaje.
- Perfil persistente por profesional con identidad, contacto, condición fiscal, matrículas y datos bancarios reutilizables como variables Word; el último profesional elegido se restaura al iniciar.
- Checklist operativo de documentación pendiente, compartido con la entrevista del caso y actualizable al recibir cada elemento.
- Proyección SQLite refrescada desde los metadatos vigentes del caso y conservación de la identidad relacional al renombrar su carpeta.
- Clientes compartidos por identidad con varios casos visualmente agrupados; los datos personales ya conocidos precargan campos vacíos de otro caso sólo al abrir su formulario, sin modificar carpetas ni metadatos hermanos.
- Nombre `_FIRMADO` con versiones legibles y advertencia si el tamaño posterior a la firma supera el perfil seleccionado.
- Apertura o preparación del PDF para una aplicación externa de firma configurable como alternativa.
- Reutilización de la sesión abierta de Xólido y archivo arrastrable hacia su grilla.
- Registro local de errores y aviso visible ante fallos inesperados.
- Guardado atómico de metadatos ocultos; `Tab` sólo cambia de campo y nunca guarda accidentalmente.
- Normalización temporal de PDFs con cifrado AES, incluidos archivos generados por PdfLive/SRT.
- Lectura de PDF desde memoria y cierre explícito de recursos para no bloquear carpetas del caso en Windows.

## Límites actuales

- La firma interna requiere SafeNet Authentication Client, el token conectado y un certificado vigente. La versión inicial produce PAdES básico; todavía no incorpora sellado de tiempo ni información de revocación para preservación de largo plazo (PAdES-LT/LTA).
- La validación inmediata comprueba la integridad criptográfica del PDF. La confianza jurídica completa depende de la cadena reconocida por el sistema receptor.
- Xólido no ofrece una interfaz de línea de comandos documentada para precargar el archivo; por eso la alternativa externa lo deja listo para arrastrar en un solo gesto.
- El cuadro RAEO valida y prepara los datos, pero la emisión automática del oficio y del formulario queda para la siguiente iteración.
- El monto reclamado permanece manual hasta acordar una regla de cálculo jurídico; la aplicación no inventa una fórmula.
- No se migran automáticamente casos creados con la estructura anterior.
- Google Drive se usa a través de una carpeta visible en Windows y sincronizada o montada por Google Drive para escritorio; no existe todavía una conexión directa con la web de Drive.
- La automatización depende de que SISFE conserve sus rutas y controles actuales. Ante una demora, cambio del portal o error 500 del servidor, el Gestor detiene el intento y deja la vista oficial abierta para reintentar con el clip, sin recurrir al transporte alternativo que producía respuestas inconsistentes.

## Alcance preservado

La prioridad inmediata sigue siendo consolidar el flujo documental y SISFE. La relación básica cliente-casos ya existe; agenda y seguimiento procesal integral se incorporarán por etapas después de separar dominio, servicios e interfaz. MEV y SRT permanecen pausados.

## Publicación

La versión `0.13.4` es la referencia estable de trabajo y cuenta con instalador transaccional para Windows. Primero prepara y valida el programa nuevo, cierra todos los procesos de la instalación anterior y conserva una copia de respaldo durante el intercambio. Reemplaza sólo el programa y mantiene las Ubicaciones del Estudio, `%APPDATA%\GestorDocumental`, los modelos personalizados y las bases locales. El arranque no depende de poder escribir el registro de diagnóstico y el instalador valida los accesos directos antes de confirmar la actualización. El instalador todavía no está firmado con un certificado de publicación ni incorpora actualización automática.

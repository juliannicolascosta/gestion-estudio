# Estado del proyecto

Actualizado: 2 de septiembre de 2026

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
- Acceso rápido siempre visible, almacenado en `00 - ACCESO RÁPIDO` dentro de cada ubicación activa y excluido del árbol de casos.
- Entrada con normalización/conversión, arrastre al caso y salida hacia correo u otras aplicaciones desde Acceso rápido.
- Creación y renombrado contextual de casos.
- Metadatos básicos protegidos en modo lectura, con edición explícita, Guardar/Cancelar y confirmación al cambiar de caso o cerrar.
- Ficha ampliada organizada por uso en **Datos generales**, **Entrevista inicial** y **RAEO**, para mantener breve la pantalla cotidiana.
- Datos personales, laborales, procesales, médicos y probatorios, con filas repetibles para testigos, documentación, responsables, antecedentes LRT, afecciones, atenciones y estudios.
- Carátula y número de expediente derivados de los datos ya existentes; identificación interna, fecha de creación y profesional creador generados por el sistema.
- Cálculos de edad, antigüedad, intervalos entre hitos y remuneraciones, más alertas contextuales y control de datos faltantes para RAEO.
- Las credenciales ARCA/AFIP y ANSES no se almacenan: sólo se registra si el acceso fue informado o verificado.
- Indicador visible de ubicación y estado de carga de datos del caso actual.
- Archivos del caso con drag & drop de entrada y salida.
- Reconocimiento recursivo, importación, apertura, renombrado y eliminación recuperable de carpetas creadas por el usuario.
- Navegación dentro de subcarpetas sin salir del panel, con ubicación visible y botón Atrás.
- Iconos de Windows por tipo de archivo en el caso y en Acceso rápido.
- Incorporación ordenada a la compilación de todos los archivos compatibles contenidos en una carpeta.
- Cuadro de normalización al importar y conversión opcional a PDF.
- Apertura por doble clic o `Enter`, renombrado directo y envío a Papelera con `Supr`.
- Escritos base o desde modelos Word; el selector de modelos usa una lista buscable y permite definir el título en el mismo cuadro.
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
- Nombre de salida propuesto al compilar como `ACTOR_FECHA_TÍTULO.pdf`, con Actor abreviado configurable y confirmación editable.
- Recompilación mediante reemplazo recuperable del PDF anterior o versiones legibles `_V2`, `_V3`, sin sufijos ambiguos `(2)`.
- Identificación visual de Word editable, PDF para firmar y PDF firmado sin crear nuevas subcarpetas.
- Conversión a PDF al importar corregida para Word e imágenes.
- Compilación en un hilo de trabajo con progreso visible y procesos auxiliares ocultos.
- Botón de cancelación y cierre seguro: detiene el proceso auxiliar, no produce un PDF parcial y cierra al terminar la limpieza.
- Automatización de Word fuera del proceso principal, con límite de 45 segundos por conversión.
- Caché invalidable por tamaño y fecha para reutilizar PDFs de Word sin cambios.
- Optimización de imágenes PDF sin rasterizar páginas completas ni perder texto seleccionable.
- Compresión y pregunta antes de dividir si continúa excedido.
- Límites de 1, 3, 6 y 20 MB.
- Selección ampliable de profesionales.
- Firma PAdES interna mediante token SafeNet y PKCS#11, con SHA-256, validación inmediata y conservación del PDF original.
- Inicio de sesión del token una sola vez por ejecución: el PIN no se persiste y la sesión puede cerrarse manualmente desde el menú Firmar.
- Portal jurídico separado del área cotidiana de archivos, con contador propio y acceso a los movimientos integrados.
- Checklist operativo de documentación pendiente, compartido con la entrevista del caso y actualizable al recibir cada elemento.
- Proyección SQLite refrescada desde los metadatos vigentes del caso y conservación de la identidad relacional al renombrar su carpeta.
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

## Alcance preservado

La app sigue siendo documental. No incluye agenda, clientes, estrategia, seguimiento procesal ni presentación automática en sistemas judiciales.

## Publicación

El desarrollo está versionado en GitHub. Todavía no se generó una versión estable, actualización automática ni instalador firmado para distribución general.

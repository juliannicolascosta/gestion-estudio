# Gestor de documental

Aplicación de escritorio para organizar los casos de un estudio, trabajar sus archivos y compilar presentaciones judiciales con la menor navegación posible.

## Modelo de trabajo

El usuario puede definir una o varias **Ubicaciones del Estudio**. Cada carpeta hija directa de una ubicación es un caso. Las ubicaciones pueden ser locales, de red o carpetas sincronizadas por Google Drive para escritorio. La aplicación no crea automáticamente `01 Escritos`, `02 Documental` ni `PARA PRESENTAR`; si el usuario crea carpetas internas o incorpora un caso que ya las tiene, las reconoce y muestra su contenido en el mismo panel.

## Funciones actuales

- Buscador conjunto en todas las Ubicaciones del Estudio por nombre, actor, demandado, causa, número de expediente, radicación, abogado o contraparte.
- Árbol con una carpeta raíz azul por ubicación, todos sus casos e iconos de tipo; permite renombrar los casos desde el menú contextual.
- Iconografía vectorial moderna para ubicaciones, casos, tipos de archivo y acciones; los comandos secundarios repetitivos usan iconos con ayuda emergente y las acciones principales conservan su nombre.
- Ubicación activa seleccionable: determina dónde se crea el próximo caso y qué biblioteca de Acceso rápido se muestra.
- Las ubicaciones temporalmente desconectadas permanecen visibles como **Ubicación no disponible** y pueden quitarse del Gestor sin borrar sus archivos.
- **Acceso rápido** disponible para DNI, matrícula, CBU, constancias y documental reutilizable, con controles para contraer la biblioteca o ampliar temporalmente el Directorio.
- Cada ubicación tiene su propia biblioteca en `00 - ACCESO RÁPIDO`, pero esa carpeta no aparece como si fuera un caso.
- Creación de casos vacíos, sin subcarpetas automáticas; reconocimiento, importación y renombrado de carpetas creadas por el usuario.
- Datos del caso protegidos contra cambios involuntarios: se muestran en modo lectura y sólo se modifican mediante **Editar datos**, con Guardar/Cancelar y aviso si se intenta cambiar de caso con cambios pendientes.
- Datos procesales con portal asociado, radicaciones de ambas instancias y domicilios de las partes, sin duplicar la identidad principal del expediente.
- **Más datos** se organiza en tres pestañas: **Datos generales**, **Entrevista inicial** y **RAEO**. La pantalla principal conserva sólo Actor, Demandado, Causa, Número de expediente y Radicación, mientras que la ficha ampliada incorpora datos personales, laborales, procesales, médicos, prueba, campos repetibles y datos propios del formulario RAEO.
- Carátula y número de expediente se reutilizan del caso: nunca se vuelven a cargar en RAEO. El sistema genera además una identificación interna, fecha de creación y profesional creador.
- Cálculos automáticos de edad, antigüedad, días entre hitos médicos/laborales, remuneración mensual estimada y diferencia con convenio; alertas de datos RAEO faltantes y sugerencias contextuales.
- Archivos del caso con arrastre, copiar/cortar/pegar, actualización ante cambios externos, iconos de tipo y navegación interna por subcarpetas mediante doble clic, `Enter` y **Atrás**.
- Normalización de nombre al importar, con conversión opcional de Word o imagen a PDF; las imágenes admiten color, escala de grises o blanco y negro.
- Apertura de archivos con doble clic o `Enter`, renombrado con `F2` y envío recuperable a la Papelera con `Supr`.
- Escritos nuevos desde el modelo oficio provisto por el usuario, editable externamente en Word, y escritos desde modelos precargables mediante una lista moderna con búsqueda y título editable en el mismo paso.
- Inserción automática del profesional seleccionado y de la carátula `ACTOR C/ DEMANDADO S/ CAUSA` con CUIJ.
- Modelo precargado **Cedula LABVC**, basado en el formulario aportado por el usuario: completa fecha extensa, Actor, Demandado, Causa y Número de expediente.
- Idioma predeterminado del modelo base: Español (Argentina).
- Área central con pestañas **Archivos**, **Portal jurídico** y **Documentación pendiente**; la **Compilación** permanece a la derecha junto con las acciones finales, pero ahora puede redimensionarse u ocultarse desde el encabezado.
- Los anchos del Directorio, el área de trabajo y la Compilación, junto con las divisiones verticales internas, se recuerdan en esta computadora. El engranaje permite **Restablecer distribución**.
- Borrador de compilación guardado por expediente con rutas portátiles: conserva orden, escrito, perfil de tamaño y último resultado al cambiar de caso, reiniciar o abrir el Estudio desde otra computadora.
- Lista ordenable de documental y escrito; el escrito nuevo se coloca al final y puede moverse con arrastre o con **Subir/Bajar**.
- Compilación de todos los elementos en un único PDF, respetando el orden visible.
- Al pulsar **Compilar PDF** propone un nombre identificable `ACTOR_FECHA_TÍTULO.pdf`, editable antes de comenzar. Si ya existe, permite reemplazarlo de forma segura o crear `_V2`, `_V3`, etc.
- Los Word de trabajo se identifican como **EDITABLE**, los PDF de salida como **PARA FIRMAR** y los archivos cuyo nombre indica firma como **FIRMADO**. No se crean carpetas ni copias auxiliares permanentes.
- Perfiles de tamaño:

  - SRT: 1 MB.
  - SISFE común: 3 MB.
  - SISFE demanda o contestación: 6 MB.
  - Provincia de Buenos Aires: 20 MB.

- Compresión automática. Si el resultado todavía excede el límite, pregunta antes de dividirlo.
- Compilación en segundo plano con una ventana de progreso, cancelación segura y sin mostrar PowerShell.
- Pestaña **Portal jurídico** de altura completa, con el estado actual del expediente y desde cuándo rige, además de todas las novedades SISFE almacenadas, recorriendo todas las páginas disponibles y evitando movimientos repetidos.
- Indicador compacto de estado SISFE preparado para distinguir espera, operación en curso, finalización correcta y error sin ocupar espacio documental.
- Desde el detalle de una novedad, **Descargar documentos** abre el expediente, ubica la página correcta y acciona los clips oficiales de SISFE. Los PDF se guardan en `Documentos SISFE`, se vinculan con el movimiento de origen, se registran por hash y las copias idénticas se descartan de forma recuperable. Si SISFE no inicia la descarga, la vista oficial queda abierta para reintentar manualmente.
- El estado vigente se toma de **Trámite interno / Ubicación actual** de SISFE, incluyendo la fecha “desde” cuando está disponible. Las novedades se interpretan por separado mediante reglas auditables para detectar audiencias, traslados y vencimientos explícitos; cada detección conserva su texto de origen y advierte cuando falta una fecha cierta.
- Ficha ampliada a pantalla completa, organizada por tipo de caso (LRT, laboral, responsabilidad civil, sucesiones u otros), con datos generales, procesales y específicos sin perder metadatos históricos. Incluye nombre completo, derivación y variables rápidas de fecha para modelos Word.
- Generación contextual de **Ficha inicial**, **Pacto de cuota litis** y **Poder** desde la ficha ampliada. El catálogo Word se relee en cada uso, ordena primero los modelos afines al tipo de caso sin ocultar los demás y permite actualizarlo o agregar modelos durante la selección. En sucesiones, el poder puede generarse para uno o varios herederos.
- Semáforo del directorio configurable: verde para actividad normal, amarillo y rojo según los días definidos, y gris para casos archivados. La fecha considera archivos, metadatos y novedades registradas; los casos recientes o archivados pueden ocultarse desde el engranaje.
- Pestaña **Documentación pendiente** con un checklist operativo para agregar, ordenar, renombrar, borrar, vaciar y marcar como recibido lo solicitado al cliente.
- Liberación inmediata de los PDF leídos: al terminar de compilar o dividir, las carpetas del caso pueden renombrarse o eliminarse desde el Explorador de Windows.
- Conversión de Word aislada del proceso principal, con tiempo máximo y caché local para no reconvertir escritos sin cambios.
- Optimización de PDF que conserva el texto y evita rasterizar todas las páginas.
- Firma digital PAdES dentro del Gestor mediante token SafeNet/PKCS#11. El PIN se solicita una vez, no se guarda y la sesión se reutiliza hasta cerrarla manualmente o salir de la aplicación.
- Firma visible opcional dentro de la misma operación PAdES: permite elegir página y seis posiciones, muestra una vista previa y usa como opción estándar la última página abajo a la derecha. El PDF original nunca se modifica.
- Cada firma se valida inmediatamente y crea un archivo `_FIRMADO.pdf` sin modificar el PDF original. Si el tamaño firmado supera el límite elegido, se advierte sin alterar el documento ya firmado.
- Xólido continúa disponible como alternativa: reutiliza su sesión abierta y muestra el PDF listo para arrastrar a su cuadro de documentos.
- Selector de profesionales con **Añadir nuevo profesional…** como primera opción y un menú de configuración para MEV, firmador y modelos.
- Perfil único y editable por profesional con DNI, CUIT, domicilio, contacto, condición fiscal, matrículas y datos bancarios. La carga se reutiliza automáticamente en los modelos Word y el último perfil utilizado permanece seleccionado.

## Iniciar

En esta instalación local, hacé doble clic en `Iniciar Gestor de documental.cmd`.

Para preparar el entorno desde cero:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python run.py
```

Microsoft Word o LibreOffice es necesario para convertir documentos Word. La integración opcional más directa con Word se instala con `pywin32`.

## Primer uso

1. Pulsá **Agregar ubicación** y elegí la carpeta que contiene tus casos. Podés repetirlo para sumar una ubicación local, de red o sincronizada por Google Drive.
2. Elegí una carpeta existente del árbol o creá **Nuevo caso**.
3. Arrastrá a **Acceso rápido** los documentos que usás en distintos casos o correos.
4. Pulsá **Editar datos**, completá lo necesario y guardá. **Más datos** abre las pestañas de ficha general, entrevista y RAEO.
5. Creá o elegí un escrito y, desde **Archivos**, enviá la documental a **Compilación**.
6. Ordená los elementos en el panel derecho **Compilación**, elegí el límite y pulsá **Compilar PDF**. Confirmá el nombre sugerido para reconocerlo fácilmente después de firmarlo.
7. Pulsá **Firmar → Firmar dentro del Gestor**. La primera firma de la sesión solicita el PIN del token; las siguientes reutilizan la sesión. También podés continuar usando Xólido.

Atajos: `Ctrl+Shift+N` crea un caso, `Ctrl+N` abre las opciones de escrito, `Ctrl+O` agrega archivos, `Ctrl+P` compila, `F2` renombra, `Enter` abre y `Supr` envía a la Papelera (o quita de la compilación, según el panel activo).

Para cambiar lo que genera **Escrito nuevo**, elegí **+ Escrito → Modificar modelo base en Word**. El archivo es `%APPDATA%\GestorDocumental\Modelos\Modelo base - Escrito nuevo.docx`; se edita como cualquier Word y los cambios se aplican a los escritos nuevos posteriores. **Ver campos automáticos…** muestra las variables disponibles, entre ellas `{{PROFESIONAL}}`, `{{CARATULA}}`, `{{CUIJ_COMPLETO}}`, `{{ACTOR}}`, `{{DEMANDADO}}`, `{{CAUSA}}`, `{{NOMBRE_CORTO}}` y `{{TITULO}}`. Los campos creados en **Más datos** también se convierten en variables. La guía completa está en `docs/MODELOS_WORD.md`.

## Datos y seguridad

- Configuración general y modelos: `%APPDATA%\GestorDocumental`.
- Caché local de conversiones Word: `%LOCALAPPDATA%\GestorDocumental\conversion-cache`; se invalida automáticamente al cambiar el archivo original.
- Metadatos de cada caso: `.gestor-caso.json`, dentro de su carpeta.
- El PIN del token no se almacena en configuración, metadatos ni registros. La sesión autenticada sólo vive mientras el proceso del Gestor está abierto.
- Por decisión operativa, las claves ARCA/AFIP y ANSES pueden guardarse como texto en los metadatos locales del caso para copiar y pegar. No se envían automáticamente a ningún portal.
- Los archivos importados se copian; el original externo no se modifica.
- Quitar una Ubicación del Estudio sólo la desconecta de la aplicación: nunca elimina la carpeta ni sus casos.
- Quitar un elemento de la compilación no borra el archivo del caso. `Supr` en **Archivos del caso** pide confirmación y lo envía a la Papelera de Windows.
- La app no elimina ni migra automáticamente la estructura usada por versiones anteriores.

## Estado

La versión en desarrollo es la `0.12.0`, una evolución del MVP `delivery-sisfe`. Incorpora firma PAdES con sesión de token reutilizable, una ficha ampliada por uso —general, entrevista y RAEO— y contextos operativos para portal y documentación pendiente, sin convertir todavía la aplicación en un gestor jurídico integral. Conserva las varias **Ubicaciones del Estudio**, la búsqueda conjunta y Xólido como alternativa. Una carpeta compartida de Google Drive debe aparecer en el Explorador mediante Google Drive para escritorio. El desarrollo está versionado; todavía no hay una publicación estable para usuarios finales.

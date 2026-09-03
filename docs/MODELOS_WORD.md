# Modelos Word y campos automáticos

## Cómo ubicar los metadatos

Los campos automáticos son textos entre llaves que se escriben directamente en el lugar del documento Word donde debe aparecer el dato. Al crear un escrito, Gestor de documental hace una copia del modelo y reemplaza esos textos. El modelo original no se modifica.

Campos disponibles:

- `{{PROFESIONAL}}`: valor de **Abogado**, convertido a mayúsculas y sin `Dr.`, `Dra.`, `Doctor` o `Doctora`. Si Abogado está vacío, usa el profesional seleccionado arriba.
- `{{CARATULA}}`: `ACTOR C/ DEMANDADO S/ CAUSA`, en mayúsculas.
- `{{NUMERO_EXPEDIENTE}}`: Número de expediente o CUIJ, sin texto adicional. `{{CUIJ}}` sigue disponible como alias para modelos anteriores.
- `{{EXPEDIENTE_SRT}}`: número de expediente o trámite ante la SRT, independiente del expediente judicial.
- `{{NOMBRE_COMPLETO}}`: texto ingresado una sola vez en la ficha.
- `{{APELLIDO}}` y `{{NOMBRES}}`: componentes interpretados del nombre.
- `{{NOMBRE_APELLIDO}}`: variante natural, por ejemplo `Juan Carlos Pérez`.
- `{{APELLIDO_NOMBRES}}`: variante para carátulas, por ejemplo `Pérez, Juan Carlos`.
- `{{PORTAL_JURIDICO}}`: portal asociado al caso.
- `{{RADICACION}}` y `{{RADICACION_SEGUNDA_INSTANCIA}}`: radicaciones de primera y segunda instancia.
- `{{DOMICILIO_DEMANDADO}}`, `{{ABOGADO_CONTRAPARTE}}`, `{{DOMICILIO_PROCESAL_CONTRAPARTE}}` y `{{DOMICILIO_ELECTRONICO_CONTRAPARTE}}`: datos procesales de la parte contraria.
- `{{CUIJ_COMPLETO}}`: espacio, paréntesis y CUIJ, por ejemplo ` (CUIJ N° 21-12345678-9)`. Si no hay número, desaparece todo el bloque.
- `{{ACTOR}}`, `{{DEMANDADO}}`, `{{CAUSA}}`, `{{RADICACION}}`, `{{ABOGADO}}` y `{{CONTRAPARTE}}`: cada dato individual.
- `{{NOMBRE_CORTO}}`: identificador breve configurado en **Más datos**; si está vacío se infiere del Actor. También se usa para proponer el nombre del PDF.
- `{{JURISDICCION}}`, `{{FUERO}}`, `{{JUZGADO}}`, `{{SECRETARIA}}`, `{{SALA}}`, `{{LOCALIDAD}}`, `{{DOCUMENTO_ACTOR}}`, `{{DOCUMENTO_DEMANDADO}}`, `{{DOMICILIO_ACTOR}}`, `{{DOMICILIO_DEMANDADO}}`, `{{DOMICILIO_LEGAL}}`, `{{DOMICILIO_ELECTRONICO}}`, `{{MATRICULA}}` y `{{TOMO_FOLIO}}`: datos opcionales de la ficha ampliada.
- `{{TITULO}}`: nombre breve elegido al crear el escrito, en mayúsculas.
- `{{FECHA}}`: fecha actual como `13/08/2026`.
- `{{FECHA_ISO}}`: fecha actual como `2026-08-13`.
- `{{FECHA_EXTENSA}}`: fecha actual como `13 de agosto de 2026`.
- `{{EDAD}}` o `{{EDAD_RAEO}}`: edad calculada a la fecha de la contingencia; si no existe, a la fecha actual. El campo manual de RAEO tiene prioridad.
- `{{ANTIGUEDAD_LABORAL}}`: antigüedad calculada con las fechas disponibles.
- `{{DIAS_ACCIDENTE_DENUNCIA_ART}}`, `{{DIAS_ACCIDENTE_ALTA_MEDICA}}` y `{{DIAS_ALTA_REINGRESO}}`: intervalos automáticos cuando las fechas necesarias están cargadas.
- `{{REMUNERACION_MENSUAL_ESTIMADA}}` y `{{DIFERENCIA_REMUNERACION_CONVENIO}}`: cálculos orientativos a partir de remuneración, periodicidad y CCT.

En la pantalla, el campo antes llamado **CUIJ** aparece como **Número de expediente**. Los valores cargados con versiones anteriores se conservan y continúan funcionando.

Los campos personalizados creados en **Más datos** reciben una variable automática. Por ejemplo, **Nombre del mediador** se usa como `{{NOMBRE_DEL_MEDIADOR}}`. La aplicación muestra el nombre de la variable junto al campo para poder copiarlo al Word sin adivinarlo.

Todos los nuevos campos generales, de entrevista y RAEO siguen la misma regla. Por ejemplo, **Fecha del accidente** se usa como `{{FECHA_DEL_ACCIDENTE}}` y **Monto reclamado** como `{{MONTO_RECLAMADO}}`. Los campos repetibles se insertan como líneas legibles; por ejemplo, `{{POSIBLES_TESTIGOS}}` conserva un testigo por renglón.

## Ejemplo: apelación

En el Word modelo puede escribirse:

> {{PROFESIONAL}}, abogado de la parte actora, en autos caratulados “{{CARATULA}}”{{CUIJ_COMPLETO}}, ante V.S. respetuosamente digo:

Si el caso tiene cargados Abogado `Dr. Julián Nicolás Costa`, Actor `Pérez`, Demandado `Provincia de Santa Fe`, Causa `Daños y perjuicios` y su CUIJ, la copia generada dirá:

> JULIÁN NICOLÁS COSTA, abogado de la parte actora, en autos caratulados “PÉREZ C/ PROVINCIA DE SANTA FE S/ DAÑOS Y PERJUICIOS” (CUIJ N° …), ante V.S. respetuosamente digo:

## Incorporar el modelo

1. Preparar el documento en Word como debe verse.
2. Escribir los campos automáticos en los lugares correspondientes. Pueden tener el formato, tamaño, negrita o alineación deseados.
3. Guardarlo como `.docx`.
4. En la aplicación, elegir **+ Escrito → Agregar modelo…**.
5. Para usarlo, elegir **+ Escrito → Desde modelo…**, buscarlo en la lista y asignar el nombre breve del escrito en el mismo cuadro.

Para el escrito genérico, **+ Escrito → Modificar modelo base en Word** abre directamente el archivo externo editable.

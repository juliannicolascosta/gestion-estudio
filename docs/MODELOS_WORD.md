# Modelos Word y campos automáticos

## Cómo ubicar los metadatos

Los campos automáticos son textos entre llaves que se escriben directamente en el lugar del documento Word donde debe aparecer el dato. Al crear un escrito, Gestor de documental hace una copia del modelo y reemplaza esos textos. El modelo original no se modifica.

Campos disponibles:

- `{{PROFESIONAL}}`: valor de **Abogado**, convertido a mayúsculas y sin `Dr.`, `Dra.`, `Doctor` o `Doctora`. Si Abogado está vacío, usa el profesional seleccionado arriba.
- `{{CARATULA}}`: `ACTOR C/ DEMANDADO S/ CAUSA`, en mayúsculas.
- `{{NUMERO_EXPEDIENTE}}`: Número de expediente o CUIJ, sin texto adicional. `{{CUIJ}}` sigue disponible como alias para modelos anteriores.
- `{{CUIJ_COMPLETO}}`: espacio, paréntesis y CUIJ, por ejemplo ` (CUIJ N° 21-12345678-9)`. Si no hay número, desaparece todo el bloque.
- `{{ACTOR}}`, `{{DEMANDADO}}`, `{{CAUSA}}`, `{{RADICACION}}`, `{{ABOGADO}}` y `{{CONTRAPARTE}}`: cada dato individual.
- `{{NOMBRE_CORTO}}`: identificador breve configurado en **Más datos**; si está vacío se infiere del Actor. También se usa para proponer el nombre del PDF.
- `{{JURISDICCION}}`, `{{FUERO}}`, `{{JUZGADO}}`, `{{SECRETARIA}}`, `{{SALA}}`, `{{LOCALIDAD}}`, `{{DOCUMENTO_ACTOR}}`, `{{DOCUMENTO_DEMANDADO}}`, `{{DOMICILIO_ACTOR}}`, `{{DOMICILIO_DEMANDADO}}`, `{{DOMICILIO_LEGAL}}`, `{{DOMICILIO_ELECTRONICO}}`, `{{MATRICULA}}` y `{{TOMO_FOLIO}}`: datos opcionales de la ficha ampliada.
- `{{TITULO}}`: nombre breve elegido al crear el escrito, en mayúsculas.
- `{{FECHA}}`: fecha actual como `13/08/2026`.
- `{{FECHA_ISO}}`: fecha actual como `2026-08-13`.
- `{{FECHA_EXTENSA}}`: fecha actual como `13 de agosto de 2026`.

En la pantalla, el campo antes llamado **CUIJ** aparece como **Número de expediente**. Los valores cargados con versiones anteriores se conservan y continúan funcionando.

Los campos personalizados creados en **Más datos** reciben una variable automática. Por ejemplo, **Nombre del mediador** se usa como `{{NOMBRE_DEL_MEDIADOR}}`. La aplicación muestra el nombre de la variable junto al campo para poder copiarlo al Word sin adivinarlo.

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

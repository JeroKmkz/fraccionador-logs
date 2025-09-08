# 📂 Fraccionador de Logs - Trivial IRC

Herramienta web para **limpiar, compactar y dividir** logs de partidas de Trivial IRC en partes manejables, con **análisis estadístico para cronistas**.

## 🎯 Características

* 🧹 **Limpieza IRC (opcional)**: elimina códigos de color/estilo y residuos.
* 🧽 **Limpieza Máxima (opcional)**: compacta el log para crónica.

  * Quita timestamps iniciales.
  * Suprime ránkings intermedios del bot (equipos e individuales).
  * Suprime “SCRATCHES / PALOS / ACES” finales del bot.
  * Suprime “---- Estadística de temas ----” y sus líneas (“DEPORTE-3…”) del bot.
  * Mantiene “La buena/Las buenas” y “\*\*\* DATO EXTRA PARA EL CRONISTA \*\*\*”.
  * Recorta solo el fragmento “Base Datos Preguntas: …”.
  * “>>>” se compacta a “>>”; se conserva el separador `nick>`.
* ✂️ **División inteligente**: corta siempre justo al inicio de cada pregunta.
* 📊 **Análisis extra para cronistas** (opcional):

  * **Equipos y plantillas**: presentes/ausentes (formato `X/10 en plantilla`).
  * **Marcador por cortes** y **lucha por el MVP**.
  * **Resumen final**: clasificación individual y por equipos (con puntos, scratches, aces y palos).
  * **Records globales**:

    * Pregunta con **mayor dificultad** (tiempo hasta el primer acierto).
    * **Parcial** más favorable (umbral mínimo +3, permite múltiples preguntas empatadas).
    * **Racha interrumpida** (≥ 8 aciertos seguidos).
  * **Sprint final**: en las **últimas 5 preguntas**, si la diferencia ≤ 10, muestra marcador tras cada cierre.
* 📦 **Descarga directa** de cada parte en `.txt` o todo junto en `.zip`.
* 🔒 **100% privado**: todo se procesa **localmente** en tu navegador.
* 📱 **Responsive**: móvil y escritorio.

## 🚀 Uso

1. **Abre la herramienta**.
2. **Sube tu archivo** `.txt`/`.log` del canal.
3. Elige:

   * **Número de partes** (2–20, por defecto 4).
   * **Limpiar códigos IRC** (recomendado para detección robusta).
   * **Limpieza máxima** (recomendado para crónica).
   * **Análisis extra** (si quieres los datos para el cronista).
4. Pulsa **“Procesar Log”**.
5. **Descarga** las partes o el `.zip`.

## 📋 Formato de logs soportado

Detecta preguntas con variantes típicas de Trivial IRC, con o sin códigos, por ejemplo:

```
23:00:51''282 <Saga_Noren> Pregunta: 1 / 35 Base Datos Preguntas: TrivialIrc
23:00:53''098 <Saga_Noren> MEDICINA-SALUD ¿QUÉ AGENTE PATÓGENO PRODUCE LA LEPRA?
23:00:56''379 <AlaskaYoung> bacilo de hansen
23:00:59''409 <Saga_Noren> >>>ALASKAYOUNG acea
```

También funciona con timestamps y color-codes presentes. El bot se **auto-detecta** (por ejemplo `Saga_Noren`); si no se puede, usa un valor por defecto razonable.

## 🔧 División inteligente

* Localiza **“Pregunta: X / Y”** con detección robusta.
* Corta **antes** de cada nueva pregunta.
* Mantiene cada pregunta con su bloque de respuestas.
* Intenta **equilibrar** el tamaño de las partes.

## 🧽 Limpiezas

**Limpieza IRC**
Elimina:

* Códigos de color (`\x03` + números), negrita `\x02`, cursiva `\x1D`, subrayado `\x1F`, reset `\x0F`.
* Secuencias ANSI y caracteres de control.
* Espacios múltiples/residuos.

**Limpieza Máxima**
Además de lo anterior:

* Quita timestamps del inicio.
* Suprime ránkings intermedios y listados tipo `1º 31 LIDERES` y `4 ·CLYDE82–…` **cuando los emite el bot**.
* Suprime “SCRATCHES / PALOS / ACES” finales **del bot**.
* Suprime “---- Estadística de temas ----” y sus líneas “TEMA-#” **del bot**.
* Recorta solo el fragmento “Base Datos Preguntas: …” (mantiene la línea).
* Mantiene soluciones (“La buena/Las buenas”) y **DATO EXTRA**.
* Convierte `>>>` a `>>` y conserva el formato `nick>`.

## 🧠 Análisis extra (para cronistas)

Incluye, al final de cada parte:

* **Equipos participantes** con plantilla y presentes/ausentes.
* **Marcador del corte** y **top de MVP** provisional.
* **Resumen final** (última parte):

  * **Estadísticas de preguntas** (mayor dificultad, parciales más favorables, racha interrumpida).
  * **Clasificación individual** (puntos + scratches/aces/palos).
  * **Clasificación por equipos** (puntos + agregados scratches/aces/palos).

Además, inserta en el propio log (a la altura de cada pregunta relevante):

* **DATO EXTRA** con la pregunta de mayor dificultad, los **parciales** de las preguntas récord (umbral +3), la **racha interrumpida** y, en el **sprint final**, el **marcador tras cada pregunta** si la diferencia ≤ 10.

> Nota: el análisis se basa en lo que anuncia el bot (aciertos, “La buena/Las buenas”, etc.). No necesita conservar los ránkings intermedios del bot en la salida.

## 🛠️ Tecnologías

* HTML5 / CSS3 / JavaScript Vanilla
* [JSZip](https://stuk.github.io/jszip/) para empaquetar en ZIP
* Funciona en **navegador** (sin servidor)

## ❓Preguntas frecuentes

* **“No se encontraron preguntas en el archivo”**
  Activa **“Limpiar códigos IRC”** o verifica que las líneas de pregunta contengan `Pregunta: X / Y`. La detección es flexible con timestamps/códigos.

* **¿Puedo usar solo la limpieza máxima sin análisis?**
  Sí. Marca “Limpieza máxima” y desmarca “Análisis extra”.

* **¿Se pierden respuestas correctas al limpiar?**
  No. Se mantienen “La buena/Las buenas” y los eventos de acierto necesarios para el análisis.

## 📄 Licencia

Proyecto de código abierto bajo **Licencia MIT**.

## 🙏 Agradecimientos

* Comunidad de **Trivial IRC**.
* Quienes han aportado ideas, ejemplos y pruebas.

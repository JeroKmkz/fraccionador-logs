# 📂 Fraccionador de Logs - Trivial IRC

Herramienta web para **limpiar y dividir** logs de partidas de Trivial IRC en partes manejables.

## 🎯 Características

- 🧹 **Limpieza automática** de códigos IRC (colores, negrita, cursiva, etc.)
- ✂️ **División inteligente** que corta siempre al inicio de cada pregunta
- 📦 **Descarga directa** de cada parte en `.txt` o todo junto en un `.zip`
- 🔒 **100% privado** – todo se procesa localmente en tu navegador
- 📱 **Responsive** – funciona tanto en móvil como en escritorio

## 🚀 Uso

1. **Accede a la herramienta**: [https://tu-usuario.github.io/fraccionador-logs/](https://tu-usuario.github.io/fraccionador-logs/)
2. **Sube tu archivo** `.txt` del log de la partida
3. **Indica cuántas partes** quieres generar (entre 2 y 20, por defecto 4)
4. Pulsa **“Procesar Log”**
5. **Descarga** las partes individualmente o todas juntas en un `.zip`

## 📋 Formato de Logs Soportado

La herramienta está optimizada para logs de Trivial IRC con preguntas como:

23:00:51''282 <VegaSicilia> Pregunta: 1 / 35 Base Datos Preguntas: TrivialIrc
23:00:53''098 <VegaSicilia> MEDICINA-SALUD ¿QUÉ AGENTE PATÓGENO PRODUCE LA LEPRA?
23:00:56''379 <AlaskaYoung> bacilo de hansen
23:00:59''409 <VegaSicilia> >>>ALASKAYOUNG acea


## 🔧 División Inteligente

- Detecta automáticamente las preguntas en el log  
- Divide en puntos óptimos (justo antes de cada nueva pregunta)  
- Mantiene cada pregunta y sus respuestas completas  
- Equilibra el tamaño de las partes generadas  

## 📝 Limpieza de Códigos IRC

La limpieza se aplica **siempre de forma automática**.  
Se eliminan:  
- Códigos de color (`\x03` + números)  
- Negrita `\x02`, cursiva `\x1D`, subrayado `\x1F`  
- Caracteres de control y secuencias ANSI  
- Espacios múltiples y residuos al inicio  

## 🛠️ Tecnologías

- HTML5 / CSS3 / JavaScript Vanilla  
- [JSZip](https://stuk.github.io/jszip/) para empaquetar en ZIP  
- GitHub Pages para el hosting  

## 📄 Licencia

Este proyecto es de código abierto bajo la Licencia MIT.  

## 🙏 Agradecimientos

- A la comunidad de Trivial IRC  
- A todos los que han aportado ideas y pruebas

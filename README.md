# 📂 Fraccionador de Logs - Trivial IRC

Herramienta web para dividir y limpiar logs de partidas de Trivial IRC en partes manejables.

## 🎯 Características

- ✨ **Interfaz web moderna** con drag & drop
- 🧹 **Limpieza automática** de códigos IRC (colores, formatos)
- ✂️ **División inteligente** que respeta las preguntas
- 📦 **Descarga individual** o en ZIP
- 🔒 **100% privado** - Todo el procesamiento es local en tu navegador
- 📱 **Responsive** - Funciona en móvil y escritorio

## 🚀 Uso

1. **Accede a la herramienta**: [https://tu-usuario.github.io/fraccionador-logs/](https://tu-usuario.github.io/fraccionador-logs/)
2. **Arrastra tu archivo** `.txt` o `.log` a la zona de carga
3. **Configura las opciones**:
   - Número de partes (2-20, por defecto 4)
   - Limpieza de códigos IRC (activado por defecto)
4. **Click en "Procesar Archivo"**
5. **Descarga** las partes individualmente o todas en un ZIP

## 📋 Formato de Logs Soportado

La herramienta está optimizada para logs de Trivial IRC con el siguiente formato:

```
23:00:51''282 <VegaSicilia> Pregunta: 1 / 35 Base Datos Preguntas: TrivialIrc
23:00:53''098 <VegaSicilia> MEDICINA-SALUD ¿QUÉ AGENTE PATÓGENO PRODUCE LA LEPRA?
23:00:56''379 <AlaskaYoung> bacilo de hansen
23:00:59''409 <VegaSicilia> >>>ALASKAYOUNG acea
```

## 🔧 División Inteligente

El fraccionador:
- **Detecta automáticamente** las preguntas en el log
- **Divide en los puntos óptimos** (justo antes de cada pregunta)
- **Mantiene la integridad** de cada pregunta y sus respuestas
- **Equilibra el tamaño** de cada parte

## 🛠️ Tecnologías

- HTML5 / CSS3 / JavaScript Vanilla
- [JSZip](https://stuk.github.io/jszip/) para generar archivos ZIP
- GitHub Pages para el hosting

## 📝 Limpieza de Códigos IRC

Cuando está activada, elimina:
- Códigos de color (`\x03` + números)
- Códigos de formato (negrita `\x02`, cursiva `\x1D`, subrayado `\x1F`)
- Caracteres de control
- Espacios múltiples

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Por favor:
1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto es de código abierto y está disponible bajo la Licencia MIT.

## 🙏 Agradecimientos

- A la comunidad de Trivial IRC
- A todos los que han contribuido con sugerencias y pruebas

---

Desarrollado con ❤️ para facilitar el procesamiento de logs de Trivial IRC

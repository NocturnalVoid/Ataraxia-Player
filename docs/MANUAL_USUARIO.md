# Ataraxia Player — Manual de Usuario

> Reproductor de audio de escritorio para Linux y Windows

---

## Índice

1. [Primeros pasos](#1-primeros-pasos)
2. [Interfaz principal](#2-interfaz-principal)
3. [Biblioteca musical](#3-biblioteca-musical)
4. [Reproducción](#4-reproducción)
5. [Playlists](#5-playlists)
6. [Cola de reproducción](#6-cola-de-reproducción)
7. [Favoritos](#7-favoritos)
8. [Letras sincronizadas](#8-letras-sincronizadas)
9. [Visualizador de audio](#9-visualizador-de-audio)
10. [Motor DSP y Ecualizador](#10-motor-dsp-y-ecualizador)
11. [Mini Reproductor](#11-mini-reproductor)
12. [Convertidor de formatos](#12-convertidor-de-formatos)
13. [Estadísticas](#13-estadísticas)
14. [Preferencias](#14-preferencias)
15. [Mantenimiento de la base de datos](#15-mantenimiento-de-la-base-de-datos)
16. [Atajos de teclado](#16-atajos-de-teclado)
17. [Bandeja del sistema](#17-bandeja-del-sistema)
18. [Preguntas frecuentes](#18-preguntas-frecuentes)

---

## 1. Primeros pasos

### Requisitos

- **Python 3.11 o 3.12** (en Windows, evita Python 3.13 por incompatibilidad con la librería `winsdk`; en Linux, cualquier 3.11+ funciona)
- **FFmpeg** instalado y accesible en el PATH del sistema (o configurado en Preferencias)
- Sistema operativo: Linux (X11 o Wayland) o Windows 10/11

### Instalar FFmpeg

FFmpeg no se instala con pip — es una dependencia del sistema.

- **Linux (Debian/Ubuntu):** `sudo apt install ffmpeg`
- **Linux (Fedora):** `sudo dnf install ffmpeg`
- **Linux (Arch):** `sudo pacman -S ffmpeg`
- **Windows:** descarga el ejecutable desde [ffmpeg.org/download.html](https://ffmpeg.org/download.html) y añade su carpeta al PATH del sistema, o configura la ruta manualmente en Preferencias.

### Instalar dependencias de Python (entorno virtual recomendado)

```bash
# Crear entorno virtual
python -m venv .venv

# Activarlo
source .venv/bin/activate         # Linux/macOS
.venv\Scripts\activate            # Windows

# Instalar dependencias
pip install -r requirements.txt
```

> **Si pip falla en Windows instalando `winsdk`:** lo más probable es que estés usando Python 3.13. La librería `winsdk` (necesaria para integrar Ataraxia con el widget "Now Playing" de Windows 11) aún no tiene soporte para esa versión. Instala Python 3.12 en paralelo desde [python.org](https://python.org/downloads/) y úsala con `py -3.12 -m venv .venv`. Como alternativa, puedes comentar la línea de `winsdk` en `requirements.txt`: el reproductor sigue funcionando, solo pierde la integración con SMTC.

### Ejecutar el programa

```bash
python main.py
```

También puede abrirse pasando un archivo directamente:

```bash
python main.py /ruta/a/cancion.mp3
```

### Agregar música por primera vez

1. En la pestaña **Biblioteca**, haz clic en **Agregar Carpeta**
2. Selecciona la carpeta raíz de tu colección de música
3. Ataraxia escanea todos los archivos de audio de forma automática en segundo plano
4. La biblioteca aparece organizando la música casi de inmediato; el análisis de ReplayGain y las carátulas continúan en background

---

## 2. Interfaz principal

La ventana está dividida en dos paneles por un **separador ajustable**:

```
┌─────────────────────┬────────────────────────────────┐
│  Biblioteca         │  Reproductor                   │
│  Playlists          │  Convertidor FFmpeg             │
│  Estadísticas       │  Motor DSP                     │
└─────────────────────┴────────────────────────────────┘
         Panel izquierdo       Panel derecho
```

- Arrastra el separador central para dar más espacio a cualquiera de los dos lados
- El botón **☀️ Modo Día / 🌙 Modo Noche** en la esquina superior derecha cambia el tema de la interfaz

---

## 3. Biblioteca musical

### Vistas de la biblioteca

La biblioteca se puede ver de 5 maneras diferentes usando las **pastillas de selección** encima del árbol:

| Vista | Descripción |
|-------|-------------|
| **Canciones** | Lista plana de todas las canciones, ordenadas A-Z |
| **Álbumes** | Agrupadas por álbum |
| **Artistas** | Árbol Artista → Álbum → Canción (vista por defecto) |
| **Género** | Agrupadas por género musical |
| **Año** | Agrupadas por año de lanzamiento (más reciente primero) |

### Ordenación

El menú desplegable **Ordenar** (junto a las pastillas) cambia el orden de las canciones dentro de cada grupo:
- **Ordenar: Pista** — respeta el número de pista del álbum
- **Ordenar: Nombre** — orden alfabético por título

### Buscar

Escribe en la barra de búsqueda para filtrar por título de canción, nombre de artista o álbum. Los resultados se muestran en formato Artista → Álbum para dar contexto.

Borra el texto para volver a la vista normal.

### Reproducir canciones de la biblioteca

- **Doble clic** sobre una canción para reproducirla
  - En vista **Canciones**: se añaden todas las canciones de la biblioteca a la cola
  - En vista **Álbumes/Género/Año**: la cola incluye todas las canciones del mismo grupo
  - En vista **Artistas**: la cola incluye todas las canciones del mismo álbum

### Menú contextual (clic derecho)

| Opción | Efecto |
|--------|--------|
| Agregar a Playlist → [nombre] | Añade la canción a esa playlist |
| Editar Información | Abre el editor de metadatos |
| Eliminar de la Biblioteca | Retira la canción de la BD (no borra el archivo del disco) |

### Mantenimiento de la biblioteca

- **Limpiar**: busca y elimina de la BD las rutas que ya no existen en el disco (archivos movidos o borrados)
- **Agregar Carpeta**: puede añadirse más de una carpeta; Ataraxia fusiona el contenido

---

## 4. Reproducción

### Controles del reproductor

```
[ 🎛 ]  [ ⇄ ]  [ ↺ ]  [ ⏮ ]  [ ▶ ]  [ ⏭ ]  [ 🎤 ]  [ ⛶ ]       🔊 ══════
 Visual Shuffle  Loop  Prev  Play  Next  Letras  Full        Volumen
```

| Botón | Función |
|-------|---------|
| 🎛 Visualizador | Activa/desactiva el visualizador de barras |
| ⇄ Shuffle | Activa la reproducción en orden aleatorio |
| ↺ Loop | Cicla entre: sin bucle → bucle de cola → bucle de una canción |
| ⏮ Anterior | Retrocede a la canción anterior (o reinicia si han pasado >6 s) |
| ▶/⏸ Play/Pausa | Con fade-out suave al pausar |
| ⏭ Siguiente | Avanza a la siguiente canción |
| 🎤 Letras | Muestra las letras sincronizadas (excluye el visualizador) |
| ⛶ Pantalla completa | Expande el reproductor a pantalla completa |

### Barra de progreso

- **Arrastra** para saltar a cualquier posición de la canción
- Se actualiza en tiempo real mostrando el tiempo transcurrido y el total

### Control de volumen

- **Arrastra el slider** para ajustar el volumen (0–100%)
- **Haz clic en el icono de bocina** para silenciar/restaurar
- El icono cambia según el nivel: 🔇 silenciado · 🔈 bajo · 🔊 alto

### Comportamiento del bucle

| Estado del bucle | Al presionar "Siguiente" |
|-----------------|--------------------------|
| Sin bucle | Avanza normalmente |
| Bucle de cola (↺) | Avanza normalmente, vuelve al inicio al terminar |
| Bucle de una canción (↺1) | **Se cambia a bucle de cola** (estándar de la industria) |

### Drag & Drop

Arrastra cualquier archivo de audio **sobre la portada del reproductor** para reproducirlo inmediatamente.

Formatos soportados: `.mp3` `.wav` `.flac` `.ogg` `.m4a` `.opus` `.aac` `.webm` `.mka` `.wma`

### Pantalla completa

- Presiona **F** o el botón ⛶ para activar
- En pantalla completa, la biblioteca y las pestañas se ocultan
- El cursor se oculta automáticamente tras 5 segundos de inactividad
- Mueve el ratón o presiona cualquier tecla para recuperarlo
- Presiona **Esc** para salir de pantalla completa

---

## 5. Playlists

### Crear una playlist

1. Ve a la pestaña **Playlists**
2. Haz clic en **Nueva Playlist**
3. Escribe el nombre y confirma

### Añadir canciones a una playlist

- **Desde la biblioteca:** clic derecho sobre una canción → *Agregar a Playlist* → [nombre de la playlist]

### Reproducir una playlist

- Haz clic en el nombre de la playlist para ver sus canciones
- Doble clic sobre una canción para reproducir toda la playlist desde esa posición

### Reordenar canciones

Arrastra las canciones dentro de la lista para cambiar su orden (Drag & Drop).

### Smart Playlists (automáticas)

Ataraxia genera tres playlists automáticas que se actualizan solas:

| Playlist | Contenido |
|----------|-----------|
| 🔥 Top 25 | Las 25 canciones más escuchadas |
| ✨ Recientes | Las últimas 25 canciones añadidas a la biblioteca |
| 🎲 Mix Aleatorio | 50 canciones aleatorias de toda la biblioteca |

Estas playlists no se pueden borrar pero sí se pueden exportar como M3U.

### Importar / Exportar M3U

- **Importar:** botón de importar en la barra de playlists → selecciona un archivo `.m3u`
- **Exportar:** con una playlist seleccionada, botón de exportar → elige dónde guardar

---

## 6. Cola de reproducción

La pestaña **Cola** del panel izquierdo muestra qué está sonando y qué viene a continuación. Es independiente de tus playlists guardadas: la cola se reconstruye cada vez que reproduces algo desde la biblioteca o una playlist.

### Qué ves

- **Encabezado:** contador con el formato "42 pistas en cola · pista 5 de 42"
- **Flecha ▶** junto a la canción que está sonando
- **Pista activa resaltada** en color lavanda y negrita
- Cada fila muestra título y artista

### Qué puedes hacer

- **Arrastrar y soltar** canciones para reordenar la cola (la canción activa se preserva aunque la reordenes)
- **Doble clic** sobre una canción para saltar directamente a ella
- **Clic derecho** abre un menú contextual con:
  - **Reproducir ahora** (equivale al doble clic)
  - **Quitar de la cola** (no borra de la biblioteca)
  - **Limpiar cola** (vacía todo excepto la canción actual)
- **Botón "Limpiar cola"** en el encabezado: deja solo la canción que suena en este momento

### Añadir canciones a la cola

Desde la biblioteca o cualquier playlist, clic derecho sobre una canción:
- **Reproducir a continuación** — la inserta justo después de la pista actual
- **Añadir a la cola** — la pone al final de la cola

### Persistencia

Al cerrar Ataraxia, la cola se guarda automáticamente. Cuando vuelvas a abrir, aparecerá restaurada exactamente como la dejaste (pero no se reproduce sola; tú decides cuándo retomar).

---

## 7. Favoritos

Marcar canciones como favoritas es rápido y persistente.

### Tres formas de marcar como favorita

1. **Pasa el cursor sobre la carátula** del panel del reproductor. Aparecerá un corazón en la esquina superior derecha — clic para alternar. Si la canción ya es favorita, el corazón se queda visible permanentemente (rojo relleno).
2. **Atajo Ctrl+D** mientras suena la canción.
3. **Clic derecho** sobre cualquier canción (biblioteca, playlist, cola) → "Alternar favorito".

### Ver tus favoritos

En el panel de Playlists, aparece una smart playlist llamada **Favoritos ❤** que se actualiza automáticamente con todas las canciones marcadas. Los favoritos son independientes de las playlists: una canción puede estar en 3 playlists y además ser favorita.

### Quitar de favoritos

Cualquiera de las tres formas de marcar funciona también para desmarcar (es un toggle).

---

## 8. Letras sincronizadas

### Cómo funciona

Ataraxia busca automáticamente un archivo de letras con el **mismo nombre base** que el archivo de audio en la misma carpeta.

**Ejemplo:** para `cancion.mp3` busca en orden:
1. `cancion.lrc` (letras sincronizadas por milisegundo)
2. `cancion.srt` (subtítulos de video)
3. `cancion.txt` (texto plano sin sincronización)

### Activar las letras

Haz clic en el botón **🎤** del reproductor. Las letras aparecen sobre la portada con estilo karaoke:

- La línea **activa** se muestra en blanco grande
- Las líneas **pasadas** se muestran en gris oscuro
- Las líneas **futuras** se muestran en gris claro

La vista se desplaza automáticamente para mantener la línea activa centrada.

> **Nota:** Las letras y el visualizador son mutuamente excluyentes — activar uno desactiva el otro.

### Formato LRC

Los archivos `.lrc` usan el formato estándar:

```
[00:12.50]Primera línea de la canción
[00:18.00]Segunda línea de la canción
[01:05.23]Otra línea más adelante
```

---

## 9. Visualizador de audio

### Qué muestra

El visualizador analiza el **audio real** de la canción y muestra 48 barras que representan distintas frecuencias musicales:

| Posición | Frecuencias | Qué suena ahí |
|----------|-------------|----------------|
| Barras izquierda | 0–80 Hz | Sub-bajos, bombo |
| Barras centro-izquierda | 80–250 Hz | Bajo eléctrico |
| Barras centro | 250–600 Hz | Guitarra, piano bajo |
| Barras centro-derecha | 600–1400 Hz | Voz, guitarra media |
| Barras derecha | 1400 Hz+ | Platillos, agudos |

### Cómo activarlo

Haz clic en el botón **🎛** (primera posición a la izquierda de los controles).

### Comportamiento

- Las barras suben rápido y bajan suave para un movimiento natural
- Al **pausar**, las barras caen gradualmente a cero (no se cortan de golpe)
- Durante los primeros segundos después de cambiar de canción, hay una animación de transición mientras el análisis en background termina

---

## 10. Motor DSP y Ecualizador

El **Motor DSP** está en la pestaña derecha del reproductor.

> ⚠️ Requiere FFmpeg. El DSP reprocesa el audio antes de reproducirlo, lo que puede tardar unos segundos al cambiar de pista cuando está activo.

### Ecualizador gráfico (10 bandas)

Ajusta cada frecuencia con sliders verticales:

| Banda | Frecuencia | Afecta a |
|-------|-----------|----------|
| 1 | 31 Hz | Sub-bajos |
| 2 | 62 Hz | Bajos profundos |
| 3 | 125 Hz | Bajos |
| 4 | 250 Hz | Bajos-medios |
| 5 | 500 Hz | Medios |
| 6 | 1000 Hz | Medios-altos |
| 7 | 2000 Hz | Presencia |
| 8 | 4000 Hz | Agudos |
| 9 | 8000 Hz | Agudos brillantes |
| 10 | 16000 Hz | Air |

### Pitch (velocidad y tono)

El slider de **Pitch** modifica la velocidad de reproducción:
- Valores > 1.0: más rápido y más agudo
- Valores < 1.0: más lento y más grave
- 1.0 = normal

### Reverberación

Añade efecto de eco/sala. Valores más altos = más reverberación.

### Presets

Ataraxia incluye presets predefinidos:

| Preset | Descripción |
|--------|-------------|
| Normal (Plano) | Sin modificaciones |
| Rock | Realza graves y agudos |
| Pop | Voz y medios más presentes |
| Bass Boost | Bajos potentes |
| Voz Clara | Realza la presencia vocal |
| Nightcore | Rápido y agudo |
| Slowed & Reverb | Lento con mucho eco |

### Guardar un preset personalizado

1. Ajusta el ecualizador y los efectos a tu gusto
2. Haz clic en **💾 Guardar**
3. Escribe un nombre para el preset
4. Aparecerá en la lista de presets para uso futuro

> **Auto-skip de DSP:** Si el DSP está activo, Ataraxia salta automáticamente canciones que ya tienen efectos en el título ("slowed", "reverb", "nightcore", etc.) para evitar doble procesamiento.

---

## 11. Mini Reproductor

El Mini Reproductor (Picture-in-Picture) es una ventana flotante pequeña para controlar la música sin ocupar espacio.

### Cómo activarlo

- Botón **pip** en la esquina superior derecha del reproductor
- Menú **Herramientas → Activar Mini Reproductor**
- Clic derecho en la bandeja del sistema → **Abrir Mini Reproductor**

### Funciones del Mini Reproductor

- Muestra portada, título y artista de la canción actual
- Controles de reproducción: anterior, play/pausa, siguiente
- Barra de progreso interactiva
- Botones de shuffle y loop sincronizados con el reproductor principal
- Soporte de temas claro/oscuro

### Volver al reproductor completo

Haz clic en el botón **✕** del Mini Reproductor o ciérralo — la ventana principal se restaura automáticamente.

---

## 12. Convertidor de formatos

El convertidor está en la pestaña **Convertidor FFmpeg** del panel derecho.

### Cómo convertir un archivo

1. **Seleccionar archivo:** haz clic en *Examinar Archivo* y elige el archivo de origen (video o audio)
2. **Formato de salida:** selecciona el formato destino (MP3, WAV, FLAC, AAC, OGG, OPUS)
3. **Calidad (bitrate):** solo disponible para formatos con pérdida
4. **Metadatos:** puedes editar título, artista y álbum antes de convertir (si los dejas en blanco, se heredan del archivo original)
5. **Carátula:** se detecta automáticamente del archivo de origen
6. Haz clic en **Iniciar Conversión**

### Formatos soportados

| Formato | Tipo | Notas |
|---------|------|-------|
| MP3 | Con pérdida | Compatible con todo |
| AAC | Con pérdida | Buena calidad a bajo bitrate |
| OGG | Con pérdida | Open source |
| OPUS | Con pérdida | Mejor calidad moderna |
| WAV | Sin pérdida | Archivos grandes |
| FLAC | Sin pérdida | Comprimido sin pérdida |

> **Nota:** El convertidor bloquea upscaling de lossy → lossless (ej: MP3 → FLAC). Esto no mejora la calidad y solo ocupa más espacio.

### Cancelar una conversión en curso

Haz clic en **Cancelar** durante el proceso. El archivo parcial se elimina automáticamente.

---

## 13. Estadísticas

La pestaña **Estadísticas** muestra las 10 canciones más escuchadas con:
- Artista
- Álbum
- Título
- Número de reproducciones

> Una reproducción se cuenta al alcanzar el **50% del tiempo total** de la canción.

Usa el botón **Actualizar** para refrescar los datos.

---

## 14. Preferencias

Ve a **Herramientas → Preferencias** para configurar el programa.

### Pestaña Sistema

**Configuración de FFmpeg:**
- **Ruta de FFmpeg:** si `ffmpeg` no está en el PATH del sistema, escribe la ruta completa al ejecutable (ej. `/usr/bin/ffmpeg` o `C:\ffmpeg\bin\ffmpeg.exe`)

**Motor de Audio Avanzado:**
- **ReplayGain:** nivela el volumen de todas las canciones automáticamente. Se calcula en background al añadir música y no consume procesador durante la reproducción
- **Crossfade:** activa la transición suave de 5 segundos entre canciones

**Metadatos y Red:**
- **Autocompletado de carátulas:** descarga carátulas de Internet (iTunes por defecto) para canciones que no tienen imagen incrustada
- **URL de API:** puedes usar cualquier API REST que devuelva JSON con una imagen. El comodín `{query}` se reemplaza por `Artista Titulo`

### Pestaña Comportamiento

**Restablecer advertencias:** si en algún momento marcaste "No volver a preguntar" en un diálogo de confirmación (al cerrar, eliminar canciones, etc.), este botón restaura todas esas preferencias para que Ataraxia vuelva a preguntar.

---

## 15. Mantenimiento de la base de datos

Ataraxia almacena tu biblioteca, playlists, favoritos y estadísticas en una base de datos SQLite. La pestaña **Mantenimiento** dentro de **Preferencias** te da control directo sobre ese archivo.

### Estado de la Base de Datos

En la parte superior verás información útil:
- **Versión de schema:** la versión actual de la estructura de la BD
- **Tamaño del archivo:** cuánto espacio ocupa
- **Conteos:** cuántas canciones y playlists tienes indexadas
- **Último mantenimiento:** cuándo se hizo la última operación

### Operaciones disponibles

**Optimizar consultas (ANALYZE)** — Recalcula las estadísticas internas que SQLite usa para decidir cómo ejecutar las búsquedas. Es muy rápido (segundos) y se recomienda hacerlo cada mes o cuando notes lentitud en las búsquedas.

**Compactar archivo (VACUUM)** — Recupera el espacio que SQLite no devuelve automáticamente al borrar canciones o playlists. Puede tardar varios segundos en bibliotecas grandes — durante ese tiempo la ventana no responde. Es útil hacerlo después de borrar muchas canciones o cada 6 meses si tu BD ha crecido mucho.

**Verificar integridad** — Comprueba que el archivo no tenga corrupción. Si reporta un problema, restaura un respaldo reciente.

### Respaldo y restauración

**Exportar respaldo…** — Guarda una copia exacta de tu BD en el lugar que elijas. El nombre por defecto incluye la fecha y hora. Recomendamos hacer respaldos periódicos, especialmente antes de actualizaciones grandes del programa.

**Restaurar respaldo…** — Reemplaza tu BD actual con un archivo de respaldo. Antes de sobrescribir, Ataraxia crea automáticamente una copia de seguridad con sufijo `.pre-restore`. Después de restaurar, **debes reiniciar la aplicación** para que los cambios surtan efecto.

> **Atención:** restaurar un respaldo es una operación destructiva. La BD actual se reemplazará por completo. Si solo quieres recuperar una playlist específica, considera primero copiar el respaldo a una ubicación temporal e inspeccionarlo con una herramienta como DB Browser for SQLite.

### Sobre los archivos `.db-wal` y `.db-shm`

Junto al archivo `ataraxia.db` verás dos archivos adicionales: `ataraxia.db-wal` y `ataraxia.db-shm`. Son temporales del modo WAL (Write-Ahead Logging) de SQLite, que mejora el rendimiento cuando lecturas y escrituras ocurren al mismo tiempo. **Es normal verlos** — no los borres mientras Ataraxia esté corriendo. Si los encuentras después de cerrar, también está bien dejarlos: SQLite los gestiona automáticamente.

---

## 16. Atajos de teclado

| Atajo | Función |
|-------|---------|
| `Espacio` | Play / Pausa |
| `Ctrl+D` | Alternar favorito de la canción actual |
| `F` | Pantalla completa |
| `Esc` | Salir de pantalla completa |
| `→` | Avanzar 10 segundos |
| `←` | Retroceder 10 segundos |

---

## 17. Bandeja del sistema

Al cerrar la ventana principal, Ataraxia puede seguir funcionando en la bandeja del sistema.

### Opciones al cerrar

- **Segundo plano:** minimiza a la bandeja, la música sigue sonando
- **Cerrar por completo:** termina el programa

Puedes marcar "No volver a preguntar" para que Ataraxia recuerde tu elección.

### Menú de la bandeja

Haz **clic derecho** en el icono de la bandeja para acceder a:
- Abrir el reproductor completo
- Abrir el Mini Reproductor
- Controles de reproducción: ⏮ Anterior · ▶/⏸ Play/Pausa · ⏭ Siguiente
- Cerrar Ataraxia completamente

**Doble clic** en el icono de la bandeja restaura la ventana principal.

---

## 18. Preguntas frecuentes

**¿Por qué no escucho audio al reproducir?**  
Verifica que el volumen no esté en 0 y que el dispositivo de salida de audio esté activo en tu sistema.

**¿Por qué el DSP tarda unos segundos al cambiar de canción?**  
El Motor DSP usa FFmpeg para preprocesar el audio antes de reproducirlo. Esto es normal; el archivo temporal se genera cada vez que cambia la pista.

**¿El visualizador funciona sin FFmpeg?**  
El visualizador incluye un modo de animación de respaldo mientras analiza el audio. Si FFmpeg no está disponible, el análisis fallará silenciosamente y el visualizador usará la animación de respaldo indefinidamente.

**¿Por qué el contador de reproducciones no sube?**  
El contador solo aumenta cuando la canción llega al 50% de su duración total. Canciones que se saltan antes de la mitad no cuentan.

**¿Cómo actualizo los metadatos de una canción?**  
Clic derecho sobre la canción en la biblioteca → *Editar Información*. Los cambios se guardan en el archivo físico de audio y en la base de datos.

**¿Puedo usar múltiples carpetas de música?**  
Sí. Puedes añadir tantas carpetas como quieras con el botón *Agregar Carpeta*. Todas se fusionan en la misma biblioteca.

**¿Dónde se guarda la base de datos?**  
- Linux: `~/.local/share/AtaraxiaPlayer/ataraxia.db`
- Windows: `%APPDATA%\AtaraxiaPlayer\ataraxia.db`

**¿Qué pasa si muevo o renombro archivos de música?**  
Usa el botón **Limpiar** en la biblioteca. Ataraxia verificará qué archivos ya no existen y los eliminará de la base de datos. Luego añade la nueva ubicación con *Agregar Carpeta*.

**¿Puedo usar Ataraxia sin conexión a Internet?**  
Sí completamente. La descarga de carátulas es opcional y debe habilitarse manualmente en Preferencias.

**¿Por qué aparece "Instancia ya en ejecución" al abrir el programa?**  
Ataraxia solo permite una ventana a la vez. Si ya hay una instancia abierta (incluso minimizada en la bandeja), la nueva se cierra y envía el archivo de audio a la instancia existente.

**`pip install -r requirements.txt` falla en Windows con un error de `winsdk`**  
Lo más probable es que estés usando Python 3.13. La librería `winsdk` (que da integración con el widget "Now Playing" de Windows 11) aún no tiene wheels para esa versión y pip intenta compilarla desde fuente, lo que falla sin Visual Studio Build Tools. Solución: instala Python 3.12 desde [python.org](https://python.org/downloads/) y úsala con `py -3.12 -m venv .venv`. En Linux este problema no existe — usa cualquier Python 3.11+.

**¿Funciona en Wayland (GNOME, KDE, Sway)?**  
Sí, incluyendo el icono correcto en la barra de tareas. Si la primera vez que ejecutas Ataraxia en Wayland el icono aparece genérico, cierra sesión y vuelve a entrar — el compositor necesita releer el archivo `.desktop` que Ataraxia instala automáticamente en `~/.local/share/applications/`.

**¿Cómo hago respaldo manual de toda mi biblioteca?**  
Usa **Preferencias → Mantenimiento → Exportar respaldo…**. Esto guarda un archivo `.db` con toda tu biblioteca, playlists, favoritos y estadísticas. Si quieres respaldar también las carátulas y letras cacheadas, copia adicionalmente las carpetas `~/.cache/AtaraxiaPlayer/` (Linux) o `%LOCALAPPDATA%\AtaraxiaPlayer\cache\` (Windows).

**¿Por qué hay archivos `ataraxia.db-wal` y `ataraxia.db-shm` junto a la base de datos?**  
Son archivos temporales del modo WAL de SQLite que mejora el rendimiento. Es normal verlos y no debes borrarlos mientras Ataraxia está abierto. Ver más detalles en la sección de Mantenimiento.

---

*Ataraxia Player — Desktop Audio Manager*  
*Desarrollado con Python & PyQt6*

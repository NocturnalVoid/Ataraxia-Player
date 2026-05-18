# Ataraxia Player — Documentación Técnica

> Python 3.11 · PyQt6 · SQLite · FFmpeg  
> Patrón de arquitectura: **MVC** (Model-View-Controller)

---

## Índice

1. [Visión general](#1-visión-general)
2. [Árbol de archivos](#2-árbol-de-archivos)
3. [Capa de Modelos](#3-capa-de-modelos)
4. [Capa de Vistas](#4-capa-de-vistas)
5. [Capa de Controladores](#5-capa-de-controladores)
6. [Esquema de la base de datos](#6-esquema-de-la-base-de-datos)
7. [Flujos de datos principales](#7-flujos-de-datos-principales)
8. [Señales y conexiones clave](#8-señales-y-conexiones-clave)
9. [Dependencias y requisitos](#9-dependencias-y-requisitos)
10. [Guía para extender el proyecto](#10-guía-para-extender-el-proyecto)

---

## 1. Visión general

Ataraxia Player es un **reproductor de audio de escritorio** multiplataforma (Linux/Windows) con las siguientes capacidades principales:

| Módulo | Descripción |
|--------|-------------|
| Reproducción | Motor dual `QMediaPlayer` + crossfade de 5 s |
| Biblioteca | SQLite con vistas por Canciones, Álbumes, Artistas, Género y Año |
| Motor DSP | Ecualizador gráfico 10 bandas, pitch y reverberación vía FFmpeg |
| Visualizador | Análisis multi-banda real de audio (5 bandas IIR, 48 barras, 60 fps) |
| Letras | Soporte `.lrc` (karaoke), `.srt` y `.txt` con sincronización por ms |
| Playlists | CRUD completo + Smart Playlists + importación/exportación M3U |
| Convertidor | FFmpeg: video/audio → MP3/FLAC/WAV/AAC/OGG/OPUS con carátulas |
| OS nativo | MPRIS2 (Linux) · SMTC (Windows) · Bandeja del sistema |
| Mini Player | Ventana flotante Picture-in-Picture totalmente sincronizada |

---

## 2. Árbol de archivos

```
reproductor_musica/
│
├── main.py                          Punto de entrada — crea QApplication y MainController
├── requirements.txt                 Dependencias pip
│
├── assets/
│   ├── dark_theme/                  Iconos SVG para modo oscuro
│   ├── light_theme/                 Iconos SVG para modo claro
│   ├── library/                     Iconos SVG de la interfaz de biblioteca
│   ├── icons/                       Icono principal de la app (.ico/.png/.svg)
│   └── covers_cache/                Carátulas descargadas de la API
│
└── src/
    ├── controllers/
    │   ├── main_controller.py       Orquestador central: conecta modelos ↔ vistas
    │   ├── playback_controller.py   Motor de reproducción: cola, DSP, crossfade, lerp
    │   └── conversion_controller.py Controla el hilo de conversión FFmpeg
    │
    ├── models/
    │   ├── database_manager.py      Todas las consultas SQLite (CRUD + vistas de biblioteca)
    │   ├── metadata_manager.py      Extracción de tags (mutagen) + escaneo a BD
    │   ├── playlist.py              CRUD de playlists sobre DatabaseManager
    │   ├── lyrics_parser.py         Parser LRC/SRT/TXT con búsqueda binaria (bisect)
    │   ├── m3u_manager.py           Importación/exportación de archivos .m3u
    │   ├── media_converter.py       Worker thread de FFmpeg para conversión
    │   ├── mpris_manager.py         Integración MPRIS2 para Linux (D-Bus)
    │   └── smtc_manager.py          Integración SMTC para Windows
    │
    ├── views/
    │   ├── main_window.py           Ventana principal: splitter, pestañas, menú, bandeja
    │   ├── player_panel.py          Panel del reproductor: controles, portada, letras, EQ
    │   ├── library_panel.py         Biblioteca con 5 vistas y pills de selección
    │   ├── playlist_panel.py        Gestión de playlists con drag & drop
    │   ├── mini_player.py           Ventana flotante Picture-in-Picture
    │   ├── visualizer_widget.py     Visualizador espectral multi-banda (QPainter + QThread)
    │   ├── dsp_panel.py             Ecualizador gráfico 10 bandas + presets
    │   ├── converter_panel.py       Interfaz del convertidor de formatos
    │   ├── stats_panel.py           Tabla de canciones más escuchadas
    │   ├── preferences_dialog.py    Diálogo de preferencias (FFmpeg, red, comportamiento)
    │   └── metadata_dialog.py       Diálogo de edición de metadatos de pista
    │
    └── utils/
        └── single_instance.py       Control de instancia única vía socket IPC local
```

---

## 3. Capa de Modelos

### `DatabaseManager` (`database_manager.py`)

Gestiona **todas** las operaciones SQLite. No contiene lógica de negocio — solo consultas.

```python
# Agrupaciones disponibles para la biblioteca
get_library_tree()      → dict  # {artist: {album: [(track_n, title, filepath)]}}
get_songs_flat()        → list  # [(track_n, title, filepath)]
get_songs_by_album()    → dict  # {album: [(track_n, title, filepath)]}
get_songs_by_genre()    → dict  # {genre: [(track_n, title, filepath)]}
get_songs_by_year()     → dict  # {year_str: [(track_n, title, filepath)]}

# Gestión de canciones
remove_song(filepath)
update_song_metadata(filepath, title, artist, album, track_number)
increment_play_count(filepath)
get_all_filepaths() → list[str]

# ReplayGain
update_replay_gain(filepath, gain_db)
get_replay_gain(filepath) → float

# Playlists
delete_playlist(playlist_id)
remove_song_from_playlist(playlist_id, record_id)
update_playlist_order(playlist_id, new_paths)

# Smart Playlists
get_top_played_songs(limit=25) → list
get_recently_added(limit=25)   → list
get_random_mix(limit=50)       → list
```

### `MetadataManager` (`metadata_manager.py`)

Responsable de leer y escribir metadatos en los **archivos físicos** de audio usando `mutagen`.

```python
# Helper interno — lee TODOS los tags en una sola pasada
_read_audio_tags(filepath) → dict | None
# Retorna: {title, artist, album, tracknumber, track_num, duration, genre, year}

# API pública
extract_metadata(filepath)  → dict   # para la UI y el OS
extract_cover_art(filepath) → str    # ruta a la imagen extraída (o default)
save_metadata(filepath, new_data)    # escribe en el archivo físico
scan_directory_to_db(dir, db_manager)  # escaneo masivo en hilo
get_library_tree(db_manager) → dict  # consulta para la vista Artistas
fetch_and_embed_cover(filepath, title, artist, api_url) → bool
```

**Formatos de carátula soportados:**  
MP3 (ID3 APIC) · FLAC (Picture) · OGG/OPUS (Base64 `metadata_block_picture`) · M4A/MP4 (`covr`)

### `LyricsParser` (`lyrics_parser.py`)

Carga automáticamente el archivo de letras con el mismo nombre base que el audio.

- **Prioridad:** `.lrc` → `.srt` → `.txt`
- `get_state_at_time(ms)` usa `bisect.bisect_right` → O(log n) en lugar de O(n)
- Retorna `(lines, current_index, is_synced)` listo para renderizado karaoke

### `AudioAnalyzer` (`visualizer_widget.py`)

`QThread` que analiza el audio en background mediante FFmpeg + filtros IIR en cascada.

```
SAMPLE_RATE = 4000 Hz   WINDOW_MS = 40 ms   → 25 frames/segundo de resolución

Bandas de frecuencia (5):
  Band 0:    0 –  80 Hz  (sub-bajos / bombo)
  Band 1:   80 – 250 Hz  (bajos / bajo eléctrico)
  Band 2:  250 – 600 Hz  (medios-bajos / guitarra)
  Band 3:  600 – 1400 Hz (medios / voz)
  Band 4: 1400 Hz +      (agudos / platillos)

Filtro IIR 1-polo (lowpass) con alpha = dt / (dt + 1/(2π·fc))
Bandas como diferencias de lowpass en cascada: band_n = LP(fc_n) − LP(fc_{n-1})
Normalización: p90 de energía = 0.82  (preserva dinámica interna)
```

### `Playlist` (`playlist.py`)

Thin wrapper sobre `DatabaseManager` para las operaciones de playlist con lógica de orden.

---

## 4. Capa de Vistas

Las vistas **no tienen lógica de negocio** — solo emiten señales y renderizan datos recibidos.

### `PlayerPanel` (`player_panel.py`)

Panel central del reproductor. Contiene:

| Elemento | Descripción |
|----------|-------------|
| `lbl_cover` | Portada escalada (400 px normal, 700 px fullscreen) |
| `text_lyrics` | Overlay de letras con estilo karaoke (HTML rico) |
| `visualizer` | `VisualizerWidget` en overlay (mutuamente excluyente con letras) |
| `btn_visualizer` | Ubicado en `left_widget` (espejo del volumen a la derecha) |
| `btn_shuffle/loop` | Estados persistentes; loop-one → loop-all al saltar manualmente |
| `set_loop_state(mode)` | Actualiza el botón **sin** emitir `loop_mode_changed` (evita ciclo) |
| `set_track(filepath)` | Dispara `visualizer.load_track()` en el cambio de pista |

**Señales emitidas:** `play_toggled`, `next_clicked`, `prev_clicked`, `slider_moved`,  
`volume_changed`, `shuffle_mode_changed`, `loop_mode_changed`, `fullscreen_requested`,  
`file_dropped`, `mini_player_requested`, `track_index_changed`

### `VisualizerWidget` (`visualizer_widget.py`)

Hereda `QWidget`, dibuja con `QPainter` a 60 fps.

```
48 barras — distribución por banda: [5, 9, 10, 14, 10]
MAX_BAR_W = 8 px   GAP = 4 px   (delgadas con hueco visible)

Por barra (fijos con semilla aleatoria):
  _bar_to_band[i]       → índice de banda (0-4)
  _bar_frame_offset[i]  → ±3 frames de offset temporal (±120 ms)
  _bar_amplitude[i]     → multiplicador 0.75–1.25
  _phases[i], _speeds[i] → variación senoidal ±12 % × energía_real
```

Modo `fallback` activo mientras el `AudioAnalyzer` procesa.

### `LibraryPanel` (`library_panel.py`)

```
5 pills de vista: Canciones | Álbumes | Artistas | Género | Año

populate_library(data, mode)  — entrada unificada del controlador
populate_tree(data)           — compatibilidad con resultados de búsqueda

Renderizadores internos:
  _build_artists(data)         — 2 niveles: artista → álbum → canción
  _build_grouped(data, mode)   — 1 nivel: grupo → canción (álbumes/género/año)
  _build_flat(songs)           — 0 niveles: canciones en raíz

highlight_song(filepath)       — búsqueda recursiva O(n) → expande árbol
```

### `MainWindow` (`main_window.py`)

Ventana principal con `QSplitter` horizontal: `left_tabs` (300 px) · `right_tabs` (650 px).

- **Pestañas izquierda:** Biblioteca · Playlists · Estadísticas
- **Pestañas derecha:** Reproductor · Convertidor FFmpeg · Motor DSP
- **Comportamiento al cerrar:** minimizar a bandeja o salir (con opción "no volver a preguntar")
- **Fullscreen:** oculta pestañas, oculta cursor tras 5 s de inactividad

---

## 5. Capa de Controladores

### `MainController` (`main_controller.py`)

Orquestador central. Se construye en el `main()` y vive durante toda la sesión.

**Orden de inicialización `__init__`:**
1. Instanciar modelos (DB, Metadata, Lyrics, Playlist)
2. Instanciar vistas base
3. Ensamblar `MainWindow`
4. Crear `PlaybackController` y `ConversionController`
5. Conectar señales de bandeja, drag & drop, OS media
6. Conectar señales globales de ventana principal
7. Integrar `MiniPlayer`
8. Cargar biblioteca y playlists desde BD
9. Restaurar sesión guardada (cola, índice, playlist activa)

**Métodos de biblioteca:**
```python
_on_library_view_changed(mode)  # despacha la consulta según el modo de vista
_load_library_from_db()         # recarga el modo activo actual
_handle_library_search(query)   # siempre muestra en formato artistas para contexto
```

**Hilos background que gestiona:**
- `DatabaseScannerThread` — escaneo de carpeta + ReplayGain + carátulas API
- `CoverDownloaderThread` — descarga JIT de carátula al dar play
- `AudioAnalyzer` (gestionado dentro de `VisualizerWidget`)

### `PlaybackController` (`playback_controller.py`)

Motor de reproducción. Hereda `QObject`.

**Arquitectura de doble motor (crossfade):**
```
players[0] ──── audio_output[0] ──┐
                                    ├── active_idx alterna entre 0 y 1
players[1] ──── audio_output[1] ──┘

Crossfade: active_idx cambia 5 s antes del fin
  fade_out_vol: 1.0 → 0.0  (decrece 0.02 cada 100 ms)
  fade_in_vol:  0.0 → 1.0  (crece  0.02 cada 100 ms)
  _cancel_crossfade() restaura el estado al saltar manualmente
```

**Sistema de shuffle (baraja matemática):**
```python
_generate_shuffle_sequence(first_index)
# Genera permutación del índice actual + resto barajado
# Garantiza que la canción actual sea la primera de la baraja
```

**ReplayGain:**
```python
_calculate_replaygain_volume(filepath) → float
# gain_db = DB.get_replay_gain(filepath)
# multiplier = 10^(gain_db / 20)
# vol = clamp(base_vol * multiplier, 0.0, 1.0)
```

**Limpieza de archivos temporales DSP:**
```python
# Antes de cargar cada pista:
if _dsp_temp_path and os.path.exists(_dsp_temp_path):
    os.remove(_dsp_temp_path)
```

**Loop-one → loop-all al saltar:**
```python
# Al inicio de play_next() y play_prev():
if not is_crossfade_trigger and self.loop_mode == 2:
    self.loop_mode = 1
    self.loop_mode_override.emit(1)  # actualiza la UI
```

---

## 6. Esquema de la base de datos

```sql
-- Tabla de artistas
artists (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT UNIQUE NOT NULL
)

-- Tabla de álbumes
albums (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    cover_path  TEXT,
    artist_id   INTEGER REFERENCES artists(id)
)

-- Tabla de canciones
songs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT    NOT NULL,
    filepath        TEXT    UNIQUE NOT NULL,
    duration        INTEGER DEFAULT 0,    -- segundos
    track_number    INTEGER DEFAULT 0,
    genre           TEXT    DEFAULT '',
    year            INTEGER DEFAULT 0,
    play_count      INTEGER DEFAULT 0,
    replay_gain     REAL    DEFAULT 0.0,  -- dB de ganancia calculada
    album_id        INTEGER REFERENCES albums(id)
)

-- Playlists manuales
playlists (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
)

-- Relación playlist ↔ canción (permite duplicados)
playlist_songs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,  -- id_registro único
    playlist_id INTEGER REFERENCES playlists(id),
    song_id     INTEGER REFERENCES songs(id),
    sort_order  INTEGER
)

-- Configuración miscelánea (clave-valor)
config (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
)
```

**Ubicación del archivo `.db`:**
- Linux: `~/.local/share/AtaraxiaPlayer/ataraxia.db`
- Windows: `%APPDATA%\AtaraxiaPlayer\ataraxia.db`

**Smart Playlists (IDs virtuales, sin fila en BD):**
- `-1` → Top 25 más escuchadas
- `-2` → Añadidas recientemente (25)
- `-3` → Mezcla aleatoria (50)

---

## 7. Flujos de datos principales

### Carga de una pista

```
Usuario doble-clic en biblioteca
    └─→ LibraryPanel.track_selected.emit(queue, index)
        └─→ MainController._play_library_queue(queue, index)
            └─→ PlaybackController.play_queue(queue, index)
                └─→ PlaybackController.load_track(filepath)
                    ├─→ MetadataManager.extract_metadata()  → UI update
                    ├─→ MetadataManager.extract_cover_art() → portada
                    ├─→ LyricsParser.load_file()            → letras
                    ├─→ PlayerPanel.set_track()             → AudioAnalyzer.start()
                    ├─→ DSP._generate_experimental_track()  → FFmpeg WAV temporal
                    └─→ QMediaPlayer.setSource() + play()
```

### Escaneo de biblioteca

```
Usuario click "Agregar Carpeta"
    └─→ LibraryPanel.add_folder_requested.emit(folder)
        └─→ MainController._start_scanning(folder)
            └─→ DatabaseScannerThread.start()
                ├─→ [1] MetadataManager.scan_directory_to_db()  → canciones en BD
                │       emit scan_success → UI actualiza biblioteca
                ├─→ [2] Por cada archivo:
                │       ├─→ fetch_and_embed_cover() si auto_cover activo
                │       └─→ FFmpeg ebur128 → update_replay_gain() si gain == 0.0
                └─→ emit scan_success → UI actualiza portadas
```

### Cambio de vista de biblioteca

```
Usuario click pill "Álbumes"
    └─→ LibraryPanel._on_pill_clicked("albums")
        └─→ LibraryPanel.library_view_requested.emit("albums")
            └─→ MainController._on_library_view_changed("albums")
                └─→ DatabaseManager.get_songs_by_album() → dict
                    └─→ LibraryPanel.populate_library(data, "albums")
                        └─→ LibraryPanel._build_grouped(data, "albums")
```

---

## 8. Señales y conexiones clave

### Señales de `PlaybackController`

| Señal | Tipo | Descripción |
|-------|------|-------------|
| `track_played_halfway` | `str` | Filepath al llegar al 50% → incrementa `play_count` |
| `metadata_ready_for_os` | `str,str,str,str` | title, artist, album, cover → MPRIS/SMTC |
| `loop_mode_override` | `int` | Nuevo modo de bucle impuesto por el controlador |

### Señales de `PlayerPanel`

| Señal | Descripción |
|-------|-------------|
| `play_toggled` | Play/Pause |
| `next_clicked` / `prev_clicked` | Navegación |
| `slider_moved(int)` | Seek en segundos |
| `volume_changed(int)` | Valor 0–100 |
| `shuffle_mode_changed(bool)` | Estado del shuffle |
| `loop_mode_changed(int)` | 0=sin bucle, 1=cola, 2=una pista |
| `track_index_changed(int)` | Para resaltado visual en lista |
| `file_dropped(str)` | Drag & drop de archivo sobre la portada |
| `mini_player_requested` | Activa el Picture-in-Picture |

### Persistencia de sesión (`QSettings`)

Claves guardadas al cerrar:

| Clave | Tipo | Descripción |
|-------|------|-------------|
| `saved_queue` | `list[str]` | Cola de reproducción actual |
| `saved_index` | `int` | Índice de la pista actual |
| `active_playlist_id` | `int` | Playlist activa (-1 = biblioteca) |
| `dark_mode` | `bool` | Tema oscuro/claro |
| `ffmpeg_path` | `str` | Ruta al ejecutable de FFmpeg |
| `enable_crossfade` | `bool` | Crossfade habilitado |
| `enable_normalization` | `bool` | ReplayGain habilitado |
| `enable_auto_cover` | `bool` | Descarga automática de carátulas |
| `cover_api_url` | `str` | URL de la API REST con `{query}` |
| `custom_dsp_presets` | `str(JSON)` | Presets de EQ personalizados |
| `comportamiento_cerrar` | `str` | `"bandeja"` o `"cerrar"` |

---

## 9. Dependencias y requisitos

### Python

```
Python >= 3.11   (se usa la sintaxis de type hint dict | None)
PyQt6 >= 6.4.0
mutagen >= 1.46.0
requests         (descarga de carátulas; no está en requirements.txt — agregar si se usa auto-cover)
winsdk           (solo Windows, para SMTC)
```

### Herramientas externas

| Herramienta | Uso | Obligatorio |
|-------------|-----|-------------|
| `ffmpeg` | DSP, conversión, análisis de audio, ReplayGain | Sí para DSP/Visualizador |
| `ffprobe` | Duración del archivo (en `ConversionWorker`) | Sí para Convertidor |

### Assets requeridos

```
assets/dark_theme/   fullscreen.svg, loop.svg, loop_one.svg, lyrics.svg,
                     moon.svg, next.svg, pause.svg, pip.svg, play.svg,
                     prev.svg, shuffle.svg, sun.svg, volume_*.svg,
                     visualizer.svg

assets/light_theme/  (mismos nombres)

assets/library/      album.svg, artist.svg, behavior.svg, cancel.svg,
                     dice.svg, edit.svg, equalizer.svg, fire.svg, folder.svg,
                     gear.svg, open_folder.svg, playlist.svg, plus.svg,
                     rocket.svg, search.svg, song_dark.svg, song_light.svg,
                     sparkles.svg, stats.svg, stats_play.svg, trash.svg, trophy_*.svg

assets/icons/        ataraxia.ico, ataraxia.png, ataraxia.svg
assets/              default_audio_icon.png
```

---

## 10. Guía para extender el proyecto

### Agregar una nueva vista de biblioteca

1. **`database_manager.py`** — añadir `get_songs_by_X() → dict`
2. **`library_panel.py`** — añadir el modo a `views` en `_setup_ui()` y manejar en `_build_tree()`
3. **`main_controller.py`** — añadir el `elif mode == VIEW_X` en `_on_library_view_changed()`

### Agregar un nuevo formato de audio

1. **`metadata_manager.py`** — agregar extensión a `supported_formats`
2. **`main_controller.py`** — agregar a `valid_exts` en `_start_scanning()` y `valid_extensions` en `_play_dropped_file()`
3. **`player_panel.py`** — agregar a `valid_exts` en `dragEnterEvent()`

### Agregar un nuevo efecto DSP

1. **`dsp_panel.py`** — añadir control de UI en `_setup_ui()`, incluirlo en `_emit_settings()`
2. **`playback_controller.py`** — leer el nuevo parámetro en `current_dsp_settings` y pasarlo a `_generate_experimental_track()`
3. **`_generate_experimental_track()`** — añadir el filtro FFmpeg correspondiente en la cadena `filtros`

### Agregar una nueva Smart Playlist

1. **`database_manager.py`** — implementar la consulta SQL
2. **`main_controller.py`** — asignarle un ID virtual negativo (ej. `-4`) en `_load_playlist_songs()`
3. **`playlist_panel.py`** — referenciarla en el panel de playlists

### Agregar integración con un nuevo sistema operativo

Crear una nueva clase en `src/models/` que exponga las señales:
- `play_pause_requested`
- `next_requested`
- `prev_requested`
- `update_status(is_playing)`
- `update_metadata(title, artist, album, cover_path)`

Registrarla en `main_controller.py` dentro del bloque `elif sys.platform == ...` del paso 6.

---

*Documentación generada para la versión de desarrollo de Ataraxia Player.*

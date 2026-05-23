# -*- coding: utf-8 -*-
"""
LyricsApiClient — cliente de descarga de letras con caché LRU.

Fuente actual: lrclib.net (https://lrclib.net/docs)
  · API pública sin autenticación
  · Devuelve LRC sincronizado cuando está disponible, con fallback a texto plano
  · Open source, comunidad similar a MusicBrainz

Caché
─────
Ubicación:
    Linux   : ~/.cache/AtaraxiaPlayer/lyrics/
    Windows : %LOCALAPPDATA%\\AtaraxiaPlayer\\cache\\lyrics\\

Política:
  · Máximo MAX_CACHE_ENTRIES (200) archivos .lrc
  · Al superar el tope, se eliminan los menos usados recientemente (LRU por mtime)
  · Marcadores .notfound para canciones sin letras: válidos por NOTFOUND_TTL_DAYS
    (30 días), luego se reintenta automáticamente por si subieron letras nuevas

Identificador de cache: sha1("artist_lower::title_lower") → hash.lrc / hash.notfound
  · Insensible a mayúsculas y acentos
  · Evita colisiones entre canciones homónimas de distintos artistas
"""
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from src.utils.logger import get_logger

log = get_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Configuración (centralizada para que sea trivial cambiar proveedor)
# ══════════════════════════════════════════════════════════════════════════

LRCLIB_URL       = "https://lrclib.net/api/get"
USER_AGENT       = "AtaraxiaPlayer/1.0 (https://github.com/; open-source music player)"
REQUEST_TIMEOUT  = 5  # segundos

MAX_CACHE_ENTRIES = 200
NOTFOUND_TTL_DAYS = 30


# ══════════════════════════════════════════════════════════════════════════
# Resultado tipado para simplificar consumo
# ══════════════════════════════════════════════════════════════════════════

class LyricsResult:
    """Resultado de una petición de letras."""
    __slots__ = ("status", "content", "is_synced", "source")

    # Estados posibles
    FOUND     = "found"       # Se obtuvieron letras (content lleno)
    NOT_FOUND = "not_found"   # La API confirmó que no existen letras
    ERROR     = "error"       # Fallo de red, timeout, etc.

    def __init__(self, status: str, content: str = "", is_synced: bool = False, source: str = ""):
        self.status    = status
        self.content   = content      # texto LRC o texto plano
        self.is_synced = is_synced
        self.source    = source       # "cache" o "lrclib" o ""


# ══════════════════════════════════════════════════════════════════════════
# Cliente principal
# ══════════════════════════════════════════════════════════════════════════

class LyricsApiClient:

    def __init__(self):
        self.cache_dir = self._resolve_cache_dir()
        os.makedirs(self.cache_dir, exist_ok=True)

    # ── Resolución del directorio de caché ────────────────────────────────

    def _resolve_cache_dir(self) -> str:
        app_name = "AtaraxiaPlayer"
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
            return os.path.join(base, app_name, "cache", "lyrics")
        else:
            base = os.environ.get(
                "XDG_CACHE_HOME",
                os.path.join(os.path.expanduser("~"), ".cache")
            )
            return os.path.join(base, app_name, "lyrics")

    # ── Hash identificador ────────────────────────────────────────────────

    def _key(self, title: str, artist: str) -> str:
        """Hash canónico, insensible a mayúsculas/espacios laterales."""
        raw = f"{artist.strip().lower()}::{title.strip().lower()}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _lrc_path(self, key: str) -> str:
        return os.path.join(self.cache_dir, f"{key}.lrc")

    def _notfound_path(self, key: str) -> str:
        return os.path.join(self.cache_dir, f"{key}.notfound")

    # ── Lookup en caché ───────────────────────────────────────────────────

    def _check_cache(self, key: str) -> LyricsResult | None:
        """
        Revisa si hay resultado cacheado para esta pista.
        Retorna LyricsResult si lo hay (FOUND o NOT_FOUND vigente), None si no.
        """
        lrc_path = self._lrc_path(key)
        nf_path  = self._notfound_path(key)

        # 1. Letras cacheadas
        if os.path.exists(lrc_path):
            try:
                with open(lrc_path, "r", encoding="utf-8") as fh:
                    content = fh.read()
                # Tocar mtime para actualizar la posición LRU
                os.utime(lrc_path, None)
                is_synced = "[" in content and "]" in content.split("\n", 1)[0]
                return LyricsResult(LyricsResult.FOUND, content, is_synced, "cache")
            except OSError:
                pass

        # 2. Marcador de "no existe", revisar si sigue vigente
        if os.path.exists(nf_path):
            age_days = (time.time() - os.path.getmtime(nf_path)) / 86400
            if age_days < NOTFOUND_TTL_DAYS:
                return LyricsResult(LyricsResult.NOT_FOUND, source="cache")
            else:
                # Expirado: lo borramos y se reintentará contra la API
                try: os.remove(nf_path)
                except OSError: pass

        return None

    # ── Fetch a la API ────────────────────────────────────────────────────

    def _fetch_lrclib(self, title: str, artist: str, album: str = "",
                      duration: int = 0) -> LyricsResult:
        """
        Pide letras a lrclib.net.
        Retorna LyricsResult sin escribir en caché — eso lo hace el caller.
        """
        params = {"artist_name": artist, "track_name": title}
        if album:
            params["album_name"] = album
        if duration > 0:
            params["duration"] = str(duration)

        url = f"{LRCLIB_URL}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                log.info("lrclib: 404 para '%s - %s'", artist, title)
                return LyricsResult(LyricsResult.NOT_FOUND, source="lrclib")
            log.warning("lrclib HTTP %s para '%s - %s'", e.code, artist, title)
            return LyricsResult(LyricsResult.ERROR, source="lrclib")
        except Exception as e:
            log.warning("lrclib falló para '%s - %s': %s", artist, title, type(e).__name__)
            return LyricsResult(LyricsResult.ERROR, source="lrclib")

        # Preferir letras sincronizadas; fallback a texto plano
        synced = (payload or {}).get("syncedLyrics") or ""
        plain  = (payload or {}).get("plainLyrics") or ""

        if synced:
            return LyricsResult(LyricsResult.FOUND, synced, True, "lrclib")
        if plain:
            return LyricsResult(LyricsResult.FOUND, plain, False, "lrclib")
        # La API respondió 200 pero sin contenido útil
        return LyricsResult(LyricsResult.NOT_FOUND, source="lrclib")

    # ── Escritura en caché con enforcement del tope ───────────────────────

    def _save_found(self, key: str, content: str):
        try:
            with open(self._lrc_path(key), "w", encoding="utf-8") as fh:
                fh.write(content)
            self._enforce_lru_limit()
        except OSError as e:
            log.error("No se pudo guardar letras en caché: %s", e)

    def _save_notfound(self, key: str):
        try:
            with open(self._notfound_path(key), "w", encoding="utf-8") as fh:
                fh.write("")  # archivo vacío, solo importa la fecha
        except OSError:
            pass

    def _enforce_lru_limit(self):
        """Mantiene a lo sumo MAX_CACHE_ENTRIES archivos .lrc (no cuenta .notfound)."""
        try:
            entries = []
            for name in os.listdir(self.cache_dir):
                if name.endswith(".lrc"):
                    path = os.path.join(self.cache_dir, name)
                    entries.append((os.path.getmtime(path), path))

            if len(entries) <= MAX_CACHE_ENTRIES:
                return

            # Ordenar por mtime ascendente (más viejos primero)
            entries.sort(key=lambda e: e[0])
            to_delete = entries[: len(entries) - MAX_CACHE_ENTRIES]
            for _mt, path in to_delete:
                try:
                    os.remove(path)
                except OSError:
                    pass
            log.info("Caché de letras: purgados %d archivos antiguos", len(to_delete))
        except OSError as e:
            log.warning("No se pudo aplicar LRU en caché de letras: %s", e)

    # ── API pública ───────────────────────────────────────────────────────

    def fetch(self, title: str, artist: str, album: str = "",
              duration: int = 0) -> LyricsResult:
        """
        Flujo completo: revisa caché → si no hay, pide a la API → cachea → retorna.

        - title, artist: obligatorios (strings no vacíos)
        - album, duration: opcionales (mejoran precisión del match en lrclib)
        """
        if not title or not artist:
            return LyricsResult(LyricsResult.ERROR)

        key = self._key(title, artist)

        cached = self._check_cache(key)
        if cached is not None:
            log.debug("Letras '%s - %s' servidas desde caché (%s)",
                      artist, title, cached.status)
            return cached

        # No hay caché — pedimos a la API
        result = self._fetch_lrclib(title, artist, album, duration)

        if result.status == LyricsResult.FOUND:
            self._save_found(key, result.content)
        elif result.status == LyricsResult.NOT_FOUND:
            self._save_notfound(key)
        # Los ERROR no se cachean para permitir reintentos

        return result

    # ── Gestión manual del caché (para el botón en Preferencias) ─────────

    def clear_cache(self) -> int:
        """Borra todo el directorio de caché. Retorna cuántos archivos borró."""
        count = 0
        try:
            for name in os.listdir(self.cache_dir):
                if name.endswith(".lrc") or name.endswith(".notfound"):
                    try:
                        os.remove(os.path.join(self.cache_dir, name))
                        count += 1
                    except OSError:
                        pass
            log.info("Caché de letras limpiada: %d archivos borrados", count)
        except OSError:
            pass
        return count

    def cache_stats(self) -> dict:
        """Para mostrar en Preferencias: número de letras guardadas y tamaño."""
        count = 0
        size_bytes = 0
        try:
            for name in os.listdir(self.cache_dir):
                if name.endswith(".lrc"):
                    path = os.path.join(self.cache_dir, name)
                    count += 1
                    size_bytes += os.path.getsize(path)
        except OSError:
            pass
        return {"count": count, "size_bytes": size_bytes}

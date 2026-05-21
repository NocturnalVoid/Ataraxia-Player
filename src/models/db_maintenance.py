# -*- coding: utf-8 -*-
"""
Mantenimiento programado de la base de datos.
- ANALYZE automático si pasó más de 30 días
- VACUUM manual (expuesto vía botón en Preferencias)
- Integridad (PRAGMA integrity_check)
"""
import time

from src.utils.logger import get_logger

log = get_logger(__name__)


class DatabaseMaintenance:

    ANALYZE_INTERVAL_DAYS = 30

    def __init__(self, db_manager):
        self.db_manager = db_manager

    # ── Mantenimiento automático ────────────────────────────────────────

    def run_scheduled_maintenance(self):
        """
        Se llama al arrancar la app. Ejecuta ANALYZE si pasó suficiente tiempo
        desde el último. No es bloqueante: corre rápido en BDs pequeñas.
        """
        last_analyze = self._get_config_ts("last_analyze_at", default=0)
        now = time.time()
        days_since = (now - last_analyze) / 86400

        if days_since >= self.ANALYZE_INTERVAL_DAYS:
            log.info("Ejecutando ANALYZE (último hace %.1f días)", days_since)
            try:
                with self.db_manager.get_connection() as conn:
                    conn.execute("ANALYZE")
                    conn.commit()
                self._set_config_ts("last_analyze_at", now)
                log.info("ANALYZE completado")
            except Exception:
                log.exception("ANALYZE falló — no crítico, seguirá pospuesto")

    # ── Operaciones manuales (desde Preferencias) ──────────────────────

    def vacuum(self) -> dict:
        """
        VACUUM: reconstruye la BD compactando espacio liberado.
        Retorna dict con tamaño antes/después y duración.
        """
        import os
        start = time.time()
        size_before = os.path.getsize(self.db_manager.db_path)

        try:
            with self.db_manager.get_connection() as conn:
                conn.execute("VACUUM")
                conn.commit()
        except Exception:
            log.exception("VACUUM falló")
            return {"success": False, "error": "VACUUM falló"}

        size_after = os.path.getsize(self.db_manager.db_path)
        elapsed = time.time() - start
        saved_bytes = size_before - size_after

        log.info(
            "VACUUM completado en %.1fs: %d → %d bytes (%.1f KB liberados)",
            elapsed, size_before, size_after, saved_bytes / 1024,
        )

        return {
            "success": True,
            "size_before": size_before,
            "size_after": size_after,
            "saved_bytes": saved_bytes,
            "elapsed_seconds": elapsed,
        }

    def check_integrity(self) -> dict:
        """Verifica la integridad estructural de la BD."""
        try:
            with self.db_manager.get_connection() as conn:
                row = conn.execute("PRAGMA integrity_check").fetchone()
            is_ok = row and row[0] == "ok"
            return {
                "success": True,
                "is_healthy": is_ok,
                "message": row[0] if row else "sin respuesta",
            }
        except Exception as e:
            log.exception("integrity_check falló")
            return {"success": False, "error": str(e)}

    def analyze_now(self):
        """Fuerza ANALYZE inmediatamente (sin esperar al intervalo)."""
        with self.db_manager.get_connection() as conn:
            conn.execute("ANALYZE")
            conn.commit()
        self._set_config_ts("last_analyze_at", time.time())

    def get_stats(self) -> dict:
        """Para mostrar en Preferencias: tamaño, nº de tablas, última mantención."""
        import os
        stats = {"size_bytes": os.path.getsize(self.db_manager.db_path)}
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM songs")
            stats["songs_count"] = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM playlists")
            stats["playlists_count"] = cursor.fetchone()[0]
            stats["last_analyze_at"] = self._get_config_ts("last_analyze_at", 0)
            stats["last_vacuum_at"]  = self._get_config_ts("last_vacuum_at", 0)
            # Versión de schema actual
            cursor.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
            stats["schema_version"] = cursor.fetchone()[0]
        return stats

    # ── Helpers privados ────────────────────────────────────────────────

    def _get_config_ts(self, key: str, default: float) -> float:
        with self.db_manager.get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM config WHERE key = ?", (key,)
            ).fetchone()
        try:
            return float(row[0]) if row else default
        except (TypeError, ValueError):
            return default

    def _set_config_ts(self, key: str, value: float):
        with self.db_manager.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                (key, str(value))
            )
            conn.commit()

    def create_backup(self, destination_path: str) -> bool:
        import sqlite3
        try:
            with self.db_manager.get_connection() as src_conn:
                dst_conn = sqlite3.connect(destination_path)
                src_conn.backup(dst_conn)
                dst_conn.close()
            log.info("Backup manual creado en %s", destination_path)
            return True
        except Exception:
            log.exception("Falló create_backup")
            return False

    def restore_from_backup(self, source_path: str) -> bool:
        """
        Reemplaza la BD actual con el archivo indicado.
        ⚠ Debe llamarse solo cuando la app esté en un estado estable
        (sin reproducción en curso, sin escaneos). El MainController es
        responsable de cerrar todo antes.
        """
        import shutil, os
        try:
            # Cerrar todas las conexiones pendientes
            if not os.path.exists(source_path):
                log.error("Backup no existe: %s", source_path)
                return False
            # Backup de la actual por si algo sale mal
            emergency = self.db_manager.db_path + ".pre-restore"
            shutil.copy2(self.db_manager.db_path, emergency)
            shutil.copy2(source_path, self.db_manager.db_path)
            log.info("BD restaurada desde %s (backup de emergencia: %s)",
                    source_path, emergency)
            return True
        except Exception:
            log.exception("Falló restore_from_backup")
            return False
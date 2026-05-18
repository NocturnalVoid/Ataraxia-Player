# -*- coding: utf-8 -*-
import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtCore import QSize, Qt
from src.utils.single_instance import SingleInstanceHandler
from src.utils.logger import configure_logging, get_logger
from src.controllers.main_controller import MainController


def _install_linux_desktop_file():
    """
    En Linux (especialmente Wayland), los compositores buscan el archivo
    .desktop por el `app_id` para mostrar el icono correcto. Sin este archivo
    el compositor cae al icono genérico "W" de XWayland.

    Instala (o actualiza) ~/.local/share/applications/ataraxia-player.desktop
    apuntando al ejecutable y al icono correctos.

    Idempotente: si el archivo ya existe con el mismo contenido, no hace nada.
    """
    if not sys.platform.startswith("linux"):
        return

    try:
        # Ubicación del .desktop (estándar XDG, no requiere root)
        xdg_data_home = os.environ.get(
            "XDG_DATA_HOME",
            os.path.join(os.path.expanduser("~"), ".local", "share"),
        )
        apps_dir = os.path.join(xdg_data_home, "applications")
        os.makedirs(apps_dir, exist_ok=True)
        desktop_path = os.path.join(apps_dir, "ataraxia-player.desktop")

        # Path absoluto al ejecutable de python actual y al main.py
        # Esto permite que la entrada funcione aún si el usuario mueve el proyecto
        python_exec = sys.executable
        main_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))
        icon_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "assets", "icons", "ataraxia.png")
        )
        # Si el png no existe, usa el svg
        if not os.path.exists(icon_path):
            icon_path = icon_path.replace(".png", ".svg")

        content = f"""[Desktop Entry]
Type=Application
Name=Ataraxia Player
GenericName=Music Player
Comment=Reproductor de música de escritorio
Exec={python_exec} {main_script} %U
Icon={icon_path}
Terminal=false
Categories=AudioVideo;Audio;Player;
MimeType=audio/mpeg;audio/flac;audio/x-wav;audio/ogg;audio/mp4;audio/aac;audio/opus;
StartupNotify=true
StartupWMClass=ataraxia-player
"""

        # Idempotencia: solo reescribir si el contenido cambió
        existing = ""
        if os.path.exists(desktop_path):
            try:
                with open(desktop_path, "r", encoding="utf-8") as fh:
                    existing = fh.read()
            except OSError:
                pass

        if existing.strip() != content.strip():
            with open(desktop_path, "w", encoding="utf-8") as fh:
                fh.write(content)
            # En algunos compositores hay que dar permisos de ejecución al .desktop
            try:
                os.chmod(desktop_path, 0o755)
            except OSError:
                pass
            import logging
            logging.getLogger(__name__).info(
                "Archivo .desktop instalado/actualizado en %s", desktop_path
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "No se pudo instalar el archivo .desktop: %s", e
        )


def _apply_windows_taskbar_fix():
    """
    Windows agrupa las ventanas por AppUserModelID en la barra de tareas.
    Sin llamar a SetCurrentProcessExplicitAppUserModelID, Windows usa el ID
    del intérprete (python.exe) y muestra SU icono, no el nuestro.

    IMPORTANTE: la API espera LPCWSTR (UTF-16). Hay que declarar argtypes
    explícitamente o pasar c_wchar_p; si no, ctypes pasa bytes y Windows
    recibe basura sin avisar.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        app_id = "Ataraxia.Player.Desktop.1"
        func = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        func.argtypes = [wintypes.LPCWSTR]     # ← clave: declara wide string
        func.restype  = ctypes.HRESULT
        func(app_id)
    except Exception as e:
        # Loggeamos pero no abortamos — la app funciona sin el fix, solo
        # con el icono equivocado en la barra de tareas
        import logging
        logging.getLogger(__name__).warning("AppUserModelID fix failed: %s", e)


def _load_app_icon() -> QIcon:
    """
    Construye un QIcon con múltiples tamaños exactos preferentemente desde el SVG
    (escala vectorialmente, sin dientes de sierra). Si el SVG no está disponible,
    cae al PNG y le añade todos los tamaños que Windows/Linux piden.

    ¿Por qué importa? Si dejas que Qt escale un PNG arbitrario (501×499 en nuestro
    caso), los algoritmos bilineales producen aliasing en tamaños pequeños. Con un
    QIcon que ya contiene pixmaps pre-renderizados en 16, 24, 32, 48, 64, 128, 256
    el sistema operativo elige el exacto sin resampleo.
    """
    icon = QIcon()
    svg_path = "assets/icons/ataraxia.svg"
    ico_path = "assets/icons/ataraxia.ico"
    png_path = "assets/icons/ataraxia.png"

    # Tamaños estándar que Windows/Linux/macOS piden para barra de tareas,
    # tray icon, notificaciones, Alt+Tab, ventanas, etc.
    target_sizes = [16, 24, 32, 40, 48, 64, 96, 128, 256]

    # 1) Opción ideal: renderizar desde SVG a cada tamaño
    if os.path.exists(svg_path):
        try:
            from PyQt6.QtSvg import QSvgRenderer
            from PyQt6.QtGui import QPainter
            renderer = QSvgRenderer(svg_path)
            if renderer.isValid():
                for size in target_sizes:
                    pm = QPixmap(size, size)
                    pm.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(pm)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    renderer.render(painter)
                    painter.end()
                    icon.addPixmap(pm)
                return icon
        except Exception:
            pass  # Cae al fallback

    # 2) Fallback: usar el .ico en Windows (contiene multiple sizes)
    #    o el .png en otros sistemas, añadiendo tamaños explícitamente
    source = ico_path if (sys.platform == "win32" and os.path.exists(ico_path)) else png_path
    if os.path.exists(source):
        icon = QIcon(source)
        # Aseguramos que tenga al menos 32/48/256 disponibles si el icono base lo permite
        base_pm = QPixmap(source)
        if not base_pm.isNull():
            for size in target_sizes:
                if icon.actualSize(QSize(size, size)) != QSize(size, size):
                    scaled = base_pm.scaled(
                        size, size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    icon.addPixmap(scaled)
    return icon


def main():
    # ===================================================================
    # SOLUCIÓN MAESTRA: Forzar el directorio raíz.
    # ===================================================================
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    os.chdir(base_dir)

    # Inicializar el sistema de logging antes que cualquier otro módulo escriba
    log_path = configure_logging()
    log = get_logger(__name__)
    log.info("Application starting — base_dir=%s", base_dir)

    # Fix específico para la barra de tareas de Windows — DEBE ir antes de crear QApplication
    _apply_windows_taskbar_fix()

    # Linux/Wayland: instalar/actualizar archivo .desktop para que el compositor
    # resuelva el icono correcto en lugar del genérico "W" de XWayland
    _install_linux_desktop_file()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Ataraxia Player")
    app.setOrganizationName("Ataraxia")

    # Clave para Wayland: enlazar la app con el archivo .desktop instalado.
    # El compositor (GNOME/KDE/Sway) busca este nombre y carga su Icon=.
    # Disponible desde Qt 5.7. Sin esta línea, Wayland no encuentra el icono
    # aunque setWindowIcon() funcione perfectamente en X11.
    app.setDesktopFileName("ataraxia-player")

    # Icono global — QIcon con múltiples tamaños precalculados (anti-aliasing)
    app_icon = _load_app_icon()
    if app_icon.availableSizes():
        app.setWindowIcon(app_icon)
        log.info("Icono de aplicación cargado con %d tamaño(s)", len(app_icon.availableSizes()))
    else:
        log.warning("No se pudo cargar ningún icono de aplicación")

    # Sistema para evitar ventanas duplicadas
    instance_handler = SingleInstanceHandler()
    if instance_handler.is_another_instance_running():
        log.info("Another instance is running — passing file and exiting")
        sys.exit(0)

    instance_handler.start_server()

    try:
        controller = MainController()
        controller.ipc_handler = instance_handler
        instance_handler.file_received.connect(controller._play_dropped_file)

        # Garantizamos que la ventana principal y el tray usen el mismo QIcon
        # (algunos WMs de Linux ignoran setWindowIcon del QApplication global)
        if hasattr(controller, 'main_window'):
            controller.main_window.setWindowIcon(app_icon)
        if hasattr(controller, 'main_window') and hasattr(controller.main_window, 'tray_icon'):
            controller.main_window.tray_icon.setIcon(app_icon)

        if len(sys.argv) > 1:
            initial_file = sys.argv[1]
            controller._play_dropped_file(initial_file)

        controller.run()
        exit_code = app.exec()
        log.info("Application exiting normally — code=%s", exit_code)
        sys.exit(exit_code)
    except Exception:
        log.critical("Fatal error during startup", exc_info=True)
        raise


if __name__ == "__main__":
    main()
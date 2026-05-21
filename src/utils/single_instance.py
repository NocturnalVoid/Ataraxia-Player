# -*- coding: utf-8 -*-
from PyQt6.QtNetwork import QLocalSocket, QLocalServer
from PyQt6.QtCore import pyqtSignal, QObject
import sys

class SingleInstanceHandler(QObject):
    """
    Gestiona la comunicación entre procesos para asegurar una sola ventana.
    """
    file_received = pyqtSignal(str)

    def __init__(self, server_name="AtaraxiaPlayer_IPC"):
        super().__init__()
        self.server_name = server_name
        self.server = None

    def is_another_instance_running(self) -> bool:
        """Intenta conectarse a un servidor existente. Si puede, ya hay una app abierta."""
        socket = QLocalSocket()
        socket.connectToServer(self.server_name)
        
        if socket.waitForConnected(500):
            # Ya hay un Ataraxia abierto. Si nos pasaron un archivo, se lo enviamos.
            if len(sys.argv) > 1:
                filepath = sys.argv[1]
                socket.write(filepath.encode('utf-8'))
                socket.waitForBytesWritten(500)
            socket.disconnectFromServer()
            return True
            
        return False

    def start_server(self):
        """Si somos la primera instancia, creamos el servidor para escuchar a las futuras."""
        self.server = QLocalServer(self)
        
        # Limpiar servidores "fantasma" de cierres inesperados anteriores
        QLocalServer.removeServer(self.server_name)
        
        self.server.listen(self.server_name)
        self.server.newConnection.connect(self._handle_new_connection)

    def _handle_new_connection(self):
        """Atrapa los archivos que nos envían las instancias clonadas."""
        socket = self.server.nextPendingConnection()
        if socket.waitForReadyRead(1000):
            filepath = socket.readAll().data().decode('utf-8')
            if filepath:
                self.file_received.emit(filepath)
        socket.disconnectFromServer()
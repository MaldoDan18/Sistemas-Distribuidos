PWA cliente para la simulación de venta de boletos

Estructura
- `webapp/`: archivos estáticos de la PWA (`index.html`, `app.js`, `styles.css`, `manifest.json`, `sw.js`)

Qué es una PWA
Una Progressive Web App es una aplicación web que se comporta como una aplicación instalada: puede mostrarse a pantalla completa, guardar estado local y apoyarse en un Service Worker para mejorar la experiencia de uso.

Motivación
La implementación de esta PWA persigue llevar la simulación de venta de boletos a una interfaz visual y accesible desde el navegador. La selección de asientos, la reserva y la compra se presentan de forma inmediata, sin alterar el protocolo TCP de los clientes existentes y manteniendo la misma lógica de negocio del servidor.

API y servidor
El `servidor.py` de esta carpeta expone dos canales de comunicación sobre la misma lógica de reservas:
- El servidor socket original, usado por los clientes por hilos, sigue escuchando en el puerto 5000 por defecto.
- La API HTTP, consumida por la PWA, escucha en `127.0.0.1:5001`.

Los endpoints REST disponibles son:
- `GET /api/availability`: devuelve el estado de asientos, el snapshot y el estado de la venta.
- `POST /api/request_ticket`: crea una reserva a partir de un payload JSON.
- `POST /api/purchase`: confirma una compra a partir de un payload JSON.
- `POST /api/register_client`: registra a la PWA como cliente lógico de la simulación.
- `POST /api/ready`: marca a la PWA como lista para iniciar.

La interfaz guarda el carrito en `localStorage` y usa un identificador local para distinguir cada cliente en el navegador.

Ejecución
1. Entrar en la carpeta `07-App-PWA`.
2. Crear y activar el entorno virtual.
3. Instalar dependencias.
4. Arrancar el servicio de tickets.
5. Arrancar el servidor de venta.
6. Servir la carpeta `webapp` con un servidor estático.
7. Abrir la interfaz en el navegador.

Comandos en Windows (PowerShell):

```powershell
cd 07-App-PWA
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt

python ticketing_service.py

python servidor.py 1 --coordinator-host 127.0.0.1 --coordinator-port 6000 --no-gui

python -m http.server 8000 --directory webapp
```

Abrir la interfaz en el navegador:

```text
http://127.0.0.1:8000
```

Si se requiere coordinación global, arrancar antes el coordinador con el número de salas esperado:

```powershell
python coordinador.py 1 --no-gui
```
## Implementación de PWA

Una Progressive Web App (PWA) es una aplicación web que incorpora capacidades propias de una app instalada, como funcionamiento desde el navegador, almacenamiento local y soporte para experiencias más fluidas.

En esta práctica se implementa una PWA cliente para la simulación de venta de boletos, con el fin de ofrecer una interfaz visual para seleccionar asientos, reservarlos y concretar la compra sin alterar la lógica principal del servidor.

Estructura:
- webapp/: archivos estáticos de la PWA (index.html, app.js, styles.css, manifest.json, sw.js)

Cómo probar localmente:
1. Se debe tener corriendo el servidor de la práctica 07 (copia de la práctica 06) en el puerto 5000.
2. Desde la carpeta `07-App-PWA` se debe arrancar un servidor estático para servir `webapp`.

Ejemplo (Python 3):

```bash
cd 07-App-PWA
python -m http.server 8000 --directory webapp
```

3. La apertura en el navegador corresponde a `http://localhost:8000/index.html` (o `http://127.0.0.1:8000/index.html`).
4. Se selecciona el tipo de comprador, se espera a que se cargue el mapa y se prueban los asientos. La PWA llamará a los endpoints en `http://127.0.0.1:5000/api/...` por defecto.

API server:
- Esta copia del `servidor.py` expone un pequeño servidor HTTP en `127.0.0.1:5001` con los endpoints REST consumidos por la PWA:
	- `GET /api/availability` — estado de asientos y snapshot
	- `POST /api/request_ticket` — crear una reserva (payload JSON)
	- `POST /api/purchase` — confirmar compra (payload JSON)

Nota: el servidor socket original sigue escuchando en el puerto configurado (por defecto 5000) para los clientes por hilos; la API HTTP utiliza el puerto 5001 para evitar conflictos.

Notas:
- El Service Worker requiere servir desde `localhost` o HTTPS para poder registrarse.
- La PWA guarda el carrito en `localStorage` y registra un `buyer_id` local para identificar al cliente frente al servidor.
- No se modifican las prácticas 01-06; el trabajo se mantiene dentro de `07-App-PWA`.

Setup rápido (desarrollo)
-------------------------
Recomendado: crear un entorno virtual en la carpeta `07-App-PWA` para instalar dependencias localmente y evitar caos.

Windows (PowerShell):

```powershell
cd 07-App-PWA
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS / Linux:

```bash
cd 07-App-PWA
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Seleccionar intérprete en VS Code
--------------------------------
- Abrir la carpeta `07-App-PWA` en VS Code.
- Pulsar Ctrl+Shift+P → `Python: Select Interpreter` y elegir `07-App-PWA/.venv`.
- De este modo, Pylance y el terminal integrado usan el entorno correcto.

Arrancar servicios para prueba local
-----------------------------------
1) (Opcional) Ticketing service (emite tickets):

```powershell
cd 07-App-PWA
. .venv\Scripts\Activate.ps1
python ticketing_service.py
```

2) (Opcional) Coordinador global (para sincronizar múltiples servidores):

```powershell
cd 07-App-PWA
. .venv\Scripts\Activate.ps1
python coordinador.py 1 --no-gui
```

3) Servidor de venta (proporciona API HTTP y socket TCP):

```powershell
cd 07-App-PWA
. .venv\Scripts\Activate.ps1
python servidor.py 1 --coordinator-host 127.0.0.1 --coordinator-port 6000 --no-gui
```

4) Cliente de hilos (genera compradores simulados):

```powershell
cd 07-App-PWA
. .venv\Scripts\Activate.ps1
python cliente.py normal 1 --coordinator-host 127.0.0.1 --coordinator-port 6000
```

5) Servir la PWA (static):

```powershell
cd 07-App-PWA
. .venv\Scripts\Activate.ps1
python -m http.server 8000 --directory webapp
```

La interfaz queda disponible en: http://127.0.0.1:8000
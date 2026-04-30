PWA cliente para la simulación de venta de boletos

Estructura:
- webapp/: archivos estáticos de la PWA (index.html, app.js, styles.css, manifest.json, sw.js)

Cómo probar localmente:
1. Asegúrate de tener corriendo el servidor de la práctica 07 (copia de la práctica 06) en el puerto 5000.
2. Desde la carpeta `07-App-PWA` arrancar un servidor estático para servir `webapp`.

Ejemplo (Python 3):

```bash
cd 07-App-PWA
python -m http.server 8000 --directory webapp
```

3. Abrir en el navegador `http://localhost:8000/index.html` (o `http://127.0.0.1:8000/index.html`).
4. Selecciona tipo de comprador, espera a que se cargue el mapa y prueba a seleccionar asientos. La PWA llamará a los endpoints en `http://127.0.0.1:5000/api/...` por defecto.

API server:
- Esta copia del `servidor.py` expone un pequeño servidor HTTP en `127.0.0.1:5001` con los endpoints REST consumidos por la PWA:
	- `GET /api/availability` — estado de asientos y snapshot
	- `POST /api/request_ticket` — crear una reserva (payload JSON)
	- `POST /api/purchase` — confirmar compra (payload JSON)

Nota: el servidor socket original sigue escuchando en el puerto configurado (por defecto 5000) para los clientes por hilos; la API HTTP utiliza el puerto 5001 para evitar conflictos.

Notas:
- El Service Worker requiere servir desde `localhost` o HTTPS para poder registrarse.
- La PWA guarda el carrito en `localStorage` y registra un `buyer_id` local para identificar al cliente frente al servidor.
- No modificamos las prácticas 01-06; trabajamos dentro de `07-App-PWA` solamente.

Setup rápido (desarrollo)
-------------------------
Recomendado: crea un entorno virtual en la carpeta `07-App-PWA` para instalar dependencias localmente y evitar contaminar tu sistema.

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
- Abre la carpeta `07-App-PWA` en VS Code.
- Pulsa Ctrl+Shift+P → `Python: Select Interpreter` y elige `07-App-PWA/.venv`.
- Esto hará que Pylance y el terminal integrado usen el entorno correcto.

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

Abrir la UI: http://127.0.0.1:8000

Buenas prácticas de Git
----------------------
- No incluyas `.venv/` ni `.vscode/` en el repo. Usar `.gitignore` para omitirlos.
- Comparte dependencias con `requirements.txt` (ya incluido en `07-App-PWA`).
- Si por error subiste archivos locales grandes, limpia el índice con `git rm --cached <path>` y añade `.gitignore`.

Si quieres, puedo añadir una pequeña sección adicional en `README.md` con ejemplos de payloads para las llamadas `POST /api/request_ticket` y `POST /api/purchase`.

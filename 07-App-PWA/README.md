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

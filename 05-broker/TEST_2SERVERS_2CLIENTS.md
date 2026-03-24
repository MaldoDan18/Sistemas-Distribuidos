# Test: 2 Servidores + 2 Clientes + Countdown de 8 segundos

Este test valida la ejecución con:
- **1 Coordinador** (esperando 2 servidores)
- **2 Servidores** (cada uno esperando 1 cliente)
- **2 Clientes** (uno por servidor)
- **Countdown** de 8 segundos antes de iniciar las ventas

## Prerequisitos

Todos los comandos deben ejecutarse desde la carpeta raíz del proyecto (o ajusta las rutas según tu ubicación):
```powershell
cd c:\Users\malbe\Documentos\Github\Sistemas-Distribuidos\05-broker
```

## Secuencia de ejecución

Abre **5 terminales** (PowerShell o CMD), navega a la carpeta 05-broker, y ejecuta los siguientes comandos en el orden que se indica:

### Terminal 1: Coordinador
```powershell
# Espera 2 servidores
python coordinador.py 2 --host 127.0.0.1 --port 6000 --no-gui
```

**Salida esperada:**
```
Coordinador global iniciado
Escuchando en 127.0.0.1:6000
Servidores esperados: 2
```

---

### Terminal 2: Servidor 1 (BTS-FECHA-01)
```powershell
# Espera 1 cliente
python servidor.py 1 `
  --host 127.0.0.1 `
  --port 5000 `
  --sale-id BTS-FECHA-01 `
  --coordinator-host 127.0.0.1 `
  --coordinator-port 6000 `
  --no-gui
```

**Salida esperada:**
```
[Servidor 1] Iniciado en 127.0.0.1:5000
[Servidor 1] Registrándose con el coordinador...
[Servidor 1] Registración completada: slot=0, servidores registrados=1/2
```

El servidor se quedará esperando al cliente...

---

### Terminal 3: Servidor 2 (BTS-FECHA-02)
```powershell
# Espera 1 cliente
python servidor.py 1 `
  --host 127.0.0.1 `
  --port 5001 `
  --sale-id BTS-FECHA-02 `
  --coordinator-host 127.0.0.1 `
  --coordinator-port 6000 `
  --no-gui
```

**Salida esperada:**
```
[Servidor 2] Iniciado en 127.0.0.1:5001
[Servidor 2] Registrándose con el coordinador...
[Servidor 2] Registración completada: slot=1, servidores registrados=2/2
```

Cuando se conecte el servidor 2, el coordinador todavía esperará por los clientes...

---

### Terminal 4: Cliente 1 (conecta a Servidor 1)
```powershell
# 5 hilos de compra
python cliente.py cliente-01 5 `
  --host 127.0.0.1 `
  --port 5000 `
  --coordinator-host 127.0.0.1 `
  --coordinator-port 6000 `
  --time-between-requests 0.1
```

**Salida esperada:**
```
[Cliente cliente-01] Conectándose a 127.0.0.1:5000...
[Cliente cliente-01] Conectado al servidor de venta.
Esperando señal GLOBAL_START...
```

El cliente se quedará esperando la señal de inicio...

---

### Terminal 5: Cliente 2 (conecta a Servidor 2)
```powershell
# 5 hilos de compra
python cliente.py cliente-02 5 `
  --host 127.0.0.1 `
  --port 5001 `
  --coordinator-host 127.0.0.1 `
  --coordinator-port 6000 `
  --time-between-requests 0.1
```

**Salida esperada:**
```
[Cliente cliente-02] Conectándose a 127.0.0.1:5001...
[Cliente cliente-02] Conectado al servidor de venta.
Esperando señal GLOBAL_START...
```

---

## Qué sucede después

Una vez que el Cliente 2 se conecte:

1. **[Terminal 1 - Coordinador]** mostrará:
   ```
   [Coordinador] Condición global cumplida. Iniciando cuenta regresiva...
   
   [Coordinador] Iniciando cuenta regresiva de 8 segundos antes de GLOBAL_START...
   [Countdown] 8...
   [Countdown] 7...
   [Countdown] 6...
   [Countdown] 5...
   [Countdown] 4...
   [Countdown] 3...
   [Countdown] 2...
   [Countdown] 1...
   [Countdown] 0 - ¡INICIANDO VENTAS GLOBALES!
   ```

2. **[Terminales 2 y 3 - Servidores]** recibirán el mensaje `GLOBAL_START` y comenzarán a procesar compras

3. **[Terminales 4 y 5 - Clientes]** verán:
   ```
   ¡GLOBAL_START! Iniciando compras...
   ```

4. Las compras procederán en paralelo durante ~10 segundos (por defecto)

5. Cuando se agoten los tickets o el tiempo, verás:
   ```
   [Servidor] Ventas finalizadas: sold=1500/1500, ...
   ```

---

## Observaciones

- El **countdown de 8 segundos** es para que veas visualmente cómo el coordinador espera antes de enviar el GLOBAL_START
- Durante el countdown, los servidores y clientes están **listos pero en espera**
- Una vez que empieza el countdown, **ya no se pueden conectar más clientes** (la condición global ya se cumplió)
- Si necesitas ajustar el countdown, modifica el valor `countdown_seconds=8` en `coordinador.py`

## Para detener

Presiona `Ctrl+C` en cualquier terminal para detener el proceso.

# Broker RMI Minimo

Este modulo implementa un broker en Java RMI para observabilidad de ventas por `saleId`.

## Estados de color

- `gray`: sin eventos
- `blue`: servidor registrado
- `orange`: clientes conectandose
- `green`: servidor finalizado

## Eventos soportados

- `SERVER_REGISTERED`
- `CLIENT_CONNECTED`
- `SERVER_FINISHED`

## Compilar

```powershell
cd 05-broker
./build.ps1
```

## Ejecutar broker (RMI + GUI)

```powershell
cd 05-broker
java -cp out broker.BrokerServerMain --host 127.0.0.1 --port 1099 --bind BrokerService
```

## Enviar evento manual de prueba

```powershell
cd 05-broker
java -cp out broker.BrokerEventCli --host 127.0.0.1 --port 1099 --bind BrokerService --event SERVER_REGISTERED --sale-id 127.0.0.1:5000 --server-host 127.0.0.1 --server-port 5000 --expected-clients 3
```

## Flujo sugerido con tu proyecto

1. Ejecutar `coordinador.py` con `--no-gui`.
2. Ejecutar este broker RMI.
3. Ejecutar `servidor.py` con parametros de broker (ver cambios en `servidor.py`).
4. Ejecutar `cliente.py` con parametros de broker (ver cambios en `cliente.py`).

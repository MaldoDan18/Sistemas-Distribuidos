# Práctica 6: Servicios

Esta carpeta contiene la adaptación de la práctica anterior para separar la emisión de tickets en un servicio externo.

## Qué incluye

- `cliente.py`
- `servidor.py`
- `coordinador.py`
- `ticketing_service.py`

## Qué hace cada parte

- El `coordinador` sincroniza las ventas.
- El `servidor` administra reservas y confirma compras.
- El `ticketing_service` genera y guarda tickets en `tickets/tickets.txt`.
- El `cliente` dispara los compradores según el tipo y la cantidad indicada.

## Orden de ejecución

1. Iniciar `ticketing_service.py`.
2. Iniciar `coordinador.py` si la prueba usa varias ventas.
3. Iniciar cada `servidor.py` con la dirección del Ticketing Service.
4. Iniciar los `cliente.py`.

## Observaciones

- Ahora la compra depende de un servicio externo, así que el servidor ya no cierra la operación solo.
- La simulación tarda más porque intervienen llamadas entre puertos distintos y persistencia en archivo.
- Antes la corrida terminaba en segundos; con `Ticketing Service` y escritura en `txt`, el tiempo real sube y puede rondar cerca de un minuto.
- Esa latencia no es un error: es el costo normal de desacoplar la emisión del ticket y hacer persistencia externa.

## Archivo de tickets

- `tickets/tickets.txt`

Cada línea es un JSON con los datos del ticket emitido.

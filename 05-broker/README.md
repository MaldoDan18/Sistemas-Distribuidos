# Broker RMI Minimo

Modulo Java RMI para observabilidad del estado de ventas por saleId.

## Estados de color

- gray: sin eventos
- blue: servidor registrado
- orange: clientes conectados o venta en curso
- green: servidor finalizado

## Eventos soportados

- SERVER_REGISTERED
- CLIENT_CONNECTED
- SERVER_FINISHED

## Compilacion

Comando:

powershell
cd 05-broker
./build.ps1


Resultado esperado:

- Se genera o actualiza el directorio out con clases .class.

## Ejecucion del broker (RMI + GUI)

Comando recomendado:

powershell
cd 05-broker
./run-broker.ps1


Comando equivalente:

powershell
cd 05-broker
java -cp out broker.BrokerServerMain --host 127.0.0.1 --port 1099 --bind BrokerService


Resultado esperado:

- Registro RMI activo en 127.0.0.1:1099.
- GUI del broker abierta y refrescando estados.

## Evento manual de prueba

Comando:

powershell
cd 05-broker
java -cp out broker.BrokerEventCli --host 127.0.0.1 --port 1099 --bind BrokerService --event SERVER_REGISTERED --sale-id SALA-PRUEBA --server-host 127.0.0.1 --server-port 5000 --expected-clients 3


Resultado esperado:

- Se crea una fila en la GUI para SALA-PRUEBA con estado blue.

## Flujo de ejecucion

1. Iniciar coordinador.
2. Iniciar broker RMI.
3. Iniciar servidores con parametros de broker.
4. Iniciar clientes con parametros de broker.

Los eventos enviados por servidores y clientes actualizan el broker en tiempo real.

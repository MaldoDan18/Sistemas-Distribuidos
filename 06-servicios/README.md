# Práctica 6: Integración de Servicios

Esta práctica retoma como base la implementación de la carpeta [04-multiples-servidores-clientes](../04-multiples-servidores-clientes) y reestructura el sistema para introducir un servicio externo especializado en la generación y persistencia de tickets.

La carpeta [05-broker](../05-broker) se toma únicamente como referencia histórica de la evolución del proyecto, pero no será la base de esta práctica.

## Objetivo

El propósito de esta práctica es separar responsabilidades y convertir una parte del sistema en un servicio externo consumible por red. En particular, se implementará un **Ticketing Service** encargado de recibir la confirmación de una compra, generar el ticket correspondiente y guardar el registro persistente en un archivo de texto.

La verificación de estado tipo **HEALTH** ya existe como parte de la base previa y se conserva para el funcionamiento interno de la simulación, pero no es el foco de esta práctica ni se amplía su alcance.

## Comparación con prácticas anteriores

### Práctica 4: múltiples servidores y clientes

En la práctica 4, el sistema funcionaba como una simulación distribuida de ventas con múltiples clientes y múltiples servidores. El flujo principal estaba concentrado en el servidor de ventas, que se encargaba de:

- registrar clientes,
- administrar reservas,
- procesar compras,
- y mantener el estado de los asientos.

Todo esto ocurría dentro del mismo bloque funcional, con coordinación entre procesos, pero sin separar claramente la emisión del ticket como un servicio independiente.

### Práctica 6: servicios externos

En esta práctica, el sistema evoluciona hacia una arquitectura con responsabilidades separadas:

- el servidor de venta mantiene la lógica de reservas y confirmación de compra,
- el **Ticketing Service** se encarga de emitir y persistir tickets,
- el servicio de **HEALTH** permite monitoreo y estado,
- y el coordinador sigue funcionando como orquestador de arranque y sincronización global.

La diferencia clave es que el ticket deja de ser parte de la lógica interna del servidor de venta y pasa a ser responsabilidad de un componente externo.

## Cambio de arquitectura

Antes:

- compra y ticket vivían dentro del mismo bloque del servidor,
- el ticket era un resultado interno de la venta,
- la persistencia estaba acoplada al flujo de compra.

Ahora:

- la compra se confirma en el servidor de ventas,
- el servidor envía la información al **Ticketing Service**,
- el servicio genera el ticket,
- el ticket se guarda de forma persistente,
- y el servidor de ventas recibe una respuesta de confirmación.

Esto convierte al ticketing en un servicio real, externo y reutilizable por red.

## Componentes base reutilizados

Para esta práctica se reutiliza la base de la carpeta 04, tomando como referencia principal estos archivos:

- [cliente.py](../04-multiples-servidores-clientes/cliente.py)
- [servidor.py](../04-multiples-servidores-clientes/servidor.py)
- [coordinador.py](../04-multiples-servidores-clientes/coordinador.py)

Estos archivos servirán como punto de partida para integrar el nuevo servicio sin romper el flujo existente de venta, sincronización y cierre.

## Servicios propuestos

### 1. HEALTH

Servicio de monitoreo y estado ya presente en la base previa. Se conserva para verificar que el sistema sigue disponible y para consultar información como:

- venta abierta o cerrada,
- asientos vendidos,
- reservas activas,
- estado de conexión,
- y sincronización general.

Este servicio no forma parte del flujo visible de venta y no se modifica en esta práctica. Su función es operativa y de supervisión.

### 2. Ticketing Service

Servicio externo encargado de:

- recibir la información de una compra confirmada,
- generar el ticket,
- almacenar el ticket en un archivo de texto,
- y devolver una respuesta de confirmación.

Este servicio sí es parte visible de la arquitectura porque representa una responsabilidad independiente del servidor de ventas.

## Implementación actual

La carpeta 06 ya contiene la base funcional de la práctica y ahora incorpora el servicio externo de tickets como un proceso separado.

Archivos principales:

- [cliente.py](cliente.py)
- [servidor.py](servidor.py)
- [coordinador.py](coordinador.py)
- [ticketing_service.py](ticketing_service.py)

### Orden de ejecución sugerido

1. Iniciar el coordinador, si la prueba usa sincronización global entre servidores.
2. Iniciar el Ticketing Service externo.
3. Iniciar el servidor de ventas con la configuración del Ticketing Service.
4. Iniciar los clientes.

### Flujo de compra con tickets

- El cliente solicita una reserva.
- El servidor reserva el asiento.
- Cuando el cliente confirma la compra, el servidor contacta al Ticketing Service.
- Si el Ticketing Service responde correctamente, se confirma la compra.
- El ticket se almacena en un archivo de texto como evidencia persistente.

### Archivo de tickets

Por defecto, el Ticketing Service guarda la información en:

- `tickets/tickets.txt`

Cada ticket se guarda como una línea JSON con datos como:

- identificador del ticket,
- fecha y hora de emisión,
- identificador de la venta,
- comprador,
- tipo de comprador,
- zona,
- asiento,
- reserva asociada,
- y origen de la solicitud.

## Alcance de la implementación

La idea de esta práctica no es reescribir todo el proyecto, sino adaptar la arquitectura existente para que el sistema quede organizado por servicios.

Se busca mantener:

- la simulación de múltiples clientes,
- la sincronización por servidor,
- el coordinador global,
- y el flujo de compra actual.

Y agregar:

- separación de responsabilidades,
- persistencia de tickets,
- y comunicación con servicios externos.

## Relación con la presentación visual

La práctica también puede conservar la línea visual de entregas anteriores, con una interfaz que muestre el estado de la venta, los clientes conectados y la evolución de los tickets emitidos. Sin embargo, la diferencia principal estará en la arquitectura interna, no solo en la apariencia.

## Idea central para defender la práctica

La mejora no consiste únicamente en “agregar un servicio”, sino en reorganizar el sistema para que el ticketing sea una capacidad externa, independiente y consumible por red. Eso hace al sistema más modular y más cercano a una arquitectura basada en servicios.

## Estado esperado del proyecto

En esta carpeta se concentrará el trabajo de la práctica 6. Las demás carpetas del repositorio quedan como referencia de consulta para entender la evolución del proyecto.

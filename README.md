
# Sistemas Distribuidos - Séptimo Semestre

Repositorio educativo diseñado para organizar, documentar y compartir la evolución de las soluciones arquitectónicas desarrolladas en la asignatura de **Sistemas Distribuidos**. El proyecto ilustra la transición desde paradigmas de concurrencia local hasta orquestaciones multi-contenedor desacopladas y desplegadas en entornos multi-cloud.

* **Enlace Oficial del Repositorio:** [https://github.com/MaldoDan18/Sistemas-Distribuidos.git](https://github.com/MaldoDan18/Sistemas-Distribuidos.git)

---

## 📈 Evolución Arquitectónica del Sistema

A lo largo del semestre, el núcleo del proyecto (el sistema de venta de entradas concurrente con mapa de asientos en tiempo real) ha mutado de infraestructura para adoptar mejores prácticas de la ingeniería de software distribuido:

### 1. El Origen: Concurrencia y Monolito C/S (Prácticas 01 - 06)
* **Enfoque:** Manejo de múltiples hilos de ejecución, sockets concurrentes y paso de mensajes básicos. 
* **Evolución:** Se establecieron las primitivas lógicas para evitar condiciones de carrera en el mapa de auditorio local mediante un servidor centralizado básico y su posterior empaquetamiento en contenedores Docker independientes para distribución limpia.

### 2. El Salto a la Nube y Clientes Web PWA (Práctica 07)
* **Enfoque:** Desacoplamiento de la interfaz gráfica e infraestructura multi-plataforma.
* **Evolución:** El frontend mutó a una **Progressive Web App (PWA)** interactiva equipada con un Dashboard analítico en tiempo real. La arquitectura se replicó en producción sobre instancias independientes en las tres grandes nubes: **Microsoft Azure**, **Amazon Web Services (AWS)** y **Google Cloud Platform (GCP)**.

### 3. Descentralización Total y Microservicios (Práctica 08 - En adelante)
* **Enfoque:** Disponibilidad atómica, tolerancia a fallos y enrutamiento inteligente.
* **Evolución:** El servidor monolítico tradicional se fragmentó por completo. Se transformó en una **API Gateway** perimetral encargada de gestionar el tráfico de entrada, delegando la persistencia y control absoluto del aforo al módulo autónomo **Ticketing Service** (Autoridad Superior sobre la matriz geométrica del mapa).

---

## 📂 Estructura del Repositorio

El árbol de directorios refleja de forma cronológica la maduración del software distribuido instalado sobre el entorno de ejecución base:

| Directorio | Componente / Práctica | Descripción Lógica |
| :--- | :--- | :--- |
| `📁 01-multiprocesamiento` | Carga de Práctica 1 | Primitivas de hilos paralelos y sincronización inicial. |
| `📁 02-clienteservidor` | Carga de Práctica 2 | Modelado clásico de sockets y canales bloqueantes. |
| `📁 03-multiplesclientes` | Carga de Práctica 3 | Servidor multiplexado con soporte a peticiones concurrentes. |
| `📁 04-multiples-servidores-clientes` | Carga de Práctica 4 | Topologías de red distribuidas y replicación de buffers. |
| `📁 05-broker` | Práctica 05 | Implementación funcional de middleware para mediación de mensajes. |
| `📁 06-servicios` | Práctica Corregida | Contenerización base y abstracción de servicios de red en Docker. |
| `📁 07-App-PWA` | Aplicación Web Progresiva | Despliegue en Cloud (Azure, AWS, GCP) del monolito + PWA frontend. |
| `📁 08-Microservicios` | Arquitectura Desacoplada | Implementación de API Gateway y aislamiento del Ticketing Service. |
| `📁 09-Cloud-config` | Reporte de Nubes | Auditoría, mapeo de firewalls (NSG/Security Groups) y direccionamiento IP. |
| `📁 10-Cloud-Docker` | Reporte de Docker | Métricas de reproducibilidad y automatización en la nube mediante docker-compose. |

---

## 🛠️ Herramientas y Tecnologías Globales

* **Lenguajes de Programación:** Python / C (Lógica de Servidores y Microservicios), JavaScript / HTML5 (Frontend PWA & Dashboards).
* **Infraestructura Multi-Cloud:** Microsoft Azure (Virtual Machines), Amazon Web Services (VPC / EC2 Compute Elastic), Google Cloud Platform (Compute Engine).
* **Contenerización y Redes:** Docker, Docker Compose V2, Linux (Ubuntu Server).

---

Daniela Maldonado — Escuela Superior de Cómputo (ESCOM - IPN).
Aúnn estoy en proceso de desarrollo de dichas prácticas :)

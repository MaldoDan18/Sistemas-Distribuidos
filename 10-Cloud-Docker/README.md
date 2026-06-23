
# Práctica 10 - Cloud Docker

Mini reporte de despliegue y reproducibilidad de las prácticas 06, 07 y 08 en contenedores.

## Implementación

Se actualizó la máquina base Ubuntu, se instaló Docker y se preparó el despliegue multi-contenedor para ejecutar cada práctica en nube de forma consistente.

### Entorno base y Comandos Útiles

#### 1. Actualización de la Instancia Base (Ubuntu)
Antes de instalar cualquier dependencia, se ejecutó la actualización de los índices de paquetes y el sistema operativo para garantizar la estabilidad del demonio de Docker:

```bash
sudo apt update && sudo apt upgrade -y

```

#### 2. Instalación de Docker y Orquestador Docker Compose

Se instaló el motor de contenedores junto con la herramienta de orquestación para el manejo de arquitecturas multi-contenedor:

```bash
# Instalación del motor de Docker y Docker Compose
sudo apt install -y docker.io docker-compose-v2

# Habilitación e inicialización del servicio
sudo systemctl enable --now docker

# Agregar el usuario al grupo Docker para evitar el uso de sudo en cada comando
sudo usermod -aG docker $USER

```

#### 3. Mecanismos de Conexión Segura (SSH) por Proveedor de Nube

Dependiendo de la plataforma de nube seleccionada y de la imagen base (AMI/Imagen de origen), los usuarios por defecto y los métodos de acceso varían de la siguiente forma:

* **Microsoft Azure (`azureuser`):**
```bash
ssh -i "mv-practicas_key.pem" azureuser@<IP_PUBLICA_AZURE>

```


* **Amazon Web Services (`ubuntu` / `ec2-user`):**
* *Nota:* Para las instancias basadas en imágenes oficiales de Ubuntu Server se utiliza el usuario maestro `ubuntu`. Para distribuciones tipo Amazon Linux se invoca `ec2-user`.


```bash
ssh -i "Key-Practica.pem" ubuntu@<IP_PUBLICA_AWS>

```


* **Google Cloud Platform (gcp-cli / IAM):**
* La autenticación e inicio de sesión seguro se realiza de forma directa mediante el túnel e interfaz nativa de la CLI de la plataforma para administrar las credenciales del proyecto sin llaves manuales expuestas:


```bash
gcloud compute ssh <NOMBRE_DE_LA_VM> --zone=<ZONA_GEOGRAFICA>

```


#### 4. Despliegue de los Proyectos

Para la compilación local de los Dockerfiles y el levantamiento de las aplicaciones en segundo plano se utilizó la siguiente instrucción en la raíz de cada repositorio:

```bash
docker compose up -d --build

```

### Repositorios GitHub

* **Práctica 06:** [https://github.com/MaldoDan18/SD-Practica06.git](https://github.com/MaldoDan18/SD-Practica06.git)
* **Práctica 07:** [https://github.com/MaldoDan18/SD-Practica07.git](https://github.com/MaldoDan18/SD-Practica07.git)
* **Práctica 08:** [https://github.com/MaldoDan18/SD-Practica08.git](https://github.com/MaldoDan18/SD-Practica08.git)

---

## Despliegue en nube

### Práctica 06

* **Azure:** http://68.155.146.102/
* **AWS:** http://18.217.40.99
* **GCP:** http://35.234.184.246/

### Práctica 07

* **Azure - Dashboard:** http://158.23.183.17/dashboard
* **Azure - PWA:** http://158.23.183.17
* **AWS - Dashboard:** http://18.189.26.99/dashboard
* **AWS - PWA:** http://18.189.26.99/
* **GCP - Dashboard:** http://34.182.238.238/dashboard
* **GCP - PWA:** http://34.182.238.238

### Práctica 08

* **Azure - Dashboard:** http://68.155.146.164/
* **Azure - PWA:** http://68.155.146.164/pwa/index.html
* **AWS - Dashboard:** http://3.134.77.191/
* **AWS - PWA:** http://3.134.77.191/pwa/index.html
* **GCP - Dashboard:** http://8.228.101.127/
* **GCP - PWA:** http://8.228.101.127/pwa/index.html

---

## Nota operativa

En la **Práctica 08**, el servidor web y el proxy inverso actúan como una API Gateway distribuida que soporta redirección interna transparente entre el dashboard y la PWA. Debido a esto, ambos módulos web quedan completamente unificados y disponibles bajo la resolución del mismo dominio o dirección IP pública asignada por el proveedor.


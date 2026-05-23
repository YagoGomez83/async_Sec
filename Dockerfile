# 1. Imagen base oficial, versión slim para reducir superficie de ataque
FROM python:3.11-slim

# 2. Metadatos
LABEL maintainer="DevSecOps Engineer"

# 3. Evitar que Python escriba archivos .pyc y forzar el volcado de logs (stdout)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 4. Establecer directorio de trabajo dentro del contenedor
WORKDIR /app

# 5. Instalar dependencias del sistema operativo (Nmap es requerido por nuestro worker)
RUN apt-get update && apt-get install -y --no-install-recommends \
    nmap \
    && rm -rf /var/lib/apt/lists/*

# 6. Copiar requerimientos e instalarlos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 7. Copiar el código fuente
COPY . .

# 8. Seguridad: Crear un usuario no-root para ejecutar la aplicación
RUN adduser --disabled-password --gecos "" secuser
USER secuser
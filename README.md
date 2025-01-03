# Git Large Repository Uploader

Este script de Python automatiza la subida de repositorios Git grandes a GitHub (u otros remotos), sorteando las limitaciones de tamaño y tiempo de subida. Divide los archivos en lotes pequeños, crea commits individuales para cada lote y los sube gradualmente al remoto.

## Propósito

Superar las restricciones de GitHub al subir repositorios de gran tamaño o con un historial extenso, evitando errores por exceder los límites de tamaño de commit o tiempo de subida.

## Funcionamiento

El script realiza los siguientes pasos:

1.  **Excluye archivos grandes:** Se configuran tamaños máximos para archivos individuales y lotes de archivos. Los archivos que superan el tamaño máximo individual se excluyen de los commits.
2.  **Agrupación en lotes:** Los archivos restantes se agrupan en lotes más pequeños, según el tamaño máximo de lote configurado.
3.  **Creación de commits:** Se crea un commit individual para cada lote de archivos.
4.  **Subida gradual:** Los commits se envían al remoto uno por uno, con pausas entre cada intento y utilizando la opción `--force-with-lease` para evitar sobrescribir cambios remotos.

## Configuración

Las siguientes variables se configuran al inicio del script:

- `local_dir`: Ruta a la carpeta del repositorio local.
- `TAMAÑO_MAX_ARCHIVO_MB`: Tamaño máximo permitido para un archivo individual (en MB).
- `TAMAÑO_MAX_LOTE_MB`: Tamaño máximo permitido para un lote de archivos (en MB).
- `AUTOR`: Objeto `Actor` de Git con la información del autor del commit (nombre y correo electrónico).

## Uso

1.  Asegúrate de tener Python instalado y las dependencias requeridas (`gitpython`, `pathlib`). Puedes instalarlas con: `pip install gitpython pathlib`
2.  Configura las variables al inicio del script según tus necesidades.
3.  Ejecuta el script: `python nombre_del_script.py`

## Consideraciones

- `--force-with-lease`: El uso de esta opción en el push es crucial para evitar sobrescribir commits remotos.
- Pausas entre pushes: Las pausas ayudan a evitar sobrecargar el servidor remoto.
- Archivos grandes: Los archivos que superan `TAMAÑO_MAX_ARCHIVO_MB` se ignoran en los commits. Se recomienda usar Git LFS para gestionar archivos binarios grandes.

## Ejemplo de configuración

```python
local_dir = D:\my obsidian
author_name = leo
author_email = leocasti2@gmail.com
```

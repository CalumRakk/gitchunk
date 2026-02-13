import logging
from pathlib import Path
from typing import List

from send2trash import send2trash

logger = logging.getLogger(__name__)


class FileChunker:
    SUFFIX = ".gc"
    BLOCK_SIZE = 1024 * 1024 * 5

    @classmethod
    def split_file(
        cls,
        file_path: Path,
        chunk_size: int,
    ) -> List[Path]:
        """
        Divide un archivo en trozos de tamaño chunk_size.
        Cada trozo se escribe primero como .tmp y se renombra al finalizar.
        El archivo original se elimina solo si la operación es exitosa.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"El archivo no existe: {file_path}")

        file_size = file_path.stat().st_size
        total_parts = (file_size + chunk_size - 1) // chunk_size
        chunks_creados = []

        logger.info(
            f"Dividiendo {file_path.name} ({file_size / 1024**2:.2f} MB) en {total_parts} trozos."
        )

        try:
            with open(file_path, "rb") as f:
                for i in range(total_parts):
                    part_num = i + 1
                    chunk_name_final = f"{file_path.name}{cls.SUFFIX}.{part_num:03d}"
                    chunk_path_final = file_path.parent / chunk_name_final
                    chunk_path_tmp = chunk_path_final.with_suffix(".tmp")

                    remaining_to_read = chunk_size
                    with open(chunk_path_tmp, "wb") as out_tmp:
                        while remaining_to_read > 0:
                            to_read = min(cls.BLOCK_SIZE, remaining_to_read)
                            data = f.read(to_read)
                            if not data:
                                break
                            out_tmp.write(data)
                            remaining_to_read -= len(data)

                    if chunk_path_final.exists():
                        send2trash(chunk_path_final)

                    chunk_path_tmp.rename(chunk_path_final)
                    chunks_creados.append(chunk_path_final)
                    logger.debug(f"Trozo generado: {chunk_name_final}")

            file_path.unlink()
            logger.info(f"Proceso completado. Original '{file_path.name}' eliminado.")
            return chunks_creados

        except Exception as e:
            logger.error(f"Error durante el split de {file_path.name}: {e}")
            for c in chunks_creados:
                if c.exists():
                    c.unlink()
            raise e

    @classmethod
    def join_files(cls, folder: Path):
        """
        Escanea la carpeta buscando archivos .gc.### y los une.
        Utiliza un archivo .tmp para la reconstrucción antes de renombrar al original.
        """
        grupos = {}
        for chunk_file in folder.rglob(f"*{cls.SUFFIX}.[0-9][0-9][0-9]"):
            # Obtenemos 'video.mp4' de 'video.mp4.gc.001'
            base_name = chunk_file.name.split(cls.SUFFIX)[0]
            target_path = chunk_file.parent / base_name

            if target_path not in grupos:
                grupos[target_path] = []
            grupos[target_path].append(chunk_file)

        if not grupos:
            logger.info("No se encontraron archivos fragmentados para unir.")
            return

        for target_path, chunks in grupos.items():
            chunks.sort()  # Ordenar por el número de extensión (.001, .002...)

            # Si el último trozo es .005, deberíamos tener 5 archivos.
            last_chunk_num = int(chunks[-1].suffix.split(".")[-1])
            if len(chunks) != last_chunk_num:
                logger.error(
                    f"Error: Faltan trozos para {target_path.name}. "
                    f"Se esperaban {last_chunk_num} y hay {len(chunks)}."
                )
                continue

            target_path_tmp = target_path.with_suffix(".tmp")

            logger.info(
                f"Restaurando '{target_path.name}' desde {len(chunks)} trozos..."
            )

            try:
                with open(target_path_tmp, "wb") as out_file:
                    for chunk_p in chunks:
                        with open(chunk_p, "rb") as part_file:
                            while True:
                                data = part_file.read(cls.BLOCK_SIZE)
                                if not data:
                                    break
                                out_file.write(data)

                # Verificación básica: ¿El temporal existe y tiene datos?
                if target_path_tmp.stat().st_size == 0:
                    raise Exception("El archivo resultante está vacío.")

                # Paso final: Renombrar temporal a original y borrar trozos
                if target_path.exists():
                    send2trash(target_path)  # Si ya existía uno viejo, lo quitamos

                target_path_tmp.rename(target_path)

                for chunk_p in chunks:
                    chunk_p.unlink()

                logger.info(f"¡Archivo '{target_path.name}' restaurado exitosamente!")

            except Exception as e:
                logger.error(f"Fallo al unir {target_path.name}: {e}")
                if target_path_tmp.exists():
                    target_path_tmp.unlink()
                raise e

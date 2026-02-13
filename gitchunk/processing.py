from pathlib import Path
from typing import List

from .constants import MAX_BATCH_SIZE_BYTES, MAX_FILE_SIZE_BYTES, MAX_TOTAL_SIZE_ALLOWED
from .schemas import Batchs, FilesFiltered, GitStatus


def filter_files_from_status(repo_path: Path, git_status: GitStatus) -> FilesFiltered:
    """
    Analiza todo lo que es diferente al último commit y lo clasifica por peso.
    """
    # Todo lo que Git detecta como cambio de contenido o archivo nuevo
    pending_content = (
        git_status["unstaged"]["modified"] + git_status["unstaged"]["untracked"]
    )

    # Lo que Git detecta que ya no está
    deleted_files = git_status["unstaged"]["deleted"]

    files_to_batch = []
    files_to_chunk = []
    invalid_files = []

    for file_rel in pending_content:
        full_path = repo_path / file_rel

        # Doble comprobación: si el archivo desapareció justo ahora, saltar
        if not full_path.exists():
            continue

        size = full_path.stat().st_size

        if size <= MAX_FILE_SIZE_BYTES:
            files_to_batch.append((file_rel, size))
        elif size <= MAX_TOTAL_SIZE_ALLOWED:
            files_to_chunk.append((file_rel, size))
        else:
            invalid_files.append((file_rel, size, f"Excede el límite (360MB)"))

    # Ordenar por tamaño para que los commits sean equilibrados
    files_to_batch.sort(key=lambda x: x[1])

    return FilesFiltered(
        files_to_batch=files_to_batch,
        files_to_chunk=files_to_chunk,
        deleted_files=deleted_files,
        invalid_files=invalid_files,
    )


def batch_files(files: FilesFiltered) -> Batchs:
    batchs: List[list] = []

    batch_size_bytes = 0
    batch_current = []

    for file, size in files.files_to_batch:
        if batch_size_bytes + size > MAX_BATCH_SIZE_BYTES:
            if batch_current:
                batchs.append(batch_current)

            batch_current = [file]
            batch_size_bytes = size
        else:
            batch_current.append(file)
            batch_size_bytes += size

    if batch_current:
        batchs.append(batch_current)

    return Batchs(to_add=batchs, to_delete=files.deleted_files)


def apply_file_transformations(
    game_path: Path, files_filtered: FilesFiltered
) -> FilesFiltered:
    """
    Realiza las transformaciones físicas (como el chunking) y devuelve un
    nuevo FilesFiltered actualizado para ser procesado por batch_files.
    """
    from gitchunk.chunking import FileChunker

    # Trabajamos sobre una copia para no mutar el original inesperadamente
    final_files = files_filtered.model_copy(deep=True)
    chunk_limit = 90 * 1024 * 1024
    has_transformed = False

    for file_rel, size in files_filtered.files_to_chunk:
        full_path = game_path / file_rel

        created_chunks = FileChunker.split_file(full_path, chunk_limit)

        final_files.deleted_files.append(str(file_rel))
        for chunk_path in created_chunks:
            rel_chunk = chunk_path.relative_to(game_path).as_posix()
            final_files.files_to_batch.append((rel_chunk, chunk_path.stat().st_size))

        has_transformed = True

    if has_transformed:
        restore_path = game_path / "GITCHUNK_RESTORE.txt"
        restore_path.write_text("Usa 'gitchunk restore .' para unir los archivos.")
        final_files.files_to_batch.append(
            (restore_path.name, restore_path.stat().st_size)
        )

    final_files.files_to_chunk = []
    return final_files

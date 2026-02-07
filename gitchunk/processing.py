from pathlib import Path
from typing import List

from .constants import MAX_FILE_SIZE_BYTES
from .schemas import Batchs, FilesFiltered, GitStatus


def filter_files_from_status(repo_path: Path, git_status: GitStatus) -> FilesFiltered:
    files = git_status["unstaged"]["modified"] + git_status["unstaged"]["untracked"]

    files_to_batch = []
    invalid_files = []

    for file in files:
        path = repo_path / file
        size = path.stat().st_size
        if size > MAX_FILE_SIZE_BYTES:
            invalid_files.append((file, size, "exceeds maximum size"))
        else:
            files_to_batch.append((file, size))

    files_to_batch.sort(key=lambda x: x[1])
    return FilesFiltered(
        files_to_batch=files_to_batch,
        deleted_files=git_status["unstaged"]["deleted"],
        invalid_files=invalid_files,
    )


def batch_files(files: FilesFiltered) -> Batchs:
    batchs: List[list] = []

    batch_size_bytes = 0
    batch_current = []

    for file, size in files["files_to_batch"]:
        if batch_size_bytes + size > MAX_FILE_SIZE_BYTES:
            if batch_current:
                batchs.append(batch_current)

            batch_current = [file]
            batch_size_bytes = size
        else:
            batch_current.append(file)
            batch_size_bytes += size

    if batch_current:
        batchs.append(batch_current)

    return Batchs(to_add=batchs, to_delete=files["deleted_files"])

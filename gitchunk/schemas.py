from enum import Enum, auto
from typing import List, TypedDict

from git import Optional, Tuple
from pydantic import BaseModel


class Batchs(TypedDict):
    to_add: List[List[str]]
    to_delete: List[str]


class FilesFiltered(BaseModel):
    files_to_batch: List[Tuple[str, int]]  # Archivos normales (< 90MB)
    files_to_chunk: List[Tuple[str, int]]  # Archivos para fragmentar (90MB - 360MB)
    deleted_files: List[str]
    invalid_files: List[Tuple[str, int, str]]  # Archivos realmente prohibidos (> 360MB)


class CheckUserEmail(TypedDict):
    user_name: Optional[str]
    user_email: Optional[str]
    is_configured: bool


class FileRename(TypedDict):
    old_name: str
    new_name: str


class StatusStaged(TypedDict):
    added: List[str]
    modified: List[str]
    deleted: List[str]
    renamed: List[FileRename]


class StatusUnstaged(TypedDict):
    modified: List[str]
    deleted: List[str]
    untracked: List[str]


class GitStatus(TypedDict):
    staged: StatusStaged
    unstaged: StatusUnstaged


class TokenInfo(BaseModel):
    username: str
    scopes: List[str]
    is_valid: bool


class SyncStatus(Enum):
    NO_REMOTE = auto()  # El remoto no tiene la rama (Repo nuevo)
    EQUAL = auto()  # Estamos sincronizados
    AHEAD = auto()  # Local tiene commits nuevos (RESUME)
    BEHIND = auto()  # Remoto tiene commits nuevos (UPDATE)
    DIVERGED = auto()  # Historias incompatibles (CONFLICT)

from typing import List, TypedDict

from git import Optional, Tuple
from pydantic import BaseModel


class Batchs(TypedDict):
    to_add: List[List[str]]
    to_delete: List[str]


class FilesFiltered(TypedDict):
    files_to_batch: List[Tuple[str, int]]
    deleted_files: List[str]
    invalid_files: List[Tuple[str, int, str]]


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

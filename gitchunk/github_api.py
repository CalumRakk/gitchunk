import json
import logging
from urllib.error import HTTPError

import requests

from gitchunk.schemas import TokenInfo

logger = logging.getLogger(__name__)


class GitHubClient:
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def verify_token(self) -> TokenInfo:
        """
        Verifica si el token es válido y devuelve información sobre el usuario y permisos.
        """
        url = f"{self.base_url}/user"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()

            data = response.json()

            scopes_header = response.headers.get("X-OAuth-Scopes", "")
            scopes = (
                [s.strip() for s in scopes_header.split(",")] if scopes_header else []
            )

            return TokenInfo(username=data["login"], scopes=scopes, is_valid=True)

        except HTTPError as e:
            if e.response.status_code == 401:
                raise ValueError("El token proporcionado no es válido o ha expirado.")
            elif e.response.status_code == 403:
                raise ValueError(
                    "Acceso denegado por GitHub (Posible Rate Limit o SSO requerido)."
                )
            raise e

    def get_authenticated_user(self) -> str:
        """Obtiene el 'login' (username) del dueño del token."""
        url = f"{self.base_url}/user"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        data = response.json()
        return data["login"]

    def repo_exists(self, owner: str, repo_name: str) -> bool:
        """Comprueba si un repositorio ya existe."""
        try:
            url = f"{self.base_url}/repos/{owner}/{repo_name}"
            response = requests.get(url, headers=self.headers)
            return response.status_code == 200
        except HTTPError as e:
            if e.code == 404:
                return False
            raise e

    def create_private_repo(self, repo_name: str) -> str:
        """Crea un repositorio privado y devuelve su URL clonable con token."""
        payload = {
            "name": repo_name,
            "private": True,
            "description": "Backup automático creado por Gitchunk",
        }
        data = json.dumps(payload).encode("utf-8")

        url = f"{self.base_url}/user/repos"
        response = requests.post(url, data=data, headers=self.headers)
        response.raise_for_status()
        data = response.json()
        return data["clone_url"]

    def get_auth_url(self, clean_url: str) -> str:
        """
        Transforma una URL limpia en una con token para usar en el comando push.
        Ejemplo: https://github.com/owner/repo.git -> https://token@github.com/owner/repo.git
        """
        return clean_url.replace("https://", f"https://{self.token}@")

    def get_or_create_repo(self, repo_name: str) -> str:
        """Obtiene o crea un repositorio privado en GitHub. Y devuelve su URL remota."""
        username = self.get_authenticated_user()
        if self.repo_exists(username, repo_name):
            logger.info(f"El repositorio '{repo_name}' ya existe en GitHub.")
            return f"https://github.com/{username}/{repo_name}.git"
        else:
            logger.info(f"Creando nuevo repositorio privado: '{repo_name}'")
            return self.create_private_repo(repo_name)

    def set_default_branch(self, repo_name: str, branch_name: str) -> bool:
        """
        Cambia la rama por defecto del repositorio en GitHub.
        IMPORTANTE: La rama debe existir en el remoto ANTES de llamar a esto.
        """
        username = self.get_authenticated_user()
        url = f"{self.base_url}/repos/{username}/{repo_name}"

        payload = {"default_branch": branch_name}

        try:
            response = requests.patch(url, json=payload, headers=self.headers)
            response.raise_for_status()
            logger.info(f"Rama por defecto cambiada a '{branch_name}' en GitHub.")
            return True
        except Exception as e:
            logger.warning(
                f"No se pudo cambiar la rama por defecto a {branch_name}: {e}"
            )
            return False

    def get_remote_tags(self, owner: str, repo_name: str) -> list[str]:
        """Obtiene la lista de nombres de etiquetas del repositorio.

        Github no garantiza un orden específico, pero suele devolverlas de la más reciente a la más antigua.
        """
        url = f"{self.base_url}/repos/{owner}/{repo_name}/tags"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return [tag["name"] for tag in response.json()]
        return []

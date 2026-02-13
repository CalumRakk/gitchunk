import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from gitchunk.config import ConfigManager
from gitchunk.game.manager import GameManager
from gitchunk.github_api import GitHubClient
from gitchunk.logging_config import setup_logging

from . import __version__

app = typer.Typer(
    help="Herramienta CLI para archivar juegos en GitHub automáticamente.",
    add_completion=False,
)
profile_app = typer.Typer(help="Gestión de perfiles de usuario y tokens.")
app.add_typer(profile_app, name="profile")

console = Console()
logger = logging.getLogger(__name__)


def version_callback(value: bool):
    if value:
        console.print(f"gitchunk [bold cyan]v{__version__}[/bold cyan]")
        raise typer.Exit()


@app.callback()
def main(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Muestra logs detallados de depuración."
    ),
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Muestra la versión de la aplicación.",
    ),
):
    """
    Configuración global antes de ejecutar cualquier comando.
    """
    level = logging.DEBUG if verbose else logging.INFO
    setup_logging(level=level)


@profile_app.command("create")
def create_profile(
    name: str = typer.Option(
        ...,
        prompt="Nombre del perfil",
        help="Un nombre único para identificar este token (ej: personal, trabajo).",
    ),
    token: str = typer.Option(
        ...,
        prompt="GitHub Token",
        hide_input=True,
        help="Tu Personal Access Token (classic) de GitHub.",
    ),
):
    """
    Crea un nuevo perfil validando el token con GitHub.
    """
    console.print(
        f"[bold yellow]Validando token para el perfil '{name}'...[/bold yellow]"
    )

    try:
        client = GitHubClient(token)
        info = client.verify_token()

        table = Table(title="Token Verificado Exitosamente", show_header=False)
        table.add_row("Usuario", f"[green]{info.username}[/green]")
        table.add_row(
            "Scopes Detectados",
            ", ".join(info.scopes) if info.scopes else "[red]Ninguno (Cuidado)[/red]",
        )
        table.add_row("Válido", "Sí")
        console.print(table)

        config = ConfigManager()
        is_first = config.add_profile(name, token)

        if is_first:
            console.print(
                f"[bold green]Perfil '{name}' guardado y establecido como predeterminado.[/bold green]"
            )
        else:
            console.print(
                f"[bold green]Perfil '{name}' guardado exitosamente.[/bold green]"
            )

    except Exception as e:
        console.print(f"[bold red]Error al validar/guardar el perfil:[/bold red] {e}")
        raise typer.Exit(code=1)


@profile_app.command("list")
def list_profiles():
    """
    Lista todos los perfiles configurados.
    """
    config = ConfigManager()
    profiles = config.list_profiles()

    if not profiles:
        console.print("[yellow]No hay perfiles configurados.[/yellow]")
        console.print("Usa [bold]gitchunk profile create[/bold] para añadir uno.")
        return

    table = Table(title="Perfiles Gitchunk")
    table.add_column("Nombre", style="cyan")
    table.add_column("Estado", justify="center")

    for name, is_default in profiles.items():
        status = "[green bold](Default)[/green bold]" if is_default else ""
        table.add_row(name, status)

    console.print(table)


@profile_app.command("use")
def switch_profile(
    name: str = typer.Argument(..., help="Nombre del perfil a activar.")
):
    """
    Cambia el perfil predeterminado.
    """
    config = ConfigManager()
    try:
        config.set_default(name)
        console.print(
            f"[green]Ahora usando el perfil '[bold]{name}[/bold]' por defecto.[/green]"
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)


@profile_app.command("remove")
def remove_profile(
    name: str = typer.Argument(..., help="Nombre del perfil a eliminar.")
):
    """
    Elimina un perfil de la configuración local.
    """
    config = ConfigManager()
    if not typer.confirm(f"¿Estás seguro de que quieres borrar el perfil '{name}'?"):
        raise typer.Abort()

    config.remove_profile(name)
    console.print(f"[green]Perfil '{name}' eliminado.[/green]")


@app.command()
def archive(
    path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Ruta a la carpeta del juego que quieres archivar.",
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Nombre del perfil a usar. Si se omite, usa el default.",
    ),
    recursive: bool = typer.Option(
        False,
        "--recursive",
        "-r",
        help="Busca juegos en subcarpetas de la carpeta principal.",
    ),
):
    """
    Analiza, limpia y sube una carpeta de juego a un repositorio privado de GitHub.
    """
    console.rule(f"[bold blue]Gitchunk Archive: {path.name}[/bold blue]")

    config = ConfigManager()
    try:
        token = config.get_token(profile)
        profile_used = profile or config.data.default_profile
        console.print(f"Usando perfil: [cyan]{profile_used}[/cyan]")
    except ValueError as e:
        console.print(f"[bold red]Error de Configuración:[/bold red] {e}")
        console.print(
            "Ejecuta [bold]gitchunk profile create[/bold] para configurar tu acceso."
        )
        raise typer.Exit(code=1)

    try:
        manager = GameManager(acces_token=token)
        target = path.glob("*") if recursive else [path]
        for game_path in target:
            if not game_path.is_dir() or game_path.name.startswith("."):
                continue

            with console.status(
                "[bold green]Procesando juego... (Escaneando, Limpiando, Git)[/bold green]",
                spinner="dots",
            ):
                try:
                    manager.process_game(game_path)
                except Exception as e:
                    logger.error(f"Error al procesar '{game_path}': {e}")
                    continue

            console.print(
                Panel.fit(
                    f"[bold green]¡Éxito![/bold green]\nEl juego en '{path.name}' ha sido archivado correctamente.",
                    title="Tarea Completada",
                    border_style="green",
                )
            )

    except Exception as e:
        logger.exception("Error crítico durante el archivado")
        console.print(f"[bold red]Fallo durante el proceso:[/bold red] {e}")
        raise typer.Exit(code=1)


@app.command()
def restore(
    path: Path = typer.Argument(
        Path("."),
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Ruta a la carpeta donde quieres restaurar los archivos fragmentados.",
    )
):
    """
    Busca archivos fragmentados (.gc.###) y los vuelve a unir en sus originales.
    """
    console.rule(f"[bold blue]Gitchunk Restore: {path.name}[/bold blue]")

    try:
        from gitchunk.chunking import FileChunker

        with console.status(
            "[bold green]Escaneando y reconstruyendo archivos...[/bold green]",
            spinner="bouncingBar",
        ):
            FileChunker.join_files(path)

        console.print(
            Panel.fit(
                f"[bold green]¡Restauración completada![/bold green]\n"
                f"Se han procesado todos los archivos fragmentados en [cyan]{path.name}[/cyan].",
                title="Éxito",
                border_style="green",
            )
        )

    except Exception as e:
        console.print(f"[bold red]Fallo durante la restauración:[/bold red] {e}")
        raise typer.Exit(code=1)


def run_script():
    """Entrada para setup.py"""
    try:
        app()
    except Exception as e:
        raise e


if __name__ == "__main__":
    app()

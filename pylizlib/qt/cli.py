
from pathlib import Path
import typer

from pylizlib.qt.scripts import exec_gen_qrc, exec_gen_res_py, exec_gen_css_py

app = typer.Typer(help="Utility per la gestione delle risorse Qt e CSS.")


@app.command("gen-qrc")
def gen_qrc(
        qrc_path: Path = typer.Option(..., "--qrc-path", help=".QRC file path to generate"),
        res_dir: list[Path] = typer.Option(..., "--res-dir", help="Add resource directories to qrc file"),
):

    if not res_dir:
        typer.echo("Errore: devi specificare almeno una directory con --res-dir", err=True)
        raise typer.Exit(code=1)

    for path in res_dir:
        if not path.is_dir():
            typer.echo(f"Error: folder {path} dont exist.", err=True)
            raise typer.Exit(code=1)

    typer.echo(f"QRC generation in: {qrc_path}")
    typer.echo("Folder resources:")
    for path in res_dir:
        typer.echo(f" - {path}")
    exec_gen_qrc(qrc_path, res_dir)


@app.command("gen-res-ids")
def gen_res_ids(
        qrc_path: Path = typer.Argument(..., help="Path del file .qrc (deve esistere)"),
        py_file: Path = typer.Argument(..., help="Path del file Python da generare (può non esistere)"),
        class_name: str = typer.Option("ResourcesIds", help="Nome della classe da generare nel file Python")
):
    if not qrc_path.is_file():
        typer.echo(f"Errore: il file '{qrc_path}' non esiste.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Generazione identificatori risorse da '{qrc_path}' in '{py_file}'")
    exec_gen_res_py(qrc_path, py_file, class_name)


@app.command("gen-css-py")
def gen_css_py(
        css_dir: Path = typer.Argument(..., help="Path della cartella CSS (deve esistere)"),
        py_file: Path = typer.Argument(..., help="Path del file Python da generare (può non esistere)")
):
    if not css_dir.is_dir():
        typer.echo(f"Errore: la cartella '{css_dir}' non esiste.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Generazione file Python da CSS nella cartella '{css_dir}' in '{py_file}'")
    exec_gen_css_py(css_dir, py_file)

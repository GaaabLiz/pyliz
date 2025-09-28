from pathlib import Path

import typer

from pylizlib.core.app.configini import CfgPath
from pylizlib.core.app.pytoml import PyProjectToml
from pylizlib.core.os.path import PathMatcher

app = typer.Typer(help="General utility scripts.")


@app.command("expFileList")
def exp_file_list(
        input: Path = typer.Argument(..., help="Input path to scan"),
        output: Path = typer.Argument(..., help="Output path where to save the file"),
        file_name: str = typer.Argument(..., help="Name of the file to save"),
        recursive: bool = typer.Option(False, "--recursive", help="Enable recursive scan"),
):
    matcher = PathMatcher()
    matcher.load_path(input, recursive)
    matcher.export_file_list(output, file_name)


@app.command("iniDup")
def ini_dup(
        input: Path = typer.Argument(..., help="Input path to scan"),
        sections: bool = typer.Option(False, "--sections", help="Enable search for duplicate sections"),
        keys: bool = typer.Option(False, "--keys", help="Enable search for duplicate keys"),
):
    cfg = CfgPath(input)
    cfg.check_duplicates(keys, sections)


@app.command("gen-project-py")
def gen_project_py(
        pyproject_path: Path = typer.Argument(..., help="Path to the pyproject.toml file"),
        py_file: Path = typer.Argument(..., help="Path to the Python file to update"),
):
    try:
        toml = PyProjectToml(pyproject_path)
        toml.gen_project_py(py_file)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)



@app.command("temp")
def temp():
    typer.echo("This is a temporary command.")


if __name__ == "__main__":
    app()
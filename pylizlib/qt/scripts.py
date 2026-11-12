import keyword
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import rich


def _python_identifier(value: str, fallback: str, used: set[str] | None = None) -> str:
    value = re.sub(r"\W", "_", value, flags=re.UNICODE).strip("_")
    if not value:
        value = fallback
    if value[0].isdigit():
        value = f"_{value}"
    if not value.isidentifier():
        value = fallback
    if keyword.iskeyword(value):
        value = f"{value}_"

    if used is not None:
        base = value
        suffix = 2
        while value in used:
            value = f"{base}_{suffix}"
            suffix += 1
        used.add(value)
    return value


def _write_python_atomically(output_file_path: Path, source: str) -> None:
    output_file_path = Path(output_file_path)
    compile(source, str(output_file_path), "exec")
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_file_path.parent,
            prefix=f".{output_file_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(source)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, output_file_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def exec_gen_qrc(qrc_path: Path, dir_list: list[Path]) -> None:
    qrc_path = Path(qrc_path)
    qrc_parent = qrc_path.parent.resolve()
    root = ET.Element("RCC")

    for directory in dir_list:
        directory = Path(directory).resolve()
        if not directory.is_dir():
            continue

        resource = ET.SubElement(root, "qresource", {"prefix": directory.name})
        for file in sorted(directory.rglob("*")):
            if file.is_file():
                relative_path = Path(os.path.relpath(file, qrc_parent)).as_posix()
                ET.SubElement(resource, "file").text = relative_path

    ET.indent(root, space="  ")
    xml_data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    ET.fromstring(xml_data)

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=qrc_parent,
            prefix=f".{qrc_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(xml_data)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, qrc_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def exec_gen_res_py(qrc_file_path, output_file_path, main_class_name="ResourcesIds"):
    # Parsing del file .qrc
    tree = ET.parse(qrc_file_path)
    root = tree.getroot()

    # Inizializzazione del contenuto del file
    main_class_name = _python_identifier(main_class_name, "ResourcesIds")
    content = [
        f"class {main_class_name}:",
        '    """Class containing all application\'s resources."""',
    ]

    # Dizionario per tenere traccia delle risorse per prefix
    prefix_resources = {}

    # Elaborazione delle risorse
    for qresource in root.findall("qresource"):
        prefix = qresource.get("prefix", "")

        # Inizializza la lista per questo prefix se non esiste
        if prefix not in prefix_resources:
            prefix_resources[prefix] = []

        for file_elem in qresource.findall("file"):
            file_path = (file_elem.text or "").strip()
            public_path = file_elem.get("alias") or file_path
            public_path = public_path.replace("\\", "/").strip("/")
            prefix_path = prefix.replace("\\", "/").strip("/")
            path_parts = [part for part in (prefix_path, public_path) if part]
            resource_path = ":/" + "/".join(path_parts)

            # Crea un nome di variabile adatto
            base_name = Path(public_path).stem
            used_names = {line.split(" = ", 1)[0].strip() for line in prefix_resources[prefix]}
            var_name = _python_identifier(base_name.upper(), "RESOURCE", used_names)

            # Aggiungi la risorsa alla lista del prefix corrispondente
            prefix_resources[prefix].append(f"        {var_name} = {resource_path!r}")

    # Genera classi per ogni prefix
    used_class_names = set()
    for prefix, resources in prefix_resources.items():
        class_name = _python_identifier(prefix or "Root", "Resources", used_class_names)

        # Aggiungi la definizione della classe
        content.append("")
        content.append(f"    class {class_name}:")
        class_docstring = f"Resource with prefix {prefix!r}"
        content.append(f"        {class_docstring!r}")
        content.append("")

        # Aggiungi tutte le risorse per questo prefix
        content.extend(resources)

    _write_python_atomically(Path(output_file_path), "\n".join(content) + "\n")

    rich.print(f"Resources id python file generated in: {output_file_path}")


def exec_gen_css_py(css_folder: Path, output_file: Path):
    if not css_folder.is_dir():
        raise ValueError(f"{css_folder} is not a valid directory")

    css_files = sorted(css_folder.glob("*.css"))
    lines = ["# AUTOGENERATED\n"]
    used_names = set()

    for css_file in css_files:
        variable_name = _python_identifier(css_file.stem, "STYLE", used_names)
        css_content = css_file.read_text(encoding="utf-8")
        lines.append(f"{variable_name} = {css_content!r}\n")

    _write_python_atomically(output_file, "\n".join(lines))

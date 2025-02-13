import argparse

from pylizlib.config.cfgutils import CfgPath
from pylizlib.os.pathMatcher import PathMatcher


def hello(args):
    """Saluta l'utente"""
    print(f"Ciao, {args.name}!")


def add(args):
    """Somma due numeri"""
    result = args.a + args.b
    print(f"Risultato: {result}")

def exp_file_list(args):
    matcher = PathMatcher()
    matcher.load_path(args.input, args.recursive)
    matcher.export_file_list(args.output, args.fileName)

def ini_dup(args):
    cfg = CfgPath(args.input)
    cfg.check_duplicates(args.keys, args.sections)


def main():
    parser = argparse.ArgumentParser(prog="pyliz", description="Un CLI con più comandi")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Comando 'hello'
    parser_hello = subparsers.add_parser("hello", help="Saluta un utente")
    parser_hello.add_argument("--name", type=str, default="Mondo", help="Il nome da salutare")
    parser_hello.set_defaults(func=hello)

    # Comando 'add'
    parser_add = subparsers.add_parser("add", help="Somma due numeri")
    parser_add.add_argument("a", type=int, help="Primo numero")
    parser_add.add_argument("b", type=int, help="Secondo numero")
    parser_add.set_defaults(func=add)

    # Comando 'expFileList'
    parser_add = subparsers.add_parser("expFileList", help="Export the list of files relative a selected path in txt file")
    parser_add.add_argument("input", type=str, help="Input path to scan")
    parser_add.add_argument("output", type=str, help="Output path where to save the file")
    parser_add.add_argument("fileName", type=str, help="Name of the file to save")
    parser_add.add_argument("recursive", action="store_true", help="Enable recursive scan")
    parser_add.set_defaults(func=exp_file_list)

    # Comando 'iniDup'
    parser_add = subparsers.add_parser("iniDup", help="Find duplicate keys/sections inside ini files")
    parser_add.add_argument("input", type=str, help="Input path to scan")
    parser_add.add_argument("sections", action="store_true", help="Enable search for duplicate sections")
    parser_add.add_argument("keys", action="store_true", help="Enable search for duplicate keys")
    parser_add.set_defaults(func=ini_dup)

    # Parsing degli argomenti
    args = parser.parse_args()

    # Esegui la funzione corrispondente al comando scelto
    args.func(args)


if __name__ == "__main__":
    main()

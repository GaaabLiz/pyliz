import argparse


def hello(args):
    """Saluta l'utente"""
    print(f"Ciao, {args.name}!")


def add(args):
    """Somma due numeri"""
    result = args.a + args.b
    print(f"Risultato: {result}")


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

    # Parsing degli argomenti
    args = parser.parse_args()

    # Esegui la funzione corrispondente al comando scelto
    args.func(args)


if __name__ == "__main__":
    main()

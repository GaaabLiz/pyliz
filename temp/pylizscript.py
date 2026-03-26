from abc import ABC, abstractmethod


class PylizBaseAction(ABC):

    @abstractmethod
    def run(self):
        pass

    @abstractmethod
    def reset(self):
        pass


class PylizScript:

    def __init__(self, name: str):
        self.name = name
        self.commands: list[PylizBaseAction] = []

    def add_command(self, command: PylizBaseAction):
        self.commands.append(command)

    def run_all(self):
        for command in self.commands:
            command.run()
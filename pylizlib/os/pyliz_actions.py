from git import Repo

from pylizlib.model.pyliz_script import PylizBaseAction


class ActionGitClone(PylizBaseAction):

    def __init__(
            self,
            repo: str,
            install_dir: str,
            ignore_if_exists: bool = True,
            logs_dir: str | None = None
    ):
        super().__init__()
        self.repo = repo
        self.install_dir = install_dir
        self.ignore_if_exists = ignore_if_exists
        self.logs_dir = logs_dir

    def run(self):
        Repo.clone_from(self.repo, self.repo)
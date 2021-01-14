import shutil
import os
import sys
import tempfile
from .conda import SimpleConda
from ..default import EOS, GITHUB_ORG, GITHUB_ERSILIA_REPO, CREDENTIALS_JSON, CONFIG_JSON
from .. import ErsiliaBase
from .terminal import run_command
from .versioning import Versioner

INSTALL_LOG_FILE = ".install.log"


class Installer(ErsiliaBase):

    def __init__(self, check_install_log=True, config_json=None, credentials_json=None):
        self.development_path = None
        self._config()
        self._credentials()
        ErsiliaBase.__init__(self, config_json=config_json, credentials_json=credentials_json)
        self.check_install_log = check_install_log
        self.log_file = os.path.join(EOS, INSTALL_LOG_FILE)
        self.log = None
        self.read_log()
        self.versions = Versioner()

    def _package_path(self):
        if self.development_path is None:
            path = os.path.dirname(__file__)
            for _ in range(2):
                path = os.path.split(path)[0]
            if not os.path.exists(os.path.join(path, "setup.py")):
                self.development_path = None
            if not os.path.exists(os.path.join(path, "README.md")):
                self.development_path = None
            if not os.path.exists(os.path.join(path, "CODE_OF_CONDUCT.md")):
                self.development_path = None
            self.development_path = path

    def _config(self):
        dst = os.path.join(EOS, CONFIG_JSON)
        if os.path.exists(dst):
            return
        self._package_path()
        if self.development_path is None:
            src_exists = False
        else:
            src = os.path.join(self.development_path, CONFIG_JSON)
            src_exists = os.path.exists(src)
        if src_exists:
            os.symlink(src, dst)
        else:
            from .download import GitHubDownloader
            gd = GitHubDownloader(overwrite=True)
            gd.download_single(GITHUB_ORG, GITHUB_ERSILIA_REPO, CONFIG_JSON, os.path.join(EOS, CONFIG_JSON))

    def _credentials(self):
        dst = os.path.join(EOS, CREDENTIALS_JSON)
        if os.path.exists(dst):
            return
        self._package_path()
        if self.development_path is None:
            src_exists = False
        else:
            src = os.path.join(self.development_path, CREDENTIALS_JSON)
            src_exists = os.path.exists(src)
        if os.path.exists(src):
            os.symlink(src, dst)
        else:
            from .config import Secrets
            sc = Secrets()
            sc.fetch_from_github()
            if self.development_path is None:
                done = sc.to_credentials(dst)
            else:
                done = sc.to_credentials(src)
                if done:
                    os.symlink(src, dst)

    def write_log(self):
        if self.log is None:
            return
        with open(self.log_file, 'w') as f:
            for l in sorted(self.log):
                f.write(l+"\n")

    def update_log(self, task):
        if self.log is None:
            self.log = {task}
        self.log.update([task])
        self.write_log()

    def read_log(self):
        if not os.path.exists(self.log_file):
            return
        with open(self.log_file, "r") as f:
            self.log = []
            for l in f:
                self.log += [l.rstrip()]
        self.log = set(self.log)

    def remove_log(self):
        if os.path.exists(self.log_file):
            os.remove(self.log_file)

    def _is_done(self, name):
        if not self.check_install_log:
            return False
        if self.log is None:
            pass
        else:
            if name in self.log:
                return True
            else:
                pass
        self.update_log(name)
        return False

    @staticmethod
    def _is_tool(name):
        return shutil.which(name) is not None

    def conda(self):
        if self._is_done("conda"):
            return
        if self._is_tool("conda"):
            return
        run_command("pip install -y conda", quiet=True)

    def git(self):
        if self._is_done("git"):
            return
        if self._is_tool("git"):
            return
        self.conda()
        run_command("conda install -y -q git", quiet=True)

    def rdkit(self):
        if self._is_done("rdkit"):
            return
        try:
            import rdkit
            exists = True
        except ModuleNotFoundError:
            exists = False
        if exists:
            return
        run_command("conda install -c conda-forge -y -q rdkit", quiet=True)

    def config(self):
        if self._is_done("config"):
            return
        if os.path.exists(os.path.join(EOS, CONFIG_JSON)):
            return
        os.makedirs(EOS, exist_ok=True)
        self._package_path()
        dev_path = self.development_path
        if dev_path is not None:
            src = os.path.join(dev_path, CONFIG_JSON)
            dst = os.path.join(EOS, CONFIG_JSON)
            shutil.copyfile(src, dst)
        else:
            from .download import GitHubDownloader
            gd = GitHubDownloader(overwrite=True)
            gd.download_single(self.cfg.HUB.ORG, self.cfg.HUB.PACKAGE, CONFIG_JSON, os.path.join(EOS, CONFIG_JSON))

    def _clone_repo(self, path):
        path_repo = os.path.join(path, self.cfg.HUB.PACKAGE)
        self._package_path()
        dev_path = self.development_path
        if dev_path is not None:
            shutil.copytree(dev_path, path_repo)
        else:
            from .download import GitHubDownloader
            gd = GitHubDownloader(overwrite=True)
            gd.clone(self.cfg.HUB.ORG, self.cfg.HUB.PACKAGE, path_repo)
        return path_repo

    def base_conda(self):
        if self._is_done("base_conda"):
            return
        eos_base_env = self.versions.base_conda_name()
        sc = SimpleConda()
        if sc.exists(eos_base_env):
            return
        tmp_folder = tempfile.mkdtemp()
        tmp_repo = self._clone_repo(tmp_folder)
        tmp_script = os.path.join(tmp_folder, "script.sh")
        tmp_python_script = os.path.join(tmp_folder, "base_intaller.py")
        is_base = sc.is_base()
        if not is_base:
            bash_script = """
            source ${0}/etc/profile.d/conda.sh
            conda deactivate
            """.format(sc.conda_prefix(False))
        else:
            bash_script = ""
        bash_script += """
        source ${0}/etc/profile.d/conda.sh
        """.format(sc.conda_prefix(True))
        bash_script += """
        cd {0}
        conda create -n {1} python={2} -y
        conda activate {1}
        pip install -e .
        python {3}
        conda deactivate
        """.format(
            tmp_repo,
            eos_base_env,
            self.versions.python_version(),
            tmp_python_script
        )
        with open(tmp_script, "w") as f:
            f.write(bash_script)
        python_script = """
        from ersilia.utils.installers import base_installer
        base_installer()
        """
        with open(tmp_python_script, "w") as f:
            lines = python_script.split("\n")
            for l in lines:
                f.write(l[8:]+"\n")
        run_command("bash {0}".format(tmp_script), quiet=True)

    def server_docker(self):
        if self._is_done("server_docker"):
            return
        import tempfile
        from .docker import SimpleDocker
        docker = SimpleDocker()
        org, img, tag = self.versions.server_docker_name(as_tuple=True)
        if docker.exists(org, img, tag):
            return
        # get a copy of the repository in a temporary directory
        tmp_dir = tempfile.mkdtemp()
        tmp_repo = self._clone_repo(tmp_dir)
        # write the dockerfile
        dockerfile = """
        FROM bentoml/model-server:{0}
        MAINTAINER ersilia

        ENV LC_ALL=C.UTF-8
        ENV LANG=C.UTF-8

        WORKDIR {1}

        COPY . .

        RUN conda --version

        RUN conda install -c conda-forge rdkit
        RUN pip install .
        """.format(
            self.versions.bentoml_version(),
            self.cfg.ENV.DOCKER.IMAGE_WORKDIR
        )
        path = os.path.join(tmp_repo, "Dockerfile")
        with open(path, "w") as f:
            lines = dockerfile.split("\n")
            lines = lines[1:-1]
            for l in lines:
                f.write(l[8:]+"\n")
        docker.build(path=tmp_repo, org=org, img=img, tag=tag)


def base_installer():
    ins = Installer(check_install_log=False)
    ins.rdkit()


def check_dependencies():
    ins = Installer()
    ins.conda()
    ins.git()
    ins.rdkit()
    ins.config()
    ins.base_conda()
    ins.server_docker()

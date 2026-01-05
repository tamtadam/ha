from os import path
from setuptools import find_packages, setup

def execfile(fname, globs, locs=None):
    locs = locs or globs
    with open(fname, encoding="utf-8") as f:
        code = compile(f.read(), fname, "exec")
    exec(code, globs, locs)

version_ns = {}
try:
    execfile(path.join(path.abspath(path.dirname(__file__)), '_version.py'), version_ns)
except EnvironmentError:
    version = "dev"
else:
    version = version_ns.get("__version__", "dev")

setup(
    name='HomeAssistant',
    description='HomeAssistant',
    author='',
    version=version if version != 'dev' else '0.0.0.dev0',
    author_email='',
    packages=find_packages(include=("ha", "ha.*")),
    package_data={
        "": ["**/*.j2", "**/*.yml", "**/*.yaml"],
    },
    include_package_data=True,
)

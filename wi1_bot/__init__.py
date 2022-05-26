try:
    from setuptools_scm import get_version

    version = get_version()
except (ImportError, LookupError):
    version = "???"

__version__ = version

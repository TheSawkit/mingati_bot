from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mingati-bot")
except PackageNotFoundError:
    __version__ = "0.0.0"

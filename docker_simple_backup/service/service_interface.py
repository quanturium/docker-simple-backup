import abc
from pathlib import Path


class ServiceInterface(metaclass=abc.ABCMeta):
    def __init__(self, args):
        self.args = args

    @classmethod
    def __subclasshook__(cls, subclass):
        return (hasattr(subclass, 'copy_archive') and
                callable(subclass.copy_archive) and
                hasattr(subclass, 'remove_old_archives') and
                callable(subclass.remove_old_archives) or
                NotImplemented)

    @abc.abstractmethod
    def copy_archive(self, archive: Path):
        """Copy an archive to the service"""
        raise NotImplementedError

    @abc.abstractmethod
    def remove_old_archives(self, count: int):
        """Remove X older archives"""
        raise NotImplementedError

from pathlib import Path
from docker_simple_backup.service.service_interface import ServiceInterface
from shutil import copy2
import os
import logging

log = logging.getLogger(__name__)


class LocalService(ServiceInterface):
    def __init__(self, args):
        ServiceInterface.__init__(self, args)
        if args.service_local_dir is None:
            raise Exception(
                "Missing argument --service-local-dir for service: " + args.service
            )

    def copy_archive(self, archive: Path):
        print("Copying archive to folder...")
        destination = Path(self.args.service_local_dir)
        destination.mkdir(parents=True, exist_ok=True)
        copy2(archive, self.args.service_local_dir)
        print("Archive copied:", self.args.service_local_dir / archive.name)

    def remove_old_archives(self, max_count: int):
        destination = Path(self.args.service_local_dir)
        files = list(filter(lambda x: x.name.endswith(".zip"), destination.iterdir()))
        paths = sorted(files, key=os.path.getmtime, reverse=True)
        backup_count = len(paths)
        if backup_count > max_count:
            paths = paths[max_count:]
            for x in paths:
                x.unlink()
            print("Cleaned up", (backup_count - max_count), "old archive(s)")

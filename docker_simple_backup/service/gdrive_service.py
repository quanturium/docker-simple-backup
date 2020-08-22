from pathlib import Path
from docker_simple_backup.service.service_interface import ServiceInterface
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import pickle
from googleapiclient.http import MediaFileUpload
import logging

SCOPES = ["https://www.googleapis.com/auth/drive"]
log = logging.getLogger(__name__)


class GdriveService(ServiceInterface):
    def __init__(self, args):
        ServiceInterface.__init__(self, args)
        if args.service_gdrive_credentials is None:
            raise Exception(
                "Missing argument --service-gdrive-credentials for service: "
                + args.service
            )
        elif not Path(args.service_gdrive_credentials).exists():
            raise Exception(args.service_gdrive_credentials, "does not exists")
        if args.service_gdrive_folder is None:
            raise Exception(
                "Missing argument --service-gdrive-folder for service: " + args.service
            )

    def copy_archive(self, archive: Path):
        gdrive = self.get_gdrive()
        print("Uploading archive to gdrive...")
        file_id = self.upload_archive(gdrive, self.args.service_gdrive_folder, archive)
        print("Archive uploaded:", file_id)

    def remove_old_archives(self, max_count: int):
        gdrive = self.get_gdrive()
        result = self.list_files(gdrive, self.args.service_gdrive_folder)
        result = list(filter(lambda x: x["name"].endswith(".zip"), result))
        result = sorted(result, key=lambda x: x["createdTime"], reverse=True)
        backup_count = len(result)
        if backup_count > max_count:
            result = result[max_count:]
            for x in result:
                self.remove_file(gdrive, x["id"])
            print("Cleaned up", (backup_count - max_count), "old archive(s)")

    def get_gdrive(self):
        creds = None
        # The pickle file stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        cached_credentials_file = Path("google_drive_token.pickle")
        if cached_credentials_file.exists():
            with open(cached_credentials_file, "rb") as token:
                creds = pickle.load(token)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                creds = service_account.Credentials.from_service_account_file(
                    self.args.service_gdrive_credentials, scopes=SCOPES
                )
            # Save the credentials for the next run
            with open(cached_credentials_file, "wb") as token:
                pickle.dump(creds, token)
        # return Google Drive API service
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    def upload_archive(self, gdrive, folder_id, archive: Path):
        file_metadata = {"name": archive.name, "parents": [folder_id]}
        media = MediaFileUpload(archive.as_posix(), resumable=True)
        file = (
            gdrive.files()
            .create(body=file_metadata, media_body=media, fields="name,id")
            .execute()
        )
        file_id = file.get("id")
        return file_id

    def list_files(self, gdrive, folder_id):
        listOfFiles = []
        query = f"'{folder_id}' in parents"
        # Get list of files in folder
        page_token = None
        while True:
            response = (
                gdrive.files()
                .list(
                    q=query,
                    fields="nextPageToken, files(id, name, mimeType, size, createdTime)",
                    pageToken=page_token,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                )
                .execute()
            )

            for file in response.get("files", []):
                listOfFiles.append(file)

            page_token = response.get("nextPageToken", None)
            if page_token is None:
                break

        return listOfFiles

    def remove_file(self, gdrive, file_id):
        gdrive.files().delete(fileId=file_id).execute()

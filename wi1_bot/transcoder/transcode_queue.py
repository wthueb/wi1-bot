import os
from typing import Any, cast

from mongoengine import Document, connect
from mongoengine.fields import StringField


class TranscodeItem(Document):
    objects: Any

    path = StringField(required=True)

    languages = StringField(required=False)

    video_params = StringField(required=False)
    audio_params = StringField(required=False)


class TranscodeQueue:
    def __init__(self) -> None:
        connect(
            "wi1_bot",
            connect=True,
            host=os.environ.get("MONGODB_CONNECTION_STRING", None),
            uuidrepresentation="standard",
        )

    def add(
        self,
        path: str,
        languages: str | None = None,
        video_params: str | None = None,
        audio_params: str | None = None,
    ) -> None:
        TranscodeItem(
            path=path,
            languages=languages,
            video_params=video_params,
            audio_params=audio_params,
        ).save()

    def get_one(self) -> TranscodeItem | None:
        return cast(TranscodeItem | None, TranscodeItem.objects.first())

    def remove(self, item: TranscodeItem) -> None:
        item.delete()

    def clear(self) -> None:
        TranscodeItem.objects.delete()

    @property
    def size(self) -> int:
        return cast(int, TranscodeItem.objects.count())


queue = TranscodeQueue()

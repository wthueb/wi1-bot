import os
from typing import Any, cast

from mongoengine import Document, connect
from mongoengine.fields import BooleanField, IntField, StringField


class TranscodeItem(Document):
    objects: Any

    path = StringField(required=True)

    copy_all_streams = BooleanField(required=False)
    languages = StringField(required=False)

    video_codec = StringField(required=False)
    video_bitrate = IntField(required=False)
    audio_codec = StringField(required=False)
    audio_channels = IntField(required=False)
    audio_bitrate = StringField(required=False)

    content_id = IntField(required=False)


class TranscodeQueue:
    def __init__(self) -> None:
        connect("wi1_bot", connect=True, host=os.environ.get("MONGODB_CONNECTION_STRING", None))

    def add(
        self,
        path: str,
        copy_all_streams: bool | None = None,
        languages: str | None = None,
        video_codec: str | None = None,
        video_bitrate: int | None = None,
        audio_codec: str | None = None,
        audio_channels: int | None = None,
        audio_bitrate: str | None = None,
        content_id: int | None = None,
    ) -> None:
        TranscodeItem(
            path=path,
            copy_all_streams=copy_all_streams,
            languages=languages,
            video_codec=video_codec,
            video_bitrate=video_bitrate,
            audio_codec=audio_codec,
            audio_channels=audio_channels,
            audio_bitrate=audio_bitrate,
            content_id=content_id,
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

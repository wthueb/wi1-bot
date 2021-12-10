from typing import Optional, Generic, Type, TypeVar
from types import MethodType

from mongoengine import (
    Document,
    connect,
)
from mongoengine.fields import StringField, IntField
from mongoengine.queryset import QuerySet


def no_op(self, x):
    return self


QuerySet.__class_getitem__ = MethodType(no_op, QuerySet)

U = TypeVar("U", bound=Document)


class QuerySetManager(Generic[U]):
    def __get__(self, instance: object, cls: Type[U]) -> QuerySet[U]:
        return QuerySet(cls, cls._get_collection())


class TranscodeItem(Document):
    objects = QuerySetManager["TranscodeItem"]()

    path = StringField(required=True)

    video_bitrate = IntField(required=True)
    audio_codec = StringField(required=True)
    audio_channels = IntField(required=True)
    audio_bitrate = StringField(required=True)

    content_id = IntField(required=False)


class TranscodeQueue:
    def __init__(self) -> None:
        connect("transcode_queue")

    def add(
        self,
        path: str,
        video_bitrate: int,
        audio_codec: str,
        audio_channels: int,
        audio_bitrate: str,
        content_id: Optional[int] = None,
    ) -> None:
        if content_id is not None:
            TranscodeItem(
                path=path,
                video_bitrate=video_bitrate,
                audio_codec=audio_codec,
                audio_channels=audio_channels,
                audio_bitrate=audio_bitrate,
                content_id=content_id,
            ).save()
        else:
            TranscodeItem(
                path=path,
                video_bitrate=video_bitrate,
                audio_codec=audio_codec,
                audio_channels=audio_channels,
                audio_bitrate=audio_bitrate,
            ).save()

    def get_one(self) -> Optional[TranscodeItem]:
        return TranscodeItem.objects.first()

    def remove(self, item: TranscodeItem) -> None:
        item.delete()

    def clear(self) -> None:
        TranscodeItem.objects.delete()

    @property
    def size(self):
        return TranscodeItem.objects.count()


queue = TranscodeQueue()

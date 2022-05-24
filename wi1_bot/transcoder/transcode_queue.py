from types import MethodType
from typing import Generic, Optional, Type, TypeVar

from mongoengine import Document, QuerySet, connect
from mongoengine.fields import IntField, StringField


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

    video_codec = StringField(required=False)
    video_bitrate = IntField(required=False)
    audio_codec = StringField(required=False)
    audio_channels = IntField(required=False)
    audio_bitrate = StringField(required=False)

    content_id = IntField(required=False)


class TranscodeQueue:
    def __init__(self) -> None:
        connect("wi1_bot", connect=False)

    def add(
        self,
        path: str,
        video_codec: Optional[str] = None,
        video_bitrate: Optional[int] = None,
        audio_codec: Optional[str] = None,
        audio_channels: Optional[int] = None,
        audio_bitrate: Optional[str] = None,
        content_id: Optional[int] = None,
    ) -> None:
        TranscodeItem(
            path=path,
            video_codec=video_codec,
            video_bitrate=video_bitrate,
            audio_codec=audio_codec,
            audio_channels=audio_channels,
            audio_bitrate=audio_bitrate,
            content_id=content_id,
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

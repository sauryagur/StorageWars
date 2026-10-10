# coding: utf-8

from typing import ClassVar, Dict, List, Tuple  # noqa: F401

from openapi_server.models.health_get200_response import HealthGet200Response


class BaseSystemApi:
    subclasses: ClassVar[Tuple] = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        BaseSystemApi.subclasses = BaseSystemApi.subclasses + (cls,)
    async def health_get(
        self,
    ) -> HealthGet200Response:
        ...

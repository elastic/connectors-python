#
# Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
# or more contributor license agreements. Licensed under the Elastic License 2.0;
# you may not use this file except in compliance with the Elastic License 2.0.
#
"""
Collection of fake source classes for tests
"""
from functools import partial
from unittest.mock import Mock

from connectors.filtering.validation import (
    FilteringValidationResult,
    FilteringValidationState,
)


class FakeSource:
    """Fakey"""

    def __init__(self, configuration):
        self.configuration = configuration
        if configuration.has_field("raise"):
            raise Exception("I break on init")
        self.fail = configuration.has_field("fail")

    @staticmethod
    def name():
        return "Fakey"

    @staticmethod
    def service_type():
        return "fake"

    async def changed(self):
        return True

    async def ping(self):
        pass

    async def close(self):
        pass

    async def _dl(self, doc_id, timestamp=None, doit=None):
        if not doit:
            return
        return {"_id": doc_id, "_timestamp": timestamp, "text": "xx"}

    async def get_docs(self, filtering=None):
        if self.fail:
            raise Exception("I fail while syncing")
        yield {"_id": "1"}, partial(self._dl, "1")

    @classmethod
    def get_default_configuration(cls):
        return []

    @classmethod
    async def validate_filtering(cls, filtering):
        # being explicit about that this result should always be valid
        return FilteringValidationResult(
            state=FilteringValidationState.VALID, errors=[]
        )

    def tweak_bulk_options(self, options):
        pass


class FakeSourceFilteringValid(FakeSource):
    """Source with valid filtering."""

    @staticmethod
    def name():
        return "Source with valid filtering."

    @staticmethod
    def service_type():
        return "filtering_state_valid"

    @classmethod
    async def validate_filtering(cls, filtering):
        # use separate fake source to not rely on the behaviour in FakeSource which is used in many tests
        return FilteringValidationResult(
            state=FilteringValidationState.VALID, errors=[]
        )


class FakeSourceFilteringStateInvalid(FakeSource):
    """Source with filtering in state invalid."""

    @staticmethod
    def name():
        return "Source with filtering in state invalid."

    @staticmethod
    def service_type():
        return "filtering_state_invalid"

    @classmethod
    async def validate_filtering(cls, filtering):
        return FilteringValidationResult(state=FilteringValidationState.INVALID)


class FakeSourceFilteringStateEdited(FakeSource):
    """Source with filtering in state edited."""

    @staticmethod
    def name():
        return "Source with filtering in state edited."

    @staticmethod
    def service_type():
        return "filtering_state_edited"

    @classmethod
    async def validate_filtering(cls, filtering):
        return FilteringValidationResult(state=FilteringValidationState.EDITED)


class FakeSourceFilteringErrorsPresent(FakeSource):
    """Source with filtering errors."""

    @staticmethod
    def name():
        return "Source with filtering errors."

    @staticmethod
    def service_type():
        return "filtering_errors_present"

    @classmethod
    async def validate_filtering(cls, filtering):
        return FilteringValidationResult(errors=[Mock()])


class FakeSourceTS(FakeSource):
    """Fake source with stable TS"""

    ts = "2022-10-31T09:04:35.277558"

    @staticmethod
    def name():
        return "Fake source with stable TS"

    @staticmethod
    def service_type():
        return "fake_ts"

    async def get_docs(self, filtering=None):
        if self.fail:
            raise Exception("I fail while syncing")
        yield {"_id": "1", "_timestamp": self.ts}, partial(self._dl, "1")


class FailsThenWork(FakeSource):
    """Buggy"""

    fail = True

    @staticmethod
    def name():
        return "Buggy"

    @staticmethod
    def service_type():
        return "fail_once"

    async def get_docs(self, filtering=None):
        if FailsThenWork.fail:
            FailsThenWork.fail = False
            raise Exception("I fail while syncing")
        yield {"_id": "1"}, partial(self._dl, "1")


class LargeFakeSource(FakeSource):
    """Phatey"""

    @staticmethod
    def name():
        return "Phatey"

    @staticmethod
    def service_type():
        return "large_fake"

    async def get_docs(self, filtering=None):
        for i in range(1001):
            doc_id = str(i + 1)
            yield {"_id": doc_id, "data": "big" * 4 * 1024}, partial(self._dl, doc_id)

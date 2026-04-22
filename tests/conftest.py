# Copyright (c) 2026 Imperal, Inc., Valentin Scerbacov, and contributors
# Licensed under the AGPL-3.0 License. See LICENSE file for details.
import pytest

from imperal_sdk.auth.user import User


class _MockFactory:
    def build_system_ctx(self, ext_id="test-ext", tenant_id="default"):
        from imperal_sdk.context import Context
        from imperal_sdk.store.client import StoreClient

        store = StoreClient(gateway_url="http://mock", service_token="",
                            extension_id=ext_id, user_id="__system__",
                            tenant_id=tenant_id)
        user = User(id="__system__", email="", tenant_id=tenant_id,
                    role="system", scopes=["*"], attributes={})
        # ai/storage/http/config: bare sentinel objects (identity-tested only)
        return Context(user=user, tenant=tenant_id, store=store,
                       ai=object(), storage=object(), http=object(),
                       config=object(), _extension_id=ext_id)


@pytest.fixture
def mock_store_factory():
    return _MockFactory()

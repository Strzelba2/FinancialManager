from __future__ import annotations

import allure
import pytest


@pytest.fixture(autouse=True)
def attach_warnings_to_allure(recwarn: pytest.WarningsChecker) -> pytest.Generator[None, None, None]:
    yield
    if recwarn.list:
        text = "\n".join(
            f"{w.category.__name__} ({w.filename}:{w.lineno}): {w.message}"
            for w in recwarn.list
        )
        allure.attach(text, name="Pytest Warnings", attachment_type=allure.attachment_type.TEXT)

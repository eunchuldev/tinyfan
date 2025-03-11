from tinyfan import asset


def test_preserve_original_functionality():
    @asset()
    def test(arg: str):
        return arg

    assert test(arg="test") == "test"


def test_asset_run():
    @asset()
    def test(ds: str):
        return ds

    actual, _ = test.asset.run({"ds": "2020-01-01"})
    expected = "2020-01-01"
    assert actual == expected


def test_async_asset_run():
    async def awaitable() -> str:
        return " awaited"

    @asset()
    async def test(ds: str):
        return ds + await awaitable()

    actual, _ = test.asset.run({"ds": "2020-01-01"})
    expected = "2020-01-01 awaited"
    assert actual == expected

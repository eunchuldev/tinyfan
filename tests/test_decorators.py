from tinyfan import asset


def test_preserve_original_functionality():
    @asset()
    def test(arg: str):
        return arg

    assert test(arg="test") == "test"

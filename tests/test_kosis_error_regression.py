import pytest

from kosis_client import KosisApiError, _validate_row_payload


def test_kosis_err_object_is_reported_as_api_error():
    with pytest.raises(KosisApiError) as caught:
        _validate_row_payload({"err": "30", "errMsg": "데이터가 존재하지 않습니다."})
    assert caught.value.err == "30"
    assert caught.value.err_msg == "데이터가 존재하지 않습니다."

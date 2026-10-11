import base64

from openapi_server.impl.ingest import _FIXTURE_PNG, _image_bytes, _text


def test_amazon_metadata_list_fields_are_converted():
    assert _text(["Product details", "Second paragraph", None]) == (
        "Product details; Second paragraph"
    )
    image_data_url = "data:image/png;base64," + base64.b64encode(_FIXTURE_PNG).decode(
        "ascii"
    )
    row_images = {
        "hi_res": [None, image_data_url],
        "large": ["https://example.invalid/unused.png"],
        "thumb": [],
    }
    assert _image_bytes(row_images) == _FIXTURE_PNG

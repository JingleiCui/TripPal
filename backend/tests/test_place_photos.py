from travel_agent.providers.amap import place_photo_url, normalize_places


def test_amap_http_photos_are_upgraded_instead_of_silently_discarded():
    source = "http://store.is.autonavi.com/showpic/poi.jpg?size=large"
    assert place_photo_url(source) == "https://store.is.autonavi.com/showpic/poi.jpg?size=large"
    assert place_photo_url("//aos-comment.amap.com/image.jpg") == "https://aos-comment.amap.com/image.jpg"
    assert place_photo_url("javascript:alert(1)") is None
    assert place_photo_url("http://unknown.example/photo.jpg") is None
    assert place_photo_url("http://user:secret@store.is.autonavi.com/photo.jpg") is None
    raw = {
        "retrieved_at": "2026-11-13T00:00:00Z",
        "data": {
            "pois": [
                {
                    "id": "test",
                    "name": "景山公园",
                    "location": "116.39,39.92",
                    "photos": [
                        {"url": source},
                        {"url": "https://store.is.autonavi.com/showpic/poi.jpg?size=large"},
                        {"url": "https://store.is.autonavi.com/second.jpg"},
                    ],
                }
            ]
        },
    }
    assert len(normalize_places(raw, "北京")[0]["photos"]) == 2

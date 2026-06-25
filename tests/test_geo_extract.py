from app.crawlers.geo_extract import extract_geo


def test_extract_changsha_county_center():
    geo = extract_geo("长沙县发布山洪灾害风险预警")

    assert geo["city"] == "长沙市"
    assert geo["county"] == "长沙县"
    assert geo["geo_precision"] == "county"
    assert geo["lat"]
    assert geo["lng"]


def test_extract_river_name_and_default_changsha():
    geo = extract_geo("湘江长沙段水位上涨，需关注防汛调度。")

    assert geo["river_name"] == "湘江"
    assert geo["geo_precision"] == "city"


def test_extract_exact_coordinates():
    geo = extract_geo("监测点经度112.9388，纬度28.2282，出现滑坡变形迹象。")

    assert geo["geo_precision"] == "exact_point"
    assert geo["lat"] == 28.2282
    assert geo["lng"] == 112.9388

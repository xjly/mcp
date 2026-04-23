from weather import server


def test_tool_functions_exist():
    assert hasattr(server, "search_location_id_by_name")
    assert hasattr(server, "get_weather_forecast")
    assert hasattr(server, "get_weather_history")

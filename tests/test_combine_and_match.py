from agents.pdf_parameter_agent.tools import combine_and_match

def test_combine_and_match_basic():
    params = [
        {"id": "A", "p1": 10, "p2": 20},
        {"id": "B", "p1": 11, "p2": 21},
    ]
    t1 = [
        {"id": "A", "x": 100},
        {"id": "B", "x": 200},
    ]
    t2 = [
        {"id": "A", "y": 300},
        {"id": "B", "y": 400},
    ]

    out = combine_and_match(params, t1, t2, key="id")
    assert len(out) == 2
    a = [r for r in out if r["id"] == "A"][0]
    b = [r for r in out if r["id"] == "B"][0]
    assert a["t1_x"] == 100 and a["t2_y"] == 300
    assert b["t1_x"] == 200 and b["t2_y"] == 400
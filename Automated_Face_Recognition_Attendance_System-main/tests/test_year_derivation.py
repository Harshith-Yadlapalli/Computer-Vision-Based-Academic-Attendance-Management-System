import re

def derive_year_from_id(student_id: str, lateral: bool = False) -> str | None:
    sid = student_id.upper()
    # Lateral entries: e.g., L23CSE001 -> base 23 then +1 (cap at 4)
    if lateral and sid.startswith("L") and re.match(r"^L(\d{2})", sid):
        base = sid[1:3]
        mapping = {"23": "3", "24": "2", "25": "1"}
        base_year = mapping.get(base)
        if base_year is None:
            return None
        return str(min(int(base_year) + 1, 4))
    # Regular mapping (derived mode in app, with special 22->2)
    prefix = sid[:2]
    derived_map = {"21": "4", "22": "2", "23": "3", "24": "2", "25": "1", "20": "5"}
    return derived_map.get(prefix)

def test_regular_22_is_2nd_year_in_derived_mode():
    assert derive_year_from_id("22CSE001") == "2"

def test_lateral_L23_is_4th_year():
    assert derive_year_from_id("L23CSE001", lateral=True) == "4"

def test_regular_23_is_3rd_year():
    assert derive_year_from_id("23CSE001") == "3"

def run():
    test_regular_22_is_2nd_year_in_derived_mode()
    test_lateral_L23_is_4th_year()
    test_regular_23_is_3rd_year()
    print("All year derivation tests passed.")

if __name__ == "__main__":
    run()

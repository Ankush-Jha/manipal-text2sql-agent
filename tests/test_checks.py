from agent.checks import run_checks


def test_zero_rows():
    assert "zero_rows" in run_checks(["a"], [])


def test_all_null():
    assert "all_null_column" in run_checks(["a", "b"], [(1, None), (2, None)])


def test_percentage_over_100():
    assert "percentage_over_100" in run_checks(["pct_free"], [(130.0,)])
    assert run_checks(["pct_free"], [(30.0,)]) == []


def test_negative_count():
    assert "negative_count" in run_checks(["count(*)"], [(-1,)])


def test_row_explosion():
    rows = [(i,) for i in range(500)]
    assert "row_explosion" in run_checks(["x"], rows, sql="SELECT x FROM a JOIN b", base_rows=10)
    assert run_checks(["x"], rows, sql="SELECT x FROM a", base_rows=10) == []


def test_date_out_of_range():
    assert "date_out_of_range" in run_checks(["d"], [("2099-01-01",)], data_range=(2000, 2020))
    assert run_checks(["d"], [("2010-01-01",)], data_range=(2000, 2020)) == []


def test_clean_result_has_no_flags():
    assert run_checks(["name", "n"], [("a", 3), ("b", 4)]) == []

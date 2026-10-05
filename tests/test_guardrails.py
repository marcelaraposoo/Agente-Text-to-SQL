import pytest
from cineagent.guardrails import UnsafeSQLError, validate_sql


def test_select_ok_adds_limit():
    assert "LIMIT 500" in validate_sql("SELECT * FROM dim_movies;")


def test_with_ok():
    validate_sql("WITH a AS (SELECT 1) SELECT * FROM a LIMIT 5")


@pytest.mark.parametrize("sql", [
    "DROP TABLE dim_movies", "DELETE FROM dim_movies", "SELECT 1; DROP TABLE x",
    "UPDATE dim_movies SET title='x'", "PRAGMA table_info(x)", "", "ATTACH 'a.db' AS a",
])
def test_blocked(sql):
    with pytest.raises(UnsafeSQLError):
        validate_sql(sql)

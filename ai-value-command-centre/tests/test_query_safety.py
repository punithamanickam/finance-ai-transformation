import pytest

from src.db.database import ensure_database
from src.query import semantic_layer as Q

INJECTIONS = ["DROP TABLE ai_initiatives", "show initiatives; DELETE FROM risks", "select * from users",
              "initiatives with investment > 5 -- comment", "x' OR 1=1 --", "delete all initiatives",
              "show initiatives union select password_hash from users", "insert into risks values (1)",
              "update ai_initiatives set budget = 0", "attach database 'x' as y"]


@pytest.mark.parametrize("q", INJECTIONS)
def test_destructive_or_sql_input_is_refused(q):
    with pytest.raises(Q.QueryRefused):
        Q.parse(q)


def test_brief_example_generates_expected_sql():
    spec = Q.parse("Show AI investments above $5M.")
    sql, params = Q.render(spec)
    assert sql.startswith("SELECT ") and "FROM ai_initiative_metrics WHERE investment > :p0" in sql
    assert params == {"p0": 5_000_000.0}


def test_values_are_bound_not_interpolated():
    sql, params = Q.render(Q.parse("initiatives in EMEA with roi below 0"))
    assert "EMEA" not in sql and "EMEA" in params.values()


def test_bu_scope_always_filters():
    sql, params = Q.render(Q.parse("list initiatives"), bu_scope="BU-SCM")
    assert "bu_id = :scope" in sql and params["scope"] == "BU-SCM"
    rows = Q.execute(ensure_database(), sql, params)
    assert rows and all(r["business_unit"] == "Supply Chain & Manufacturing" for r in rows)


@pytest.mark.parametrize("sql", ["DELETE FROM risks", "SELECT * FROM users", "SELECT 1; DROP TABLE x", "SELECT name FROM ai_initiative_metrics -- x",
                                 "SELECT name FROM ai_initiative_metrics UNION SELECT password_hash FROM users"])
def test_validator_blocks_unsafe_sql(sql):
    with pytest.raises(Q.QueryRefused):
        Q.validate_sql(sql)


def test_unknown_fields_and_operators_are_rejected():
    with pytest.raises(Q.QueryRefused):
        Q.render(Q.QuerySpec("initiatives", ["password_hash"]))
    with pytest.raises(Q.QueryRefused):
        Q.render(Q.QuerySpec("initiatives", ["name"], [Q.Filter("name", "LIKE", "%")]))


def test_limit_is_capped():
    spec = Q.parse("top 5000 initiatives by investment")
    assert spec.limit <= Q.MAX_LIMIT


def test_results_match_engine(ctx):
    rows = Q.execute(ensure_database(), *Q.render(Q.parse("Show me all AI initiatives with more than $5M investment")))
    expected = set(ctx.table[ctx.table.investment > 5e6].initiative_id)
    assert {r["initiative_id"] for r in rows} == expected

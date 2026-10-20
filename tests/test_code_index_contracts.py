import pytest

from imperal_sdk.code_index import extract_contracts, match_contracts


def test_extracts_python_http_endpoints_with_provenance():
    text = '''
@router.post("/v1/orders/{order_id}", response_model=OrderOut)
async def create_order(order_id: int, body: OrderIn):
    return service.create(body)

@app.get('/healthz')
def health():
    return {"ok": True}
'''
    endpoints, schemas = extract_contracts("api/orders.py", text, "python")
    assert [(e.method, e.route, e.handler) for e in endpoints] == [
        ("POST", "/v1/orders/{order_id}", "create_order"),
        ("GET", "/healthz", "health"),
    ]
    assert endpoints[0].path == "api/orders.py"
    assert endpoints[0].line == 2
    assert "OrderIn" in endpoints[0].schema_refs
    assert "OrderOut" in endpoints[0].schema_refs


def test_extracts_pydantic_and_sqlalchemy_schemas():
    text = '''
class OrderIn(BaseModel):
    sku: str
    quantity: int = 1

class OrderRow(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    payload = mapped_column(JSON)
'''
    endpoints, schemas = extract_contracts("models.py", text, "python")
    assert not endpoints
    by_name = {s.name: s for s in schemas}
    assert by_name["OrderIn"].schema_kind == "model"
    assert by_name["OrderIn"].fields == ("quantity", "sku")
    assert by_name["OrderRow"].schema_kind == "table"
    assert by_name["OrderRow"].storage_name == "orders"
    assert by_name["OrderRow"].fields == ("id", "payload")


def test_extracts_typescript_express_and_interfaces():
    text = '''
router.put("/v1/users/:id", updateUser)
export interface UserPatch {
  displayName?: string;
  active: boolean;
}
'''
    endpoints, schemas = extract_contracts("routes/users.ts", text, "typescript")
    assert [(e.method, e.route, e.handler) for e in endpoints] == [
        ("PUT", "/v1/users/:id", "updateUser")
    ]
    assert schemas[0].name == "UserPatch"
    assert schemas[0].fields == ("active", "displayName")


def test_cross_repo_matching_is_deterministic_and_typed():
    producer_eps, producer_schemas = extract_contracts(
        "api.py",
        '@app.post("/v1/orders", response_model=OrderOut)\ndef create(body: OrderIn): pass\n',
        "python",
    )
    _, client_schemas = extract_contracts(
        "client.py", "class OrderIn(BaseModel):\n    sku: str\n", "python"
    )
    links = match_contracts(
        [
            {"repo_key": "producer", "endpoints": producer_eps, "schemas": producer_schemas},
            {"repo_key": "client", "endpoints": [], "schemas": client_schemas},
        ]
    )
    schema_links = [x for x in links if x["relation"] == "schema_name_match"]
    assert schema_links
    assert schema_links[0]["source_repo"] == "client"
    assert schema_links[0]["target_repo"] == "producer"




# ---- string keys (code graph phase 1, Task 3) ----

def _keys(path, text):
    pytest.importorskip("tree_sitter")  # the parser is the code-index extra, as in test_code_index_indexer
    from imperal_sdk.code_index import scope_facts
    return {(k.domain, k.key, k.role) for k in scope_facts(path, text).strings}


def test_activity_names_provided_and_used():
    keys = _keys("w.py", '@activity.defn(name="dispatch_local_tool")\nasync def dlt(p): pass\n'
                         '@activity.defn\nasync def foo(): pass\n'
                         'async def run():\n    await workflow.execute_activity("dispatch_local_tool", {})\n')
    assert ("activity", "dispatch_local_tool", "provides") in keys
    assert ("activity", "foo", "provides") in keys
    assert ("activity", "dispatch_local_tool", "uses") in keys


def test_workflows_and_signals():
    keys = _keys("wf.py", '@workflow.defn(name="Marathon")\nclass M: pass\n'
                          'async def go(c, h):\n    await c.start_workflow("X")\n    await h.signal("s", 1)\n')
    assert {("workflow", "Marathon", "provides"), ("workflow", "X", "uses"), ("signal", "s", "uses")} <= keys


def test_routes_provided_through_a_router_prefix_and_used_by_clients():
    provided = _keys("router.py", 'router = APIRouter(prefix="/v1/memory")\n@router.get("/repos")\n'
                                  'async def list_repos(): pass\n@router.get("/repo/{key}")\nasync def one(key): pass\n')
    assert ("route", "GET /v1/memory/repos", "provides") in provided
    assert ("route", "GET /v1/memory/repo/{}", "provides") in provided
    used = _keys("client.py", 'async def f(c, k):\n    await c.get("/v1/memory/repos")\n'
                              '    await c.get(f"/v1/memory/repo/{k}")\n')
    assert {("route", "GET /v1/memory/repos", "uses"), ("route", "GET /v1/memory/repo/{}", "uses")} <= used
    ts = _keys("ui/a.ts", 'fetch("/v1/memory/repos");\nfetch(`/v1/memory/repo/${k}`, {method: "POST"});\n')
    assert {("route", "GET /v1/memory/repos", "uses"), ("route", "POST /v1/memory/repo/{}", "uses")} <= ts


def test_events_by_literal_channel_only():
    keys = _keys("e.py", 'async def f(r, ch):\n    await r.publish("imperal:config:changed", 1)\n'
                         '    await r.publish(ch, 2)\n')
    assert keys == {("event", "imperal:config:changed", "uses")}


def test_route_key_normalises_placeholders_hosts_and_slashes():
    from imperal_sdk.code_index import route_key
    assert route_key("get", "https://api.x.io/v1/a/{id}/?q=1") == "GET /v1/a/{}"
    assert route_key("POST", "/app/[slug]//items/:id") == "POST /app/{}/items/{}"


def test_contract_evidence_is_also_schema_string_keys():
    """A model provides its schema name; an endpoint uses the schemas it references, under its handler --
    the account graph's schema nodes and endpoint_schema_ref edges come from these keys."""
    pytest.importorskip("tree_sitter")
    from imperal_sdk.code_index import scope_facts
    src = ('from pydantic import BaseModel\nrouter = APIRouter(prefix="/v1")\nclass OrderIn(BaseModel):\n'
           '    sku: str\n@router.post("/orders")\nasync def create_order(body: OrderIn):\n    return 1\n')
    keys = {(k.domain, k.key, k.role, k.in_def) for k in scope_facts("api.py", src).strings}
    assert ("schema", "OrderIn", "provides", "OrderIn") in keys
    assert ("schema", "OrderIn", "uses", "create_order") in keys
    assert ("route", "POST /v1/orders", "provides", "create_order") in keys

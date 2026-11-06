"""Field report 06.11 #3: the endpoints a change reaches -- its handler, or a handler that calls it."""
from imperal_sdk.code_links import contracts_reached

EPS = [{"repo": "gw", "method": "POST", "route": "/v1/terminal/tickets", "handler": "mint_terminal_ticket",
        "path": "app/routers/terminal.py"},
       {"repo": "gw", "method": "GET", "route": "/v1/health", "handler": "health", "path": "app/routers/health.py"},
       {"repo": "gw", "method": "POST", "route": "/v1/login", "handler": "Auth.login", "path": "app/routers/auth.py"}]
GRAPH = {"session_for_sid": ["app/routers/terminal.py::mint_terminal_ticket", "app/writers/auth.py::_write_auth_login"],
         "_write_auth_login": ["Auth.login"]}


def callers(names):
    return {n: GRAPH.get(n, []) for n in names}


def test_an_endpoint_whose_handler_calls_the_symbol_is_reached_with_its_chain():
    got = contracts_reached(["session_for_sid"], EPS, callers)
    assert [(e["route"], e["via"], e["chain"]) for e in got] == [
        ("/v1/terminal/tickets", "caller", "mint_terminal_ticket -> session_for_sid"),
        ("/v1/login", "caller", "login -> _write_auth_login -> session_for_sid")]


def test_the_handler_itself_and_the_depth_bound():
    assert contracts_reached(["app/routers/health.py::health"], EPS, callers)[0]["via"] == "handler"
    assert [e["route"] for e in contracts_reached(["session_for_sid"], EPS, callers, depth=1)] == ["/v1/terminal/tickets"]


def test_a_failing_graph_keeps_what_was_reached_and_nothing_is_invented():
    def boom(names):
        raise RuntimeError("vault down")
    assert contracts_reached(["mint_terminal_ticket"], EPS, boom)[0]["via"] == "handler"
    assert contracts_reached(["nothing_calls_me"], EPS, callers) == []

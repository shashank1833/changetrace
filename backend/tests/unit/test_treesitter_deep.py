from services.repository_analysis.treesitter_parser import TreeSitterParser


def test_treesitter_arrow_functions_and_declarations():
    parser = TreeSitterParser()
    ts_code = """
    export const cancelSubscription = async (req: Request, res: Response) => {
        const sub = await db.subscriptions.findUnique({ where: { id: req.params.id } });
        sub.status = "CANCELLED";
        await db.commit();
        return res.json(sub);
    };

    export function activateSubscription(subId: string): void {
        console.log("Activating", subId);
    }
    """
    symbols = parser.extract_symbols(ts_code, language="typescript", file_path="subscriptions.ts")
    names = {s.name for s in symbols}
    assert "cancelSubscription" in names
    assert "activateSubscription" in names

    # Verify side effect detection on cancelSubscription
    cancel_sym = next(s for s in symbols if s.name == "cancelSubscription")
    side_effects = cancel_sym.details.get("side_effects", [])
    assert "db_mutation" in side_effects or "state_assignment" in side_effects


def test_treesitter_route_extraction():
    parser = TreeSitterParser()
    py_code = """
    @router.post("/api/v1/orders/{order_id}/refund")
    async def process_refund(order_id: str):
        return {"status": "refunded"}

    @app.get("/health")
    def health_check():
        return {"status": "ok"}
    """
    symbols = parser.extract_symbols(py_code, language="python", file_path="api.py")
    routes = [s for s in symbols if s.kind == "route"]
    route_names = {r.name for r in routes}

    assert "POST /api/v1/orders/{order_id}/refund" in route_names
    assert "GET /health" in route_names


def test_treesitter_sql_semantic_extraction():
    parser = TreeSitterParser()
    sql_code = """
    CREATE TABLE subscriptions (
        id VARCHAR(36) PRIMARY KEY,
        status VARCHAR(20) NOT NULL
    );

    INSERT INTO subscriptions (id, status) VALUES ('123', 'ACTIVE');
    UPDATE subscriptions SET status = 'CANCELLED' WHERE id = '123';
    DELETE FROM subscriptions WHERE id = '123';
    """
    symbols = parser.extract_symbols(sql_code, language="sql", file_path="schema.sql")
    sql_syms = [s for s in symbols if s.kind == "sql_operation"]
    ops = {s.name for s in sql_syms}

    assert "CREATE TABLE subscriptions" in ops
    assert "INSERT INTO subscriptions" in ops
    assert "UPDATE subscriptions" in ops
    assert "DELETE FROM subscriptions" in ops


def test_treesitter_metrics_tracking():
    parser = TreeSitterParser()
    code = "def simple_func(): pass"
    symbols = parser.extract_symbols(code, language="python", file_path="test.py")

    assert parser.metrics.total_files_attempted >= 1
    assert "function" in parser.metrics.symbols_extracted_by_kind
    assert len(symbols) >= 1

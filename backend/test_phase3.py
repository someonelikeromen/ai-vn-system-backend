import asyncio

async def test():
    from agents.state import AgentState, empty_state, SSEEventType
    from agents.graph import get_writing_app
    from agents.dm import run_dm
    from agents.chronicler import run_chronicler
    from agents.calibrator import run_calibrator, run_sandbox, run_planner, run_archiver
    from agents.npc import run_npc_actors, run_style_director
    from exchange.pricing import pricing_engine, TIER_BASE_PRICES, calculate_combat_reward
    from exchange.growth_service import growth_service
    from api.game import router
    from api.exchange import router as er
    from api.narrator import router as nr
    from memory.engine import memory_engine
    print("OK: All Phase 3 modules imported successfully")
    app = get_writing_app()
    print(f"OK: LangGraph compiled with {len(app.nodes)} nodes")
    prices = [TIER_BASE_PRICES[i]["M"] for i in range(6)]
    print(f"OK: Tier price table M: {prices}")
    print("PASS: Phase 3 acceptance test passed!")

asyncio.run(test())

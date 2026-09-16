#!/home/sy5/owui/bin/python3
import ray, traceback, sys
try:
    ray.init(address='127.0.0.1:6379', ignore_reinit_error=True, logging_level='error')
    nodes = ray.nodes()
    for n in nodes:
        print("NODE", n["NodeID"][:8], n["NodeManagerAddress"], "alive=", n["Alive"], flush=True)
    n3090 = [n for n in nodes if n["NodeManagerAddress"] == "192.168.5.41" and n["Alive"]]
    if not n3090:
        print("FAIL: node3090 not alive"); sys.exit(1)
    nid = n3090[0]["NodeID"]
    from goethe_orchestrator.contracts import WorkerRegistration, TaskEnvelope
    from goethe_orchestrator.orchestrator import LocalOrchestrator
    reg = WorkerRegistration(worker_id='node3090-smoke',
        capabilities={'node_ip':'192.168.5.41','ray_node_id':nid},
        ray_node_id=nid)
    orch = LocalOrchestrator(backend='ray', ray_address='127.0.0.1:6379')
    orch.register_worker(reg)
    env = TaskEnvelope(payload={"handler":"node_info","args":{},
                                "requires":{"node_ip":"192.168.5.41"}})
    dr = orch.dispatch(env)
    print("dispatched", dr.envelope_id if hasattr(dr, "envelope_id") else dr, flush=True)
    dr = orch.collect(dr, timeout=90)
    print("STATUS:", dr.status, flush=True)
    print("RESULT:", dr.result, flush=True)
    print("ERROR:", getattr(dr, "error", None), flush=True)
    print("SMOKE PASS" if dr.status == "COMPLETED" else "SMOKE FAIL", flush=True)
except SystemExit:
    raise
except Exception:
    traceback.print_exc()

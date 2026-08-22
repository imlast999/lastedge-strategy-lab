import json
import time
import urllib.request
import pytest
from services.api_server import ResearchAPIServer


def test_research_api_server_endpoints():
    port = 8892
    server = ResearchAPIServer(port=port)
    server.start()
    time.sleep(0.3)

    try:
        # Test status
        req = urllib.request.urlopen(f"http://localhost:{port}/api/research/status")
        assert req.status == 200
        data = json.loads(req.read().decode("utf-8"))
        assert data.get("ok") is True
        assert data.get("service") == "LastEdge Strategy Lab"
        assert data.get("status") == "ONLINE"

        # Test health
        req_health = urllib.request.urlopen(f"http://localhost:{port}/api/research/health")
        assert req_health.status == 200
        health_data = json.loads(req_health.read().decode("utf-8"))
        assert health_data.get("ok") is True

        # Test experiments
        req_exps = urllib.request.urlopen(f"http://localhost:{port}/api/research/experiments")
        assert req_exps.status == 200
        exps_data = json.loads(req_exps.read().decode("utf-8"))
        assert exps_data.get("ok") is True
        assert "experiments" in exps_data

        # Test candidates
        req_cand = urllib.request.urlopen(f"http://localhost:{port}/api/research/candidates")
        assert req_cand.status == 200
        cand_data = json.loads(req_cand.read().decode("utf-8"))
        assert cand_data.get("ok") is True
        assert "candidates" in cand_data

        # Test 404
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"http://localhost:{port}/api/non_existent")
        assert exc_info.value.code == 404

    finally:
        server.stop()
        time.sleep(0.2)

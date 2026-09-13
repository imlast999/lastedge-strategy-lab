import json
import time
import unittest
import urllib.request
import urllib.error
from services.api_server import ResearchAPIServer


class TestResearchAPIServer(unittest.TestCase):
    def test_research_api_server_endpoints(self):
        port = 8892
        server = ResearchAPIServer(port=port)
        server.start()
        time.sleep(0.3)

        try:
            # Test root / discovery index
            req_root = urllib.request.urlopen(f"http://localhost:{port}/")
            self.assertEqual(req_root.status, 200)
            root_data = json.loads(req_root.read().decode("utf-8"))
            self.assertTrue(root_data.get("ok"))
            self.assertEqual(root_data.get("service"), "LastEdge Strategy Lab")
            self.assertIn("endpoints", root_data)

            # Test status
            req = urllib.request.urlopen(f"http://localhost:{port}/api/research/status")
            self.assertEqual(req.status, 200)
            data = json.loads(req.read().decode("utf-8"))
            self.assertTrue(data.get("ok"))
            self.assertEqual(data.get("service"), "LastEdge Strategy Lab")
            self.assertEqual(data.get("status"), "ONLINE")

            # Test health
            req_health = urllib.request.urlopen(f"http://localhost:{port}/api/research/health")
            self.assertEqual(req_health.status, 200)
            health_data = json.loads(req_health.read().decode("utf-8"))
            self.assertTrue(health_data.get("ok"))

            # Test experiments
            req_exps = urllib.request.urlopen(f"http://localhost:{port}/api/research/experiments")
            self.assertEqual(req_exps.status, 200)
            exps_data = json.loads(req_exps.read().decode("utf-8"))
            self.assertTrue(exps_data.get("ok"))
            self.assertIn("experiments", exps_data)

            # Test candidates
            req_cand = urllib.request.urlopen(f"http://localhost:{port}/api/research/candidates")
            self.assertEqual(req_cand.status, 200)
            cand_data = json.loads(req_cand.read().decode("utf-8"))
            self.assertTrue(cand_data.get("ok"))
            self.assertIn("candidates", cand_data)

            # Test 404
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(f"http://localhost:{port}/api/non_existent")
            self.assertEqual(cm.exception.code, 404)

        finally:
            server.stop()
            time.sleep(0.2)


if __name__ == "__main__":
    unittest.main()

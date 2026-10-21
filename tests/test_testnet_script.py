import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script():
    path = ROOT / "scripts" / "testnet_e2e.py"
    spec = importlib.util.spec_from_file_location("testnet_e2e", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestnetScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = load_script()

    def test_parsers_read_cli_output(self):
        upload = "\n".join([
            "info",
            "https://stellar.expert/explorer/testnet/tx/" + "ab" * 32,
            "bafa5a29c0ea41043364778d70e13b3059230166971758f25a031f1ab3ddd879",
        ])
        self.assertEqual(
            self.script.wasm_hash(upload),
            "bafa5a29c0ea41043364778d70e13b3059230166971758f25a031f1ab3ddd879",
        )
        self.assertEqual(self.script.transaction_hashes(upload), ["ab" * 32])
        deploy = "Deployed!\nCD4LQD4JBNNOOPMXMZWUIEJOD47YC7DE2VJNVPGB4JFI5BEIF2BW7VWP\n"
        self.assertEqual(
            self.script.contract_id(deploy),
            "CD4LQD4JBNNOOPMXMZWUIEJOD47YC7DE2VJNVPGB4JFI5BEIF2BW7VWP",
        )
        invoked = "\n".join([
            "\U0001f4c5 CABC - Success - Event: Updated (updated), owner: \"G\"",
            "100000000000000000",
        ])
        self.assertEqual(self.script.invoke_result(invoked), "100000000000000000")
        self.assertEqual(
            self.script.truncate_hash("330609a5120d05942f49d4c0717fe12a2652c6890ae658ee532b3087dc755fa2"),
            "330609a5\u2026755fa2",
        )

    def test_manifest_matches_deployment_record(self):
        record = json.loads((ROOT / "deployments" / "testnet.json").read_text(encoding="utf-8"))
        manifest = (ROOT / "web" / "app" / "testnet-manifest.ts").read_text(encoding="utf-8")
        for json_key, web_key in self.script.WEB_KEYS.items():
            item = record["contracts"][json_key]
            self.assertIn('  {}: {{'.format(web_key), manifest)
            self.assertIn(item["contract_id"], manifest)
            self.assertIn(item["deploy_transaction"], manifest)
            self.assertIn(self.script.truncate_hash(item["wasm_hash"]), manifest)
        source = record.get(
            "source_account",
            "GBTZVQRXWUTOBJZU5VEZZVNOQIEP7TIHORJFG26FVAHJGCUPDC22BULU",
        )
        self.assertEqual(manifest, self.script.render_manifest(source, record["contracts"]))
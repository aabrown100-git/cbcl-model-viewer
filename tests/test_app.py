from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cbcl_model_viewer import app


class AppEntrypointTests(unittest.TestCase):
    def test_main_starts_server_without_opening_browser(self):
        fake_server = Mock()
        fake_app = SimpleNamespace(server=fake_server)
        fake_args = SimpleNamespace(models="examples/fontan", cache=".cbcl-cache", host="127.0.0.1", port=8080)

        with patch.object(app, "parse_args", return_value=fake_args), patch.object(app, "build_app", return_value=fake_app):
            app.main([])

        fake_server.start.assert_called_once_with(host="127.0.0.1", port=8080, open_browser=False)


if __name__ == "__main__":
    unittest.main()

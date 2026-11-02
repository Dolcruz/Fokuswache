import contextlib
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from service import FokusService
import win32service


class ServiceHostTests(unittest.TestCase):
    def host(self):
        host = object.__new__(FokusService)
        host.stop_requested = threading.Event()
        host.controller = None
        host.ReportServiceStatus = Mock()
        return host

    def test_stop_returns_to_scm_without_terminating_process(self):
        host = self.host()
        host.controller = Mock(stop=threading.Event())
        with patch('service.os._exit') as terminate:
            host.SvcStop()
        host.ReportServiceStatus.assert_called_once_with(win32service.SERVICE_STOP_PENDING)
        self.assertTrue(host.stop_requested.is_set())
        self.assertTrue(host.controller.stop.is_set())
        terminate.assert_not_called()

    def test_host_persists_before_returning_after_listener_finishes(self):
        host = self.host()
        controller = Mock(stop=threading.Event(), mutex=contextlib.nullcontext())

        def start_thread(*, target, daemon):
            self.assertTrue(daemon)
            return Mock(start=target)

        with patch('service.Controller', return_value=controller), patch('service.threading.Thread', side_effect=start_thread):
            host.SvcDoRun()
        controller.serve.assert_called_once_with()
        controller.persist.assert_called_once_with()
        self.assertTrue(controller.stop.is_set())

    def test_listener_failure_is_reported_by_service_host(self):
        host = self.host()
        controller = Mock(stop=threading.Event(), mutex=contextlib.nullcontext())
        controller.serve.side_effect = RuntimeError('listener failed')
        with tempfile.TemporaryDirectory() as folder, \
             patch('service.DATA', Path(folder)), \
             patch('service.Controller', return_value=controller), \
             patch('service.threading.Thread', side_effect=lambda *, target, daemon: Mock(start=target)):
            with self.assertRaisesRegex(RuntimeError, 'listener failed'):
                host.SvcDoRun()
            self.assertIn('listener failed', Path(folder, 'startup-error.log').read_text('utf-8'))


if __name__ == '__main__':
    unittest.main()

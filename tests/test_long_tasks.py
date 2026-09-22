import threading
import time
import unittest

from gestor_documental.long_tasks import (
    BatchTaskWorker,
    GlobalTaskError,
    LongTask,
    TaskState,
)


class LongTaskTests(unittest.TestCase):
    def test_progress_and_individual_error_do_not_stop_batch(self):
        task = LongTask("Importando casos", 3)

        def process(value):
            if value == 2:
                raise ValueError("fila inválida")
            return "ok", "listo", value

        BatchTaskWorker(task, [1, 2, 3], process).run()

        self.assertEqual(task.state, TaskState.COMPLETED)
        self.assertEqual(task.current, 3)
        self.assertEqual([detail.result for detail in task.details], ["ok", "error", "ok"])

    def test_pause_waits_before_starting_next_unit_and_resume_continues(self):
        task = LongTask("Sincronizando expedientes", 2)
        first_started = threading.Event()
        release_first = threading.Event()
        second_started = threading.Event()

        def process(value):
            if value == 1:
                first_started.set()
                release_first.wait(2)
            else:
                second_started.set()
            return "ok", "listo", value

        worker = BatchTaskWorker(task, [1, 2], process)
        thread = threading.Thread(target=worker.run)
        thread.start()
        self.assertTrue(first_started.wait(1))
        task.pause()
        release_first.set()
        time.sleep(0.05)
        self.assertEqual(task.state, TaskState.PAUSED)
        self.assertFalse(second_started.is_set())
        task.resume()
        thread.join(2)
        self.assertTrue(second_started.is_set())
        self.assertEqual(task.state, TaskState.COMPLETED)

    def test_cancel_finishes_current_unit_without_starting_next(self):
        task = LongTask("Importando casos", 2)
        first_started = threading.Event()
        release_first = threading.Event()
        processed = []

        def process(value):
            processed.append(value)
            if value == 1:
                first_started.set()
                release_first.wait(2)
            return "ok", "listo", value

        worker = BatchTaskWorker(task, [1, 2], process)
        thread = threading.Thread(target=worker.run)
        thread.start()
        self.assertTrue(first_started.wait(1))
        task.cancel()
        release_first.set()
        thread.join(2)

        self.assertEqual(processed, [1])
        self.assertEqual(task.current, 1)
        self.assertEqual(task.state, TaskState.CANCELLED)

    def test_global_error_stops_batch(self):
        task = LongTask("Sincronizando expedientes", 3)

        def process(value):
            if value == 2:
                raise GlobalTaskError("sesión vencida")
            return "ok", "listo", value

        BatchTaskWorker(task, [1, 2, 3], process).run()

        self.assertEqual(task.state, TaskState.ERROR)
        self.assertEqual(task.current, 1)
        self.assertEqual(task.error, "sesión vencida")


if __name__ == "__main__":
    unittest.main()

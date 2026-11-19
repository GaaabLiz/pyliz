from unittest.mock import Mock

import pytest

from pylizlib.qt.handler import operation_core
from pylizlib.qt.handler.operation_core import GenericTask, Operation, Task
from pylizlib.qt.handler.operation_domain import OperationInfo, OperationStatus


@pytest.fixture
def clock(monkeypatch):
    clock = Mock(return_value=0.0)
    monkeypatch.setattr(operation_core, "perf_counter", clock)
    return clock


def test_eta_uses_progress_after_startup_and_counts_down_on_repeated_progress(clock):
    operation = Operation([Task("search")], OperationInfo("search", ""))
    operation.set_operation_started()
    assert operation.get_eta_formatted() == "--:--"

    clock.return_value = 4.0
    operation.update_op_progress(10)
    assert operation.get_eta_formatted() == "--:--"

    clock.return_value = 4.125
    operation.update_op_progress(10)
    assert operation.get_eta_formatted() == "--:--"

    clock.return_value = 4.25
    operation.update_op_progress(20)
    assert operation.time_estimated_total == pytest.approx(6.25)
    assert operation.get_eta_formatted() == "00:02"

    for progress, elapsed in [(20, 4.75), (19, 5.0), (20, 5.25)]:
        clock.return_value = elapsed
        operation.update_op_progress(progress)

    assert operation.time_estimated_total == pytest.approx(6.25)
    assert operation.time_estimated_remaining == pytest.approx(1.0)
    assert operation.get_eta_formatted() == "00:01"


def test_eta_starts_with_configured_duration_and_adapts_to_progress(clock):
    operation = Operation([Task("search")], OperationInfo("search", "", estimated_duration=8.0))
    updates = []
    operation.signals.op_start.connect(lambda: updates.append(("start", operation.get_eta_formatted())))
    operation.signals.op_eta_update.connect(lambda op_id, eta: updates.append((op_id, eta)))

    operation.set_operation_started()

    assert operation.progress == 0
    assert operation.time_estimated_total == operation.time_estimated_remaining == 8.0
    assert updates == [("start", "00:08"), (operation.id, "00:08")]

    clock.return_value = 1.0
    operation.update_op_progress(10)
    assert operation.get_eta_formatted() == "00:07"

    clock.return_value = 1.5
    operation.update_op_progress(20)
    assert operation.time_estimated_total == pytest.approx(6.7)
    assert operation.get_eta_formatted() == "00:06"


def test_eta_suppresses_small_boundary_changes_but_reflects_a_slowdown(clock):
    def search(task):
        for current, elapsed in [(1, 0.5), (2, 0.625), (3, 0.8125), (4, 0.96875), (5, 1.875)]:
            clock.return_value = elapsed
            task.gen_update_task_progress(current, 10)
        clock.return_value = 3.0

    operation = Operation([GenericTask("search", search)], OperationInfo("search", ""))
    eta_updates = []
    progress_updates = []
    operation.signals.op_eta_update.connect(lambda op_id, eta: eta_updates.append(eta))
    operation.signals.op_update_progress.connect(lambda op_id, progress: progress_updates.append(progress))

    operation.execute()

    assert eta_updates == ["00:01", "00:02", "00:00"]
    assert progress_updates == [10, 20, 30, 40, 50, 100]


@pytest.mark.parametrize(
    ("status", "final_eta"),
    [(OperationStatus.Completed, "00:00"), (OperationStatus.Cancelled, "--:--"), (OperationStatus.Failed, "--:--")],
)
def test_operation_finalizes_eta_with_actual_duration(clock, monkeypatch, status, final_eta):
    def search(task):
        task.update_task_progress(30)
        clock.return_value = 3.0
        if status == OperationStatus.Cancelled:
            task.cancel()
        elif status == OperationStatus.Failed:
            raise ValueError("search failed")

    def advance_clock(seconds):
        clock.return_value += seconds

    monkeypatch.setattr(operation_core, "sleep", advance_clock)
    operation = Operation([GenericTask("search", search)], OperationInfo("search", "", delay_each_task=1.0, estimated_duration=8.0))
    eta_updates = []
    operation.signals.op_eta_update.connect(lambda op_id, eta: eta_updates.append(eta))

    operation.execute()

    assert operation.status == status
    assert operation.time_elapsed == operation.time_estimated_total == 4.0
    assert operation.time_estimated_remaining == 0
    assert operation.get_eta_formatted() == eta_updates[-1] == final_eta
    if status == OperationStatus.Completed:
        assert eta_updates == ["00:08", "00:01", "00:00"]
